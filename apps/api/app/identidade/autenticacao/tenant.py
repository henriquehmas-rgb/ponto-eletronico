"""Resolucao de tenant para os fluxos de autenticacao.

**Por que isto existe aqui e nao so em `TenantMiddleware`.** O middleware
(ownership do agente A2, T2 do PCF) publica o IDENTIFICADOR bruto do tenant
(slug ou UUID) em `app.core.contexto`, sem consultar o banco. Os fluxos desta
fase (`login`, `refresh`, `token` OAuth, recuperacao de senha) precisam do
UUID real ANTES de abrir a sessao de banco com RLS -- e a resolucao pode ter
de acontecer aqui de qualquer forma (T2 pode nao ter rodado ainda, ou pode
rodar depois e so reafirmar o que aqui ja foi validado; a funcao e idempotente
nos dois casos). Usa exclusivamente a funcao de contrato
`fn_resolve_tenant(TEXT)` (`SECURITY DEFINER`, so quatro colunas) para o caso
de slug; para UUID, a existencia e o status sao confirmados por uma consulta
comum, com RLS ja ativa (o `SET LOCAL app.tenant_id` e feito com o proprio
candidato: se o UUID nao existir, a policy devolve zero linhas, nunca vaza
outro tenant).
"""

from __future__ import annotations

import contextlib
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.erros import ErroDeAplicacao
from app.db.sessao import aplicar_tenant, fabrica_de_sessoes


@dataclass(frozen=True, slots=True)
class TenantResolvido:
    id: uuid.UUID
    slug: str
    status: str


async def resolver_tenant_para_autenticacao(
    sessao_db: AsyncSession, identificador: str
) -> TenantResolvido:
    """Resolve `identificador` (slug ou UUID) e publica `app.tenant_id` na transacao.

    Levanta `PONTO-VAL-011` (cabecalho ausente) quando `identificador` e vazio,
    `PONTO-TEN-001` quando nao existe tenant com aquele slug/id, e
    `PONTO-TEN-003` quando o tenant existe mas esta suspenso ou cancelado.
    """
    identificador = (identificador or "").strip()
    if not identificador:
        raise ErroDeAplicacao("PONTO-VAL-011", detalhe="X-Tenant")

    try:
        candidato_uuid = uuid.UUID(identificador)
    except ValueError:
        candidato_uuid = None

    if candidato_uuid is not None:
        await aplicar_tenant(sessao_db, str(candidato_uuid))
        linha = (
            (
                await sessao_db.execute(
                    sa.text("SELECT id, slug, status FROM tenants WHERE id = :id"),
                    {"id": str(candidato_uuid)},
                )
            )
            .mappings()
            .one_or_none()
        )
    else:
        linha = (
            (
                await sessao_db.execute(
                    sa.text("SELECT id, slug, status FROM fn_resolve_tenant(:slug)"),
                    {"slug": identificador},
                )
            )
            .mappings()
            .one_or_none()
        )
        if linha is not None:
            await aplicar_tenant(sessao_db, str(linha["id"]))

    if linha is None:
        raise ErroDeAplicacao("PONTO-TEN-001")

    resolvido = TenantResolvido(id=linha["id"], slug=linha["slug"], status=linha["status"])
    if resolvido.status in ("suspenso", "cancelado"):
        raise ErroDeAplicacao("PONTO-TEN-003")
    return resolvido


async def verificar_tenant_do_cabecalho(
    sessao_db: AsyncSession, *, x_tenant: str | None, tenant_esperado: uuid.UUID
) -> None:
    """`PONTO-TEN-002` quando `X-Tenant` aponta para um tenant diferente do token.

    Cabecalho ausente nao e erro aqui: acesso por subdominio nao o envia (a
    comparacao com o host e responsabilidade do `TenantMiddleware`, T2/A2).
    """
    if not x_tenant:
        return
    resolvido = await resolver_tenant_para_autenticacao(sessao_db, x_tenant)
    if resolvido.id != tenant_esperado:
        raise ErroDeAplicacao("PONTO-TEN-002")
    # Garante que a sessao volte a publicar o tenant do TOKEN (a resolucao
    # acima e idempotente porque os dois IDs sao iguais, mas o `SET LOCAL` e
    # reaplicado explicitamente por clareza e para blindar contra qualquer
    # mudanca futura em `resolver_tenant_para_autenticacao`).
    await aplicar_tenant(sessao_db, str(tenant_esperado))


@contextlib.asynccontextmanager
async def sessao_com_tenant_resolvido(
    identificador: str,
) -> AsyncIterator[tuple[AsyncSession, TenantResolvido]]:
    """Abre uma sessao propria (fora do `SessaoDb` padrao) e resolve o tenant nela.

    Uso deliberado, e nao `app.db.sessao.obter_sessao`: esta so aplica
    `set_config('app.tenant_id', tenant, true)` com o que ja estiver em
    `app.core.contexto` -- que pode ainda ser um SLUG (a resolucao de T2 e do
    agente A2). Aplicar um slug direto quebraria a policy de RLS no primeiro
    `SELECT` (`... ::uuid` falha em texto que nao e UUID). As rotas publicas
    desta fase (login, refresh, token OAuth, recuperacao de senha) usam este
    gerenciador de contexto para resolver o identificador ANTES de qualquer
    consulta de dominio.
    """
    fabrica = fabrica_de_sessoes()
    async with fabrica() as sessao_db:
        try:
            resolvido = await resolver_tenant_para_autenticacao(sessao_db, identificador)
            yield sessao_db, resolvido
        except ErroDeAplicacao:
            # Erro de NEGOCIO (ex.: senha errada): os efeitos colaterais ja
            # gravados nesta transacao (como o incremento de
            # `tentativas_falhas` do bloqueio progressivo) sao intencionais e
            # precisam sobreviver, mesmo que a resposta HTTP seja um erro.
            # Descarta-los aqui apagaria o proprio bloqueio que a falha
            # deveria registrar.
            await sessao_db.commit()
            raise
        except Exception:
            # Erro INESPERADO (bug, falha de infraestrutura): desfaz tudo.
            await sessao_db.rollback()
            raise
        else:
            await sessao_db.commit()


@contextlib.asynccontextmanager
async def sessao_com_tenant_id(tenant_id: uuid.UUID) -> AsyncIterator[AsyncSession]:
    """Abre uma sessao propria e publica um `tenant_id` JA CONHECIDO (do JWT).

    Usada pelas rotas autenticadas (`bearerAuth`): o tenant vem da claim
    `tenant` do access token, que e sempre um UUID valido (emitido por esta
    mesma fase), entao nao ha ambiguidade slug/uuid a resolver.
    """
    fabrica = fabrica_de_sessoes()
    async with fabrica() as sessao_db:
        try:
            await aplicar_tenant(sessao_db, str(tenant_id))
            yield sessao_db
        except ErroDeAplicacao:
            # Ver comentario equivalente em `sessao_com_tenant_resolvido`.
            await sessao_db.commit()
            raise
        except Exception:
            await sessao_db.rollback()
            raise
        else:
            await sessao_db.commit()
