"""Regras de dominio do login OIDC (T21, A9): allowlist por tenant,
resolucao/vinculo de `credenciais` (`tipo='sso'`) e emissao da MESMA sessao
que `autenticar`/`renovarSessao` (F1, `app.identidade.tokens`) ja emitem.

**Nunca cria `usuarios` novo** (proibicao 11 do PCF, decisao de escopo de
T21): a primeira vez que uma identidade federada aparece, ela so e aceita se
ja existir um `usuarios` com o MESMO e-mail (case-insensitive) no tenant --
casos contrario responde `PONTO-AUTH-001`, a mesma resposta (deliberadamente
identica) que login por senha ja usa para nao virar oraculo de conta
existente.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import uuid
from dataclasses import dataclass

import sqlalchemy as sa
from ponto_contracts import Credencial, Usuario
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.erros import ErroDeAplicacao
from app.identidade.sso.oidc import configuracao as config_sso
from app.identidade.sso.oidc.protocolo import ClaimsIdToken
from app.identidade.tokens import jwt as jwt_mod
from app.identidade.tokens import refresh as refresh_mod
from app.identidade.tokens import sessao as sessao_mod

#: `sessoes.canal` (schema.sql) so aceita 'web'/'mobile'/'totem'/'api'/
#: 'terminal' -- nao ha 'sso'. O login federado e, por natureza, um fluxo de
#: navegador: reaproveita 'web', o mesmo canal do login por senha na tela de
#: login. O que distingue a origem SSO da senha e `credenciais.tipo`, nunca
#: `sessoes.canal`.
CANAL_SESSAO = "web"


async def verificar_provedor_habilitado(
    sessao_db: AsyncSession, *, tenant_id: uuid.UUID, provedor: str
) -> None:
    """`PONTO-TEN-001` quando o tenant nao configurou nenhuma allowlist para `provedor`.

    Falha FECHADA de proposito: sem `GET/PUT /v1/admin/sso/provedores`
    configurado, o provedor fica desabilitado para o tenant, mesmo que o app
    OIDC compartilhado da aplicacao esteja ativo. Chamada cedo, em `iniciar`,
    para nao gastar um round-trip inteiro ao IdP so para falhar no callback.
    """
    chave = (
        config_sso.CHAVE_GOOGLE_DOMINIOS
        if provedor == "google"
        else config_sso.CHAVE_ENTRA_TENANT_ID
    )
    valor = await config_sso.ler_valor(sessao_db, tenant_id=tenant_id, chave=chave)
    vazio = (
        valor is None
        or (isinstance(valor, list) and not valor)
        or (isinstance(valor, str) and not valor.strip())
    )
    if vazio:
        raise ErroDeAplicacao(
            "PONTO-TEN-001", detalhe="SSO nao configurado para este tenant/provedor"
        )


async def verificar_identidade_permitida(
    sessao_db: AsyncSession, *, tenant_id: uuid.UUID, provedor: str, claims: ClaimsIdToken
) -> None:
    """`PONTO-TEN-001` quando o dominio (google) ou o tenant_id do IdP (entra_id)
    nao esta na allowlist do tenant SEEG."""
    if provedor == "google":
        dominios = await config_sso.ler_valor(
            sessao_db, tenant_id=tenant_id, chave=config_sso.CHAVE_GOOGLE_DOMINIOS
        )
        permitidos = {str(d).lower() for d in dominios} if isinstance(dominios, list) else set()
        dominio_email = (claims.email or "").rsplit("@", 1)[-1].lower() if claims.email else ""
        if not dominio_email or dominio_email not in permitidos:
            raise ErroDeAplicacao(
                "PONTO-TEN-001", detalhe="dominio de e-mail nao autorizado para este tenant"
            )
    else:
        tenant_id_entra_permitido = await config_sso.ler_valor(
            sessao_db, tenant_id=tenant_id, chave=config_sso.CHAVE_ENTRA_TENANT_ID
        )
        if not tenant_id_entra_permitido or claims.tid != str(tenant_id_entra_permitido):
            raise ErroDeAplicacao(
                "PONTO-TEN-001", detalhe="tenant_id do Entra ID nao autorizado para este tenant"
            )


def _hash_identificador_externo(identificador_externo: str) -> str:
    """`credenciais.hash` e `NOT NULL`, mas nao ha segredo para comparar aqui:
    quem verifica a identidade e o IdP, nao esta coluna. Mesmo padrao de
    `algoritmo='nenhum'` que `app.identidade.mfa.recuperacao` ja estabelece
    para credencial que nao e senha (SHA-256 do valor, so para nunca deixar o
    campo vazio nem repetir o `sub`/e-mail do provedor em claro na coluna)."""
    return hashlib.sha256(identificador_externo.encode("utf-8")).hexdigest()


async def _usuario_por_email(
    sessao_db: AsyncSession, *, tenant_id: uuid.UUID, email: str
) -> Usuario | None:
    return (
        await sessao_db.execute(
            sa.select(Usuario).where(
                Usuario.tenant_id == tenant_id,
                sa.func.lower(Usuario.email) == email.strip().lower(),
                Usuario.excluido_em.is_(None),
            )
        )
    ).scalar_one_or_none()


async def _credencial_sso_por_identidade(
    sessao_db: AsyncSession, *, tenant_id: uuid.UUID, provedor: str, identificador_externo: str
) -> Credencial | None:
    return (
        await sessao_db.execute(
            sa.select(Credencial).where(
                Credencial.tenant_id == tenant_id,
                Credencial.tipo == "sso",
                Credencial.provedor_sso == provedor,
                Credencial.identificador_externo == identificador_externo,
                Credencial.ativo.is_(True),
            )
        )
    ).scalar_one_or_none()


async def _credencial_sso_ativa_do_usuario(
    sessao_db: AsyncSession, *, tenant_id: uuid.UUID, usuario_id: uuid.UUID
) -> Credencial | None:
    return (
        await sessao_db.execute(
            sa.select(Credencial).where(
                Credencial.tenant_id == tenant_id,
                Credencial.usuario_id == usuario_id,
                Credencial.tipo == "sso",
                Credencial.ativo.is_(True),
            )
        )
    ).scalar_one_or_none()


async def _resolver_usuario_e_credencial(
    sessao_db: AsyncSession, *, tenant_id: uuid.UUID, provedor: str, claims: ClaimsIdToken
) -> Usuario:
    """Resolve o `usuarios` para este login, vinculando (nunca criando) a `credenciais`.

    1. Vinculo exato (provedor, identificador_externo) ja existe -> usa direto.
    2. Senao, resolve `usuarios` pelo e-mail da claim. Sem usuario -> `PONTO-AUTH-001`
       (nunca cria usuario novo, proibicao 11 do PCF).
    3. Usuario ja tem OUTRA credencial `sso` ativa (outro provedor/identificador)?
       `uq_credenciais_ativa` permite no maximo UMA linha `tipo='sso'` ativa por
       usuario -- nao ha como manter duas em paralelo sem tabela nova (fora do
       escopo desta fase). Decisao desta fase, documentada aqui e no relatorio:
       o login bem-sucedido MAIS RECENTE re-vincula a credencial ativa ao
       provedor/identificador atual, em vez de falhar. Cobre o caso legitimo de
       uma empresa migrando de Google para Entra (ou vice-versa) sem exigir
       intervencao manual antes do primeiro login no provedor novo.
    4. Sem credencial `sso` previa -- cria uma.
    """
    credencial = await _credencial_sso_por_identidade(
        sessao_db, tenant_id=tenant_id, provedor=provedor, identificador_externo=claims.sub
    )
    if credencial is not None:
        usuario = await sessao_db.get(Usuario, credencial.usuario_id)
        if usuario is None:
            raise ErroDeAplicacao("PONTO-AUTH-001")
        return usuario

    if not claims.email:
        raise ErroDeAplicacao("PONTO-AUTH-001")
    usuario = await _usuario_por_email(sessao_db, tenant_id=tenant_id, email=claims.email)
    if usuario is None:
        raise ErroDeAplicacao("PONTO-AUTH-001")

    credencial_ativa = await _credencial_sso_ativa_do_usuario(
        sessao_db, tenant_id=tenant_id, usuario_id=usuario.id
    )
    if credencial_ativa is not None:
        credencial_ativa.provedor_sso = provedor
        credencial_ativa.identificador_externo = claims.sub
        credencial_ativa.hash = _hash_identificador_externo(claims.sub)
    else:
        sessao_db.add(
            Credencial(
                tenant_id=tenant_id,
                usuario_id=usuario.id,
                tipo="sso",
                provedor_sso=provedor,
                identificador_externo=claims.sub,
                hash=_hash_identificador_externo(claims.sub),
                algoritmo="nenhum",
                ativo=True,
            )
        )
    await sessao_db.flush()
    return usuario


@dataclass(frozen=True, slots=True)
class ResultadoLoginSso:
    usuario: Usuario
    access_token: str
    refresh_token: str
    expires_in: int
    sessao_id: uuid.UUID


async def resolver_e_emitir_sessao(
    sessao_db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    provedor: str,
    claims: ClaimsIdToken,
    ip: str | None,
    user_agent: str | None,
    agora: _dt.datetime | None = None,
) -> ResultadoLoginSso:
    agora = agora or _dt.datetime.now(_dt.UTC)

    await verificar_identidade_permitida(
        sessao_db, tenant_id=tenant_id, provedor=provedor, claims=claims
    )
    usuario = await _resolver_usuario_e_credencial(
        sessao_db, tenant_id=tenant_id, provedor=provedor, claims=claims
    )

    if usuario.status in ("bloqueado", "inativo"):
        raise ErroDeAplicacao("PONTO-AUTH-010")

    usuario.ultimo_acesso_em = agora
    usuario.ultimo_acesso_ip = ip

    nova_sessao = await sessao_mod.criar_sessao(
        sessao_db,
        tenant_id=tenant_id,
        usuario_id=usuario.id,
        canal=CANAL_SESSAO,
        ip=ip,
        user_agent=user_agent,
        agora=agora,
    )
    emitido = await refresh_mod.emitir(
        sessao_db,
        tenant_id=tenant_id,
        usuario_id=usuario.id,
        sessao_id=nova_sessao.id,
        ip=ip,
        user_agent=user_agent,
        agora=agora,
    )
    access_token, expires_in = jwt_mod.emitir_access_token(
        usuario_id=usuario.id,
        tenant_id=tenant_id,
        email=usuario.email,
        sessao_id=nova_sessao.id,
        agora=agora,
    )
    return ResultadoLoginSso(
        usuario=usuario,
        access_token=access_token,
        refresh_token=emitido.token,
        expires_in=expires_in,
        sessao_id=nova_sessao.id,
    )
