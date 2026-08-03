"""Resolve/vincula `credenciais` (tipo='sso', provedor_sso='saml') e emite o
MESMO par de tokens de sessao que `autenticar`/`renovarSessao` (F1) ja
emitem -- RFC-018/ADR-013: SSO e uma FORMA alternativa de autenticar, nunca
um mecanismo de sessao paralelo (`app.identidade.tokens.{sessao,refresh,jwt}`
reaproveitados por import, nada reimplementado).

**Nunca cria `usuarios` novo** (proibicao 11 do PCF de F13): resolve por
e-mail contra um usuario JA EXISTENTE no tenant (o `NameID` da asserção, no
formato `emailAddress` que este sistema exige -- ver `protocolo.py`). Login
SSO para um e-mail sem usuario correspondente e rejeitado com o mesmo
`PONTO-AUTH-001` do login por senha, para nao virar oraculo de conta
existente (mesmo cuidado que `app.identidade.autenticacao.servico.login` ja
tem para senha errada vs. usuario inexistente).

**Achado de contrato documentado aqui (nao escondido, ver relatorio da
fase).** `credenciais` so permite UMA linha ATIVA por `(tenant_id,
usuario_id, tipo)` (`uq_credenciais_ativa`, `schema.sql`) -- nao ha coluna na
chave unica que distinga "sso via google" de "sso via saml". Se um usuario
que ja tem uma `credenciais` ativa tipo='sso' para OUTRO provedor (ex.:
Google, vinculada por `app.identidade.sso.oidc`) fizer login por SAML pela
primeira vez, a unica forma de honrar o login sem violar a constraint e
REPONTAR a mesma linha para `provedor_sso='saml'`/o novo `identificador_
externo` -- e seguro porque a troca so acontece DEPOIS de a asserção SAML
ja ter sido validada contra o certificado do IdP do tenant (nunca antes).
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
from app.identidade.tokens import jwt as jwt_mod
from app.identidade.tokens import refresh as refresh_mod
from app.identidade.tokens import sessao as sessao_mod

PROVEDOR = "saml"

#: `sessoes.canal` (schema.sql) aceita so 'web'/'mobile'/'totem'/'api'/
#: 'terminal' -- sem valor 'sso'. O SAML deste sistema e sempre um fluxo de
#: navegador iniciado por link/redirecionamento (nunca app nativo nem
#: terminal), entao 'web' e o canal correto sem exigir migration nova.
CANAL_SESSAO = "web"


@dataclass(frozen=True, slots=True)
class ResultadoLoginSso:
    usuario: Usuario
    access_token: str
    refresh_token: str
    expires_in: int
    sessao_id: uuid.UUID


def _hash_identificador(identificador_externo: str) -> str:
    """`credenciais.hash` e `NOT NULL` para todo `tipo`, mas SSO nao tem
    segredo local -- a autenticidade vem da assinatura da asserção SAML, nao
    deste campo. sha256 do proprio `identificador_externo` (ja publico, ver
    comentario da coluna em `schema.sql`) so satisfaz a constraint; nunca e
    tratado como segredo em lugar nenhum deste modulo."""
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
    sessao_db: AsyncSession, *, tenant_id: uuid.UUID, identificador_externo: str
) -> Credencial | None:
    return (
        await sessao_db.execute(
            sa.select(Credencial).where(
                Credencial.tenant_id == tenant_id,
                Credencial.tipo == "sso",
                Credencial.provedor_sso == PROVEDOR,
                Credencial.identificador_externo == identificador_externo,
                Credencial.ativo.is_(True),
            )
        )
    ).scalar_one_or_none()


async def resolver_ou_vincular_usuario(
    sessao_db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    identificador_externo: str,
    agora: _dt.datetime,
) -> Usuario:
    """`PONTO-AUTH-001` quando nenhum `usuarios` corresponde ao `NameID` --
    mesma resposta (e mesmo motivo: nao virar oraculo de conta) do login por
    senha. Nunca cria `usuarios` novo."""
    credencial_existente = await _credencial_sso_por_identidade(
        sessao_db, tenant_id=tenant_id, identificador_externo=identificador_externo
    )
    if credencial_existente is not None:
        usuario = (
            await sessao_db.execute(
                sa.select(Usuario).where(Usuario.id == credencial_existente.usuario_id)
            )
        ).scalar_one_or_none()
        if usuario is None:
            raise ErroDeAplicacao("PONTO-AUTH-001")
        return usuario

    usuario = await _usuario_por_email(sessao_db, tenant_id=tenant_id, email=identificador_externo)
    if usuario is None:
        raise ErroDeAplicacao("PONTO-AUTH-001")

    credencial_sso_do_usuario = (
        await sessao_db.execute(
            sa.select(Credencial).where(
                Credencial.tenant_id == tenant_id,
                Credencial.usuario_id == usuario.id,
                Credencial.tipo == "sso",
                Credencial.ativo.is_(True),
            )
        )
    ).scalar_one_or_none()

    hash_valor = _hash_identificador(identificador_externo)
    if credencial_sso_do_usuario is not None:
        # Repontar (ver docstring do modulo) -- nunca duas linhas ativas de
        # tipo='sso' para o mesmo usuario, a constraint do banco proibiria.
        credencial_sso_do_usuario.provedor_sso = PROVEDOR
        credencial_sso_do_usuario.identificador_externo = identificador_externo
        credencial_sso_do_usuario.hash = hash_valor
        credencial_sso_do_usuario.algoritmo = "nenhum"
        credencial_sso_do_usuario.atualizado_em = agora
    else:
        sessao_db.add(
            Credencial(
                tenant_id=tenant_id,
                usuario_id=usuario.id,
                tipo="sso",
                provedor_sso=PROVEDOR,
                identificador_externo=identificador_externo,
                hash=hash_valor,
                algoritmo="nenhum",
                ativo=True,
            )
        )
    await sessao_db.flush()
    return usuario


async def emitir_sessao(
    sessao_db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    usuario: Usuario,
    ip: str | None,
    user_agent: str | None,
    agora: _dt.datetime,
) -> ResultadoLoginSso:
    """`PONTO-AUTH-010` quando o usuario resolvido esta bloqueado ou
    inativo -- mesma regra do login por senha."""
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
