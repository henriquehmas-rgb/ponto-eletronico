"""Orquestracao de `POST /v1/auth/login`, `mfa/verificar`, `logout`,
`reautenticar`, `senha/recuperar` e `senha/redefinir`.

Este modulo e o unico lugar onde as pecas de `autenticacao/`, `tokens/` e
`mfa/` se encontram. Os routers (`app/routers/auth.py`) so traduzem
HTTP <-> estes dataclasses; nenhuma regra de negocio mora no router.
"""

from __future__ import annotations

import datetime as _dt
import uuid
from dataclasses import dataclass, field

import sqlalchemy as sa
from ponto_contracts import Credencial, MfaDispositivo, Sessao, Usuario
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.erros import ErroDeAplicacao
from app.identidade.autenticacao import bloqueio
from app.identidade.autenticacao.senha import gerar_hash, verificar_hash
from app.identidade.mfa import backup_codes, recuperacao
from app.identidade.mfa import totp as totp_mod
from app.identidade.tokens import jwt as jwt_mod
from app.identidade.tokens import refresh as refresh_mod
from app.identidade.tokens import sessao as sessao_mod

#: Hash Argon2id de um segredo fixo, usado so para gastar tempo de CPU
#: equivalente ao de uma verificacao real quando o usuario ou a credencial nao
#: existem -- e o que torna a resposta de "usuario inexistente" indistinguivel
#: de "senha errada" tambem no tempo de resposta, nao so no corpo/status.
_HASH_FANTASMA = gerar_hash("um-segredo-que-nunca-e-comparado-de-verdade")

_TIPOS_MFA_SUPORTADOS = ("totp", "codigos_backup")


@dataclass(frozen=True, slots=True)
class ResultadoLogin:
    mfa_requerido: bool
    usuario: Usuario | None = None
    desafio_id: uuid.UUID | None = None
    metodos_mfa: list[str] = field(default_factory=list)
    access_token: str | None = None
    refresh_token: str | None = None
    expires_in: int | None = None
    sessao_id: uuid.UUID | None = None


async def _usuario_e_credencial_senha(
    sessao_db: AsyncSession, *, tenant_id: uuid.UUID, email: str
) -> tuple[Usuario, Credencial] | None:
    usuario = (
        await sessao_db.execute(
            sa.select(Usuario).where(
                Usuario.tenant_id == tenant_id,
                sa.func.lower(Usuario.email) == email.strip().lower(),
                Usuario.excluido_em.is_(None),
            )
        )
    ).scalar_one_or_none()
    if usuario is None:
        return None
    credencial = (
        await sessao_db.execute(
            sa.select(Credencial).where(
                Credencial.tenant_id == tenant_id,
                Credencial.usuario_id == usuario.id,
                Credencial.tipo == "senha",
                Credencial.ativo.is_(True),
            )
        )
    ).scalar_one_or_none()
    if credencial is None:
        return None
    return usuario, credencial


async def _dispositivos_mfa_confirmados(
    sessao_db: AsyncSession, *, tenant_id: uuid.UUID, usuario_id: uuid.UUID
) -> list[MfaDispositivo]:
    dispositivos = (
        (
            await sessao_db.execute(
                sa.select(MfaDispositivo).where(
                    MfaDispositivo.tenant_id == tenant_id,
                    MfaDispositivo.usuario_id == usuario_id,
                    MfaDispositivo.ativo.is_(True),
                    MfaDispositivo.confirmado_em.isnot(None),
                    MfaDispositivo.tipo.in_(_TIPOS_MFA_SUPORTADOS),
                )
            )
        )
        .scalars()
        .all()
    )
    return list(dispositivos)


def _mfa_e_exigido(usuario: Usuario, dispositivos: list[MfaDispositivo]) -> bool:
    return bool(usuario.mfa_obrigatorio) or bool(dispositivos)


async def _registrar_falha_senha(
    sessao_db: AsyncSession, *, credencial: Credencial, agora: _dt.datetime
) -> None:
    credencial.tentativas_falhas += 1
    credencial.bloqueado_ate = bloqueio.calcular_bloqueado_ate(credencial.tentativas_falhas, agora)
    await sessao_db.flush()


def _levantar_bloqueio(credencial: Credencial, agora: _dt.datetime) -> None:
    if bloqueio.bloqueado(credencial.bloqueado_ate, agora):
        restante_s = max(
            1,
            int((credencial.bloqueado_ate - agora).total_seconds()),  # type: ignore[operator]
        )
        raise ErroDeAplicacao("PONTO-AUTH-009", tentar_novamente_em=restante_s)


