"""Refresh token rotativo com deteccao de reuso.

O ponto mais facil de errar da fase, nas palavras do PCF: **cada uso do
refresh emite um token novo e marca o anterior como usado**; se um token com
`usado_em` preenchido for apresentado de novo, isso caracteriza reuso e a
resposta correta e invalidar a FAMILIA INTEIRA (`refresh_tokens.familia_id`),
nunca so o token reapresentado -- invalidar so o apresentado deixaria um
eventual atacante com o token ainda valido e derrubaria a vitima.

O valor em claro do refresh token so existe no cliente: o banco guarda apenas
o SHA-256 (`refresh_tokens.token_hash`, tipo `dom_sha256`).
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import secrets
import uuid
from dataclasses import dataclass

import sqlalchemy as sa
from ponto_contracts import RefreshToken, Sessao
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.erros import ErroDeAplicacao
from app.identidade.tokens import sessao as sessao_mod

#: 30 dias, mesma ordem de grandeza da sessao (a sessao e o teto absoluto).
VIDA_REFRESH_TOKEN = _dt.timedelta(days=30)

_TAMANHO_TOKEN_BYTES = 48


def _gerar_token_bruto() -> str:
    return secrets.token_urlsafe(_TAMANHO_TOKEN_BYTES)


def _hash(token_bruto: str) -> str:
    return hashlib.sha256(token_bruto.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class RefreshEmitido:
    token: str
    registro: RefreshToken


async def emitir(
    sessao_db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    usuario_id: uuid.UUID,
    sessao_id: uuid.UUID,
    familia_id: uuid.UUID | None = None,
    antecessor_id: uuid.UUID | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
    agora: _dt.datetime | None = None,
) -> RefreshEmitido:
    """Emite um novo refresh token. Sem `familia_id`, inicia uma familia nova (login)."""
    agora = agora or _dt.datetime.now(_dt.UTC)
    bruto = _gerar_token_bruto()
    registro = RefreshToken(
        tenant_id=tenant_id,
        usuario_id=usuario_id,
        sessao_id=sessao_id,
        familia_id=familia_id or uuid.uuid4(),
        antecessor_id=antecessor_id,
        token_hash=_hash(bruto),
        emitido_em=agora,
        expira_em=agora + VIDA_REFRESH_TOKEN,
        ip=ip,
        user_agent=user_agent,
    )
    sessao_db.add(registro)
    await sessao_db.flush()
    return RefreshEmitido(token=bruto, registro=registro)


async def rotacionar(
    sessao_db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    token_bruto: str,
    ip: str | None = None,
    user_agent: str | None = None,
    agora: _dt.datetime | None = None,
) -> RefreshEmitido:
    """Consome `token_bruto` e emite o proximo da cadeia.

    Levanta:
    * `PONTO-AUTH-006` -- token desconhecido, ja revogado ou sessao encerrada
      (do ponto de vista do cliente e indistinguivel de "sessao encerrada").
    * `PONTO-AUTH-003` -- token valido mas expirado.
    * `PONTO-AUTH-005` -- reuso detectado: a familia inteira e revogada e a
      sessao encerrada com `motivo_encerramento = 'reuso_token'` ANTES da
      excecao ser levantada, para que o efeito de seguranca aconteca mesmo que
      o chamador ignore a excecao.
    """
    agora = agora or _dt.datetime.now(_dt.UTC)
    hash_apresentado = _hash(token_bruto)

    atual = (
        await sessao_db.execute(
            sa.select(RefreshToken).where(
                RefreshToken.tenant_id == tenant_id,
                RefreshToken.token_hash == hash_apresentado,
            )
        )
    ).scalar_one_or_none()
    if atual is None:
        raise ErroDeAplicacao("PONTO-AUTH-006")

    if atual.usado_em is not None:
        # Reuso: um token que ja foi trocado por outro esta sendo reapresentado.
        # Checado ANTES de `revogado_em` de proposito -- reuso e o que este
        # ramo existe para detectar, e nao pode ser mascarado por uma
        # revogacao concorrente (ex.: um segundo reuso da MESMA familia, apos
        # o primeiro ja ter revogado tudo, ainda precisa contar como reuso,
        # nao como "sessao generica encerrada"). Revoga a FAMILIA inteira e
        # encerra a sessao -- nao so este token.
        await sessao_mod.encerrar_sessao_e_familia(
            sessao_db,
            tenant_id=tenant_id,
            sessao_id=atual.sessao_id,
            familia_id=atual.familia_id,
            motivo_sessao="reuso_token",
            motivo_familia="reuso_detectado",
            agora=agora,
        )
        raise ErroDeAplicacao("PONTO-AUTH-005")

    if atual.revogado_em is not None:
        raise ErroDeAplicacao("PONTO-AUTH-006")

    sessao_da_familia = (
        await sessao_db.execute(sa.select(Sessao).where(Sessao.id == atual.sessao_id))
    ).scalar_one_or_none()
    if sessao_da_familia is not None and sessao_da_familia.encerrada_em is not None:
        raise ErroDeAplicacao("PONTO-AUTH-006")

    if atual.expira_em <= agora:
        raise ErroDeAplicacao("PONTO-AUTH-003")

    # `usado_em` (nao `revogado_em`) e a marca de rotacao normal: `revogado_em`
    # fica reservado para revogacao de verdade (reuso, logout, admin, troca de
    # senha), para que a checagem de reuso acima nunca seja mascarada por uma
    # rotacao comum. `motivo_revogacao` acompanha `revogado_em` por definicao
    # de coluna (so faz sentido junto), entao fica de fora aqui tambem.
    atual.usado_em = agora

    novo = await emitir(
        sessao_db,
        tenant_id=tenant_id,
        usuario_id=atual.usuario_id,
        sessao_id=atual.sessao_id,
        familia_id=atual.familia_id,
        antecessor_id=atual.id,
        ip=ip,
        user_agent=user_agent,
        agora=agora,
    )
    return novo


async def revogar_por_valor(
    sessao_db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    token_bruto: str,
    motivo: str,
    agora: _dt.datetime | None = None,
) -> RefreshToken | None:
    """Usado por `logout`: revoga o token apresentado (e devolve o registro,
    para o chamador encerrar a sessao e/ou revogar a familia inteira)."""
    agora = agora or _dt.datetime.now(_dt.UTC)
    registro = (
        await sessao_db.execute(
            sa.select(RefreshToken).where(
                RefreshToken.tenant_id == tenant_id,
                RefreshToken.token_hash == _hash(token_bruto),
            )
        )
    ).scalar_one_or_none()
    if registro is None:
        return None
    if registro.revogado_em is None:
        registro.revogado_em = agora
        registro.motivo_revogacao = motivo
    return registro
