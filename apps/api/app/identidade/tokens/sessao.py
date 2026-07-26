"""Ciclo de vida de `sessoes`: criacao, encerramento e revogacao em massa.

Uma sessao agrupa uma familia de refresh tokens (ver `refresh.py`) e e a
unidade de revogacao: encerrar a sessao e revogar toda a familia sao a mesma
operacao logica, feitas juntas em `encerrar_sessao_e_familia`.
"""

from __future__ import annotations

import datetime as _dt
import uuid

import sqlalchemy as sa
from ponto_contracts import RefreshToken, Sessao
from sqlalchemy.ext.asyncio import AsyncSession

#: Vida maxima de uma sessao (janela de expiracao absoluta). O refresh token
#: tem vida propria mais curta (ver `refresh.VIDA_REFRESH_TOKEN`); a sessao e o
#: teto: nenhuma rotacao estende a sessao para alem deste prazo.
VIDA_SESSAO = _dt.timedelta(days=30)

#: Janela reduzida para a sessao pendente de segundo fator (entre `login` com
#: `mfaRequerido=true` e `POST /v1/auth/mfa/verificar`). Uma sessao que fica
#: pendente por mais tempo que isso expira sem nunca ter emitido token.
VIDA_SESSAO_PENDENTE_MFA = _dt.timedelta(minutes=10)

MOTIVOS_ENCERRAMENTO_VALIDOS = frozenset(
    {
        "logout",
        "expiracao",
        "inatividade",
        "revogacao_admin",
        "troca_senha",
        "reuso_token",
        "dispositivo_revogado",
    }
)


async def criar_sessao(
    sessao_db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    usuario_id: uuid.UUID,
    canal: str,
    ip: str | None = None,
    user_agent: str | None = None,
    fingerprint: str | None = None,
    dispositivo_id: uuid.UUID | None = None,
    pendente_mfa: bool = False,
    agora: _dt.datetime | None = None,
) -> Sessao:
    agora = agora or _dt.datetime.now(_dt.UTC)
    vida = VIDA_SESSAO_PENDENTE_MFA if pendente_mfa else VIDA_SESSAO
    registro = Sessao(
        tenant_id=tenant_id,
        usuario_id=usuario_id,
        canal=canal,
        ip=ip,
        user_agent=user_agent,
        fingerprint=fingerprint,
        dispositivo_id=dispositivo_id,
        iniciada_em=agora,
        ultima_atividade_em=agora,
        expira_em=agora + vida,
    )
    sessao_db.add(registro)
    await sessao_db.flush()
    return registro


async def estender_apos_mfa(
    sessao_db: AsyncSession, *, sessao: Sessao, agora: _dt.datetime | None = None
) -> None:
    """Troca a janela curta (pendente de MFA) pela vida normal da sessao."""
    agora = agora or _dt.datetime.now(_dt.UTC)
    sessao.expira_em = agora + VIDA_SESSAO
    sessao.mfa_validado_em = agora
    await sessao_db.flush()


async def obter_sessao(
    sessao_db: AsyncSession, *, tenant_id: uuid.UUID, sessao_id: uuid.UUID
) -> Sessao | None:
    return (
        await sessao_db.execute(
            sa.select(Sessao).where(Sessao.tenant_id == tenant_id, Sessao.id == sessao_id)
        )
    ).scalar_one_or_none()


async def encerrar_sessao(
    sessao_db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    sessao_id: uuid.UUID,
    motivo: str,
    agora: _dt.datetime | None = None,
) -> None:
    if motivo not in MOTIVOS_ENCERRAMENTO_VALIDOS:
        raise ValueError(f"motivo de encerramento invalido: {motivo!r}")
    agora = agora or _dt.datetime.now(_dt.UTC)
    await sessao_db.execute(
        sa.update(Sessao)
        .where(
            Sessao.tenant_id == tenant_id,
            Sessao.id == sessao_id,
            Sessao.encerrada_em.is_(None),
        )
        .values(encerrada_em=agora, motivo_encerramento=motivo)
    )


async def revogar_familia(
    sessao_db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    familia_id: uuid.UUID,
    motivo: str,
    agora: _dt.datetime | None = None,
) -> None:
    """Revoga todos os refresh tokens nao revogados de uma familia."""
    agora = agora or _dt.datetime.now(_dt.UTC)
    await sessao_db.execute(
        sa.update(RefreshToken)
        .where(
            RefreshToken.tenant_id == tenant_id,
            RefreshToken.familia_id == familia_id,
            RefreshToken.revogado_em.is_(None),
        )
        .values(revogado_em=agora, motivo_revogacao=motivo)
    )


async def encerrar_sessao_e_familia(
    sessao_db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    sessao_id: uuid.UUID,
    familia_id: uuid.UUID,
    motivo_sessao: str,
    motivo_familia: str,
    agora: _dt.datetime | None = None,
) -> None:
    agora = agora or _dt.datetime.now(_dt.UTC)
    await encerrar_sessao(
        sessao_db, tenant_id=tenant_id, sessao_id=sessao_id, motivo=motivo_sessao, agora=agora
    )
    await revogar_familia(
        sessao_db, tenant_id=tenant_id, familia_id=familia_id, motivo=motivo_familia, agora=agora
    )


async def revogar_tokens_da_sessao(
    sessao_db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    sessao_id: uuid.UUID,
    motivo: str,
    agora: _dt.datetime | None = None,
) -> None:
    """Revoga todo refresh token ligado a uma sessao (por `sessao_id`, nao por familia).

    Usado por `logout`: uma sessao agrupa, na pratica, uma unica familia, mas
    filtrar por `sessao_id` dispensa localizar `familia_id` primeiro.
    """
    agora = agora or _dt.datetime.now(_dt.UTC)
    await sessao_db.execute(
        sa.update(RefreshToken)
        .where(
            RefreshToken.tenant_id == tenant_id,
            RefreshToken.sessao_id == sessao_id,
            RefreshToken.revogado_em.is_(None),
        )
        .values(revogado_em=agora, motivo_revogacao=motivo)
    )


async def encerrar_todas_as_sessoes_do_usuario(
    sessao_db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    usuario_id: uuid.UUID,
    motivo: str,
    agora: _dt.datetime | None = None,
) -> None:
    """Usado por redefinicao de senha e por `logout` com `todasAsSessoes=true`."""
    agora = agora or _dt.datetime.now(_dt.UTC)
    sessoes_ativas = (
        (
            await sessao_db.execute(
                sa.select(Sessao.id).where(
                    Sessao.tenant_id == tenant_id,
                    Sessao.usuario_id == usuario_id,
                    Sessao.encerrada_em.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )
    if not sessoes_ativas:
        return
    await sessao_db.execute(
        sa.update(Sessao)
        .where(Sessao.tenant_id == tenant_id, Sessao.id.in_(sessoes_ativas))
        .values(encerrada_em=agora, motivo_encerramento=motivo)
    )
    await sessao_db.execute(
        sa.update(RefreshToken)
        .where(
            RefreshToken.tenant_id == tenant_id,
            RefreshToken.usuario_id == usuario_id,
            RefreshToken.revogado_em.is_(None),
        )
        .values(revogado_em=agora, motivo_revogacao=motivo)
    )