async def login(
    sessao_db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    email: str,
    senha: str,
    canal: str = "web",
    ip: str | None = None,
    user_agent: str | None = None,
    fingerprint: str | None = None,
    dispositivo_identificador: str | None = None,
    agora: _dt.datetime | None = None,
) -> ResultadoLogin:
    """`POST /v1/auth/login`.

    `PONTO-AUTH-001` -- usuario ou senha nao conferem. A resposta e
    DELIBERADAMENTE identica (mesmo corpo, mesmo status) para as duas causas,
    exigencia explicita do contrato contra enumeracao de contas.
    """
    agora = agora or _dt.datetime.now(_dt.UTC)
    encontrado = await _usuario_e_credencial_senha(sessao_db, tenant_id=tenant_id, email=email)
    if encontrado is None:
        verificar_hash(_HASH_FANTASMA, senha)  # gasta tempo de CPU equivalente
        raise ErroDeAplicacao("PONTO-AUTH-001")
    usuario, credencial = encontrado

    if usuario.status in ("bloqueado", "inativo"):
        raise ErroDeAplicacao("PONTO-AUTH-010")

    _levantar_bloqueio(credencial, agora)

    if not verificar_hash(credencial.hash, senha):
        await _registrar_falha_senha(sessao_db, credencial=credencial, agora=agora)
        raise ErroDeAplicacao("PONTO-AUTH-001")

    # Senha correta: reseta o contador de falhas.
    credencial.tentativas_falhas = 0
    credencial.bloqueado_ate = None
    await sessao_db.flush()

    dispositivos_mfa = await _dispositivos_mfa_confirmados(
        sessao_db, tenant_id=tenant_id, usuario_id=usuario.id
    )

    if _mfa_e_exigido(usuario, dispositivos_mfa):
        pendente = await sessao_mod.criar_sessao(
            sessao_db,
            tenant_id=tenant_id,
            usuario_id=usuario.id,
            canal=canal,
            ip=ip,
            user_agent=user_agent,
            fingerprint=fingerprint,
            pendente_mfa=True,
            agora=agora,
        )
        metodos = sorted({d.tipo for d in dispositivos_mfa})
        return ResultadoLogin(
            mfa_requerido=True,
            desafio_id=pendente.id,
            metodos_mfa=metodos,
        )

    usuario.ultimo_acesso_em = agora
    usuario.ultimo_acesso_ip = ip
    nova_sessao = await sessao_mod.criar_sessao(
        sessao_db,
        tenant_id=tenant_id,
        usuario_id=usuario.id,
        canal=canal,
        ip=ip,
        user_agent=user_agent,
        fingerprint=fingerprint,
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
    return ResultadoLogin(
        mfa_requerido=False,
        usuario=usuario,
        access_token=access_token,
        refresh_token=emitido.token,
        expires_in=expires_in,
        sessao_id=nova_sessao.id,
    )


async def _verificar_totp(
    sessao_db: AsyncSession, dispositivo: MfaDispositivo, codigo: str, agora: _dt.datetime
) -> bool:
    from app.identidade.mfa.cifra import decifrar

    if (
        dispositivo.segredo_cifrado is None
        or dispositivo.iv is None
        or dispositivo.chave_id is None
    ):
        # Invariante do cadastro: um dispositivo TOTP confirmado sempre tem os
        # tres campos preenchidos. Chegar aqui sem eles e defeito de dado, nao
        # falha do usuario.
        return False
    segredo_base32 = decifrar(
        dispositivo.segredo_cifrado, dispositivo.iv, chave_id=dispositivo.chave_id
    ).decode("ascii")
    passo = totp_mod.verificar_codigo(
        segredo_base32, codigo, ultimo_passo_aceito=dispositivo.contador, agora=agora
    )
    if passo is None:
        return False
    dispositivo.contador = passo
    dispositivo.ultimo_uso_em = agora
    await sessao_db.flush()
    return True


async def _verificar_backup(
    sessao_db: AsyncSession, dispositivo: MfaDispositivo, codigo: str, agora: _dt.datetime
) -> bool:
    if (
        dispositivo.segredo_cifrado is None
        or dispositivo.iv is None
        or dispositivo.chave_id is None
    ):
        return False
    resultado = backup_codes.consumir(
        dispositivo.segredo_cifrado, dispositivo.iv, dispositivo.chave_id, codigo
    )
    if not resultado.sucesso:
        return False
    dispositivo.segredo_cifrado = resultado.cifrado
    dispositivo.iv = resultado.iv
    dispositivo.ultimo_uso_em = agora
    await sessao_db.flush()
    return True


@dataclass(frozen=True, slots=True)
class ResultadoMfa:
    usuario: Usuario
    access_token: str
    refresh_token: str
    expires_in: int
    sessao_id: uuid.UUID


async def verificar_segundo_fator(
    sessao_db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    desafio_id: uuid.UUID,
    codigo: str,
    metodo: str | None,
    ip: str | None = None,
    user_agent: str | None = None,
    agora: _dt.datetime | None = None,
) -> ResultadoMfa:
    """`POST /v1/auth/mfa/verificar`.

    O `desafioId` do contrato E o `id` da sessao pendente criada em `login`
    (ver docstring de `app.identidade.tokens.sessao`): nao existe tabela
    dedicada a desafio de MFA no contrato congelado, e criar uma seria
    migration nova (proibida nesta fase). Reaproveitar `sessoes` evita as
    duas coisas.
    """
    agora = agora or _dt.datetime.now(_dt.UTC)
    pendente = (
        await sessao_db.execute(
            sa.select(Sessao).where(Sessao.tenant_id == tenant_id, Sessao.id == desafio_id)
        )
    ).scalar_one_or_none()
    if (
        pendente is None
        or pendente.mfa_validado_em is not None
        or pendente.encerrada_em is not None
        or pendente.expira_em <= agora
    ):
        raise ErroDeAplicacao("PONTO-AUTH-008")

    usuario = (
        await sessao_db.execute(sa.select(Usuario).where(Usuario.id == pendente.usuario_id))
    ).scalar_one_or_none()
    if usuario is None:
        raise ErroDeAplicacao("PONTO-AUTH-008")

    dispositivos = await _dispositivos_mfa_confirmados(
        sessao_db, tenant_id=tenant_id, usuario_id=usuario.id
    )
    por_tipo = {d.tipo: d for d in dispositivos}

    candidatos: list[MfaDispositivo] = []
    if metodo:
        if metodo in por_tipo:
            candidatos = [por_tipo[metodo]]
    else:
        candidatos = [d for d in (por_tipo.get("totp"), por_tipo.get("codigos_backup")) if d]

    sucesso = False
    for dispositivo in candidatos:
        if dispositivo.tipo == "totp":
            sucesso = await _verificar_totp(sessao_db, dispositivo, codigo, agora)
        elif dispositivo.tipo == "codigos_backup":
            sucesso = await _verificar_backup(sessao_db, dispositivo, codigo, agora)
        if sucesso:
            break

    if not sucesso:
        # Reusa o mesmo bloqueio progressivo da senha: o contrato lista
        # PONTO-AUTH-009 entre os erros possiveis desta operacao, e um MFA
        # sujeito a forca bruta ilimitada anularia a protecao da senha.
        credencial = (
            await sessao_db.execute(
                sa.select(Credencial).where(
                    Credencial.tenant_id == tenant_id,
                    Credencial.usuario_id == usuario.id,
                    Credencial.tipo == "senha",
                    Credencial.ativo.is_(True),
                )
            )
        ).scalar_one_or_none()
        if credencial is not None:
            _levantar_bloqueio(credencial, agora)
            await _registrar_falha_senha(sessao_db, credencial=credencial, agora=agora)
        raise ErroDeAplicacao("PONTO-AUTH-008")

    await sessao_mod.estender_apos_mfa(sessao_db, sessao=pendente, agora=agora)
    usuario.ultimo_acesso_em = agora
    usuario.ultimo_acesso_ip = ip
    emitido = await refresh_mod.emitir(
        sessao_db,
        tenant_id=tenant_id,
        usuario_id=usuario.id,
        sessao_id=pendente.id,
        ip=ip,
        user_agent=user_agent,
        agora=agora,
    )
    access_token, expires_in = jwt_mod.emitir_access_token(
        usuario_id=usuario.id,
        tenant_id=tenant_id,
        email=usuario.email,
        sessao_id=pendente.id,
        agora=agora,
    )
    return ResultadoMfa(
        usuario=usuario,
        access_token=access_token,
        refresh_token=emitido.token,
        expires_in=expires_in,
        sessao_id=pendente.id,
    )


async def renovar_sessao(
    sessao_db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    refresh_token_bruto: str,
    ip: str | None = None,
    user_agent: str | None = None,
    agora: _dt.datetime | None = None,
) -> tuple[Usuario, str, str, int, uuid.UUID]:
    """`POST /v1/auth/refresh`. Devolve `(usuario, access, refresh, expires_in, sessao_id)`."""
    novo = await refresh_mod.rotacionar(
        sessao_db,
        tenant_id=tenant_id,
        token_bruto=refresh_token_bruto,
        ip=ip,
        user_agent=user_agent,
        agora=agora,
    )
    usuario = (
        await sessao_db.execute(sa.select(Usuario).where(Usuario.id == novo.registro.usuario_id))
    ).scalar_one()
    access_token, expires_in = jwt_mod.emitir_access_token(
        usuario_id=usuario.id,
        tenant_id=tenant_id,
        email=usuario.email,
        sessao_id=novo.registro.sessao_id,
        agora=agora,
    )
    return usuario, access_token, novo.token, expires_in, novo.registro.sessao_id


async def logout(
    sessao_db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    usuario_id: uuid.UUID,
    sessao_id: uuid.UUID,
    todas_as_sessoes: bool,
    agora: _dt.datetime | None = None,
) -> None:
    agora = agora or _dt.datetime.now(_dt.UTC)
    if todas_as_sessoes:
        await sessao_mod.encerrar_todas_as_sessoes_do_usuario(
            sessao_db, tenant_id=tenant_id, usuario_id=usuario_id, motivo="logout", agora=agora
        )
        return
    await sessao_mod.encerrar_sessao(
        sessao_db, tenant_id=tenant_id, sessao_id=sessao_id, motivo="logout", agora=agora
    )
    await sessao_mod.revogar_tokens_da_sessao(
        sessao_db, tenant_id=tenant_id, sessao_id=sessao_id, motivo="logout", agora=agora
    )


@dataclass(frozen=True, slots=True)
class ResultadoReautenticacao:
    reautenticado_em: _dt.datetime
    valido_ate: _dt.datetime
    token_operacao: str


async def reautenticar(
    sessao_db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    usuario_id: uuid.UUID,
    sessao_id: uuid.UUID,
    senha: str,
    codigo_mfa: str | None,
    agora: _dt.datetime | None = None,
) -> ResultadoReautenticacao:
    agora = agora or _dt.datetime.now(_dt.UTC)
    usuario = (
        await sessao_db.execute(sa.select(Usuario).where(Usuario.id == usuario_id))
    ).scalar_one_or_none()
    if usuario is None or usuario.status in ("bloqueado", "inativo"):
        raise ErroDeAplicacao("PONTO-AUTH-010" if usuario is not None else "PONTO-AUTH-001")

    credencial = (
        await sessao_db.execute(
            sa.select(Credencial).where(
                Credencial.tenant_id == tenant_id,
                Credencial.usuario_id == usuario_id,
                Credencial.tipo == "senha",
                Credencial.ativo.is_(True),
            )
        )
    ).scalar_one_or_none()
    if credencial is None:
        verificar_hash(_HASH_FANTASMA, senha)
        raise ErroDeAplicacao("PONTO-AUTH-001")

    _levantar_bloqueio(credencial, agora)
    if not verificar_hash(credencial.hash, senha):
        await _registrar_falha_senha(sessao_db, credencial=credencial, agora=agora)
        raise ErroDeAplicacao("PONTO-AUTH-001")
    credencial.tentativas_falhas = 0
    credencial.bloqueado_ate = None

    dispositivos = await _dispositivos_mfa_confirmados(
        sessao_db, tenant_id=tenant_id, usuario_id=usuario_id
    )
    if _mfa_e_exigido(usuario, dispositivos):
        por_tipo = {d.tipo: d for d in dispositivos}
        sucesso = False
        if codigo_mfa:
            for tipo in ("totp", "codigos_backup"):
                dispositivo = por_tipo.get(tipo)
                if dispositivo is None:
                    continue
                if tipo == "totp":
                    sucesso = await _verificar_totp(sessao_db, dispositivo, codigo_mfa, agora)
                else:
                    sucesso = await _verificar_backup(sessao_db, dispositivo, codigo_mfa, agora)
                if sucesso:
                    break
        if not sucesso:
            raise ErroDeAplicacao("PONTO-AUTH-008")

    await sessao_db.execute(
        sa.update(Sessao)
        .where(Sessao.tenant_id == tenant_id, Sessao.id == sessao_id)
        .values(reautenticado_em=agora)
    )
    token_operacao, valido_ate = jwt_mod.emitir_token_operacao(
        usuario_id=usuario_id, tenant_id=tenant_id, sessao_id=sessao_id, agora=agora
    )
    return ResultadoReautenticacao(
        reautenticado_em=agora, valido_ate=valido_ate, token_operacao=token_operacao
    )


@dataclass(frozen=True, slots=True)
class RecuperacaoSolicitada:
    """Uso interno/teste: o roteador NUNCA expoe estes campos (resposta e sempre 202 vazio)."""

    token_bruto: str | None


async def solicitar_recuperacao_senha(
    sessao_db: AsyncSession,
    *,
    tenant_id: uuid.UUID | None,
    email: str,
    agora: _dt.datetime | None = None,
) -> RecuperacaoSolicitada:
    agora = agora or _dt.datetime.now(_dt.UTC)
    if tenant_id is None:
        return RecuperacaoSolicitada(token_bruto=None)
    usuario = (
        await sessao_db.execute(
            sa.select(Usuario).where(
                Usuario.tenant_id == tenant_id,
                sa.func.lower(Usuario.email) == email.strip().lower(),
                Usuario.excluido_em.is_(None),
                Usuario.status != "inativo",
            )
        )
    ).scalar_one_or_none()
    if usuario is None:
        return RecuperacaoSolicitada(token_bruto=None)

    # No maximo uma credencial de recuperacao ATIVA por usuario
    # (uq_credenciais_ativa): desativa a anterior antes de criar a nova.
    await sessao_db.execute(
        sa.update(Credencial)
        .where(
            Credencial.tenant_id == tenant_id,
            Credencial.usuario_id == usuario.id,
            Credencial.tipo == "recuperacao",
            Credencial.ativo.is_(True),
        )
        .values(ativo=False)
    )
    gerado = recuperacao.gerar(agora)
    sessao_db.add(
        Credencial(
            tenant_id=tenant_id,
            usuario_id=usuario.id,
            tipo="recuperacao",
            hash=gerado.hash,
            algoritmo=recuperacao.ALGORITMO,
            expira_em=gerado.expira_em,
            ativo=True,
        )
    )
    await sessao_db.flush()
    return RecuperacaoSolicitada(token_bruto=gerado.token)


async def redefinir_senha(
    sessao_db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    token_bruto: str,
    nova_senha: str,
    agora: _dt.datetime | None = None,
) -> None:
    agora = agora or _dt.datetime.now(_dt.UTC)
    hash_apresentado = recuperacao.hash_token(token_bruto)
    credencial_recuperacao = (
        await sessao_db.execute(
            sa.select(Credencial).where(
                Credencial.tenant_id == tenant_id,
                Credencial.tipo == "recuperacao",
                Credencial.ativo.is_(True),
                Credencial.hash == hash_apresentado,
            )
        )
    ).scalar_one_or_none()
    if credencial_recuperacao is None or (
        credencial_recuperacao.expira_em is not None and credencial_recuperacao.expira_em <= agora
    ):
        raise ErroDeAplicacao("PONTO-AUTH-004")

    usuario_id = credencial_recuperacao.usuario_id
    credencial_recuperacao.ativo = False

    await sessao_db.execute(
        sa.update(Credencial)
        .where(
            Credencial.tenant_id == tenant_id,
            Credencial.usuario_id == usuario_id,
            Credencial.tipo == "senha",
            Credencial.ativo.is_(True),
        )
        .values(ativo=False)
    )
    sessao_db.add(
        Credencial(
            tenant_id=tenant_id,
            usuario_id=usuario_id,
            tipo="senha",
            hash=gerar_hash(nova_senha),
            algoritmo="argon2id",
            trocar_no_proximo_acesso=False,
            ativo=True,
            ultima_troca_em=agora,
        )
    )
    await sessao_mod.encerrar_todas_as_sessoes_do_usuario(
        sessao_db,
        tenant_id=tenant_id,
        usuario_id=usuario_id,
        motivo="troca_senha",
        agora=agora,
    )
    await sessao_db.flush()
