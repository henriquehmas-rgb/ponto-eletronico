"""Fixture do subarvore `webhooks` no lado worker da fase F13 (A3, T11/T12 --
`apps/worker/tests/f13/**` nao tem dono nomeado explicito no PCF; criado por
A3 como extensao natural do proprio ownership, mesma decisao ja documentada
por A8 em `apps/worker/tests/f13/importadores/afd_terceiro/conftest.py`).

Self-contained: usa `PONTO_TEST_DATABASE_URL` como conexao DIRETA ao banco
de teste exclusivo desta fase (`ponto_f13_a3`) -- mesmo padrao de A8 (mais
simples que reabrir role/migracao aqui: `apps/api/tests/f13/webhooks/
conftest.py`, rodado antes por este mesmo agente, ja garante banco criado e
migrado; este arquivo so conecta)."""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

_URL_PADRAO_LOCAL = "postgresql+asyncpg://ponto:ponto@localhost:5432/ponto_f13_a3"


def _url_banco_teste() -> str:
    return os.environ.get("PONTO_TEST_DATABASE_URL", _URL_PADRAO_LOCAL)


async def _reiniciar_engines_compartilhadas() -> None:
    """`app.db.sessao` (apps/api, importado como biblioteca por
    `worker.notificacoes_verificacao.listar_tenants_ativos_cross_tenant`,
    que `despachar_webhooks_pendentes_cross_tenant` chama) cacheia sua
    PROPRIA engine, independente de `worker.tarefas.integracoes`. Sem
    descarta-la tambem entre testes, o segundo teste de uma suite
    pytest-asyncio (loop novo por teste) reusa uma engine presa ao loop
    FECHADO do teste anterior -- `RuntimeError: Event loop is closed` na
    hora de devolver a conexao ao pool. Mesma causa raiz que `app/db/
    sessao.py::_engine_presa_a_outro_loop` documenta, so que aqui e um
    modulo diferente (`app.db.sessao`, nao `worker.tarefas.integracoes`)
    tambem precisando de reset."""
    from app.core.config import (
        obter_configuracao as obter_config_api,  # type: ignore[import-not-found]
    )
    from app.db.sessao import encerrar_engine  # type: ignore[import-not-found]

    obter_config_api.cache_clear()
    await encerrar_engine()


@pytest_asyncio.fixture(autouse=True)
async def _apontar_worker_config_para_banco_de_teste() -> AsyncIterator[None]:
    os.environ["DATABASE_URL"] = _url_banco_teste()
    from worker.config import obter_configuracao
    from worker.tarefas import integracoes as tarefas_integracoes

    obter_configuracao.cache_clear()
    await tarefas_integracoes.reiniciar_engine_para_testes()
    await _reiniciar_engines_compartilhadas()
    yield
    await tarefas_integracoes.reiniciar_engine_para_testes()
    await _reiniciar_engines_compartilhadas()


@pytest_asyncio.fixture
async def engine_worker_f13(request: object) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(_url_banco_teste(), pool_pre_ping=True)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def sessao_worker_f13(engine_worker_f13: AsyncEngine) -> AsyncIterator[AsyncSession]:
    fabrica = async_sessionmaker(engine_worker_f13, expire_on_commit=False, autoflush=False)
    async with fabrica() as sessao:
        yield sessao
        await sessao.rollback()


async def aplicar_tenant(sessao: AsyncSession, tenant_id: uuid.UUID) -> None:
    await sessao.execute(
        text("SELECT set_config('app.tenant_id', :tenant, true)"), {"tenant": str(tenant_id)}
    )


@dataclass(frozen=True, slots=True)
class ContextoWebhooksWorkerF13:
    tenant_id: uuid.UUID
    api_client_id: uuid.UUID
    webhook_id: uuid.UUID


@pytest_asyncio.fixture
async def contexto_webhooks_worker_f13(
    sessao_worker_f13: AsyncSession,
) -> ContextoWebhooksWorkerF13:
    """Semeia tenant + api_client + um webhook ATIVO assinando
    `colaborador.admitido` -- base minima para `despachar_webhooks_
    pendentes_cross_tenant` ter algo para reivindicar."""
    sufixo = uuid.uuid4().hex[:10]
    tenant_id = uuid.uuid4()
    await aplicar_tenant(sessao_worker_f13, tenant_id)

    await sessao_worker_f13.execute(
        text(
            "INSERT INTO tenants (id, slug, razao_social, nome_exibicao, status) "
            "VALUES (:id, :slug, :r, :n, 'ativo')"
        ),
        {
            "id": tenant_id,
            "slug": f"f13a3-worker-{sufixo}",
            "r": "Tenant worker F13 A3",
            "n": "Tenant worker F13 A3",
        },
    )

    api_client_id = uuid.uuid4()
    await sessao_worker_f13.execute(
        text(
            "INSERT INTO api_clients "
            "(id, tenant_id, nome, client_id, tipo, ambiente, escopos, "
            " rate_limit_por_minuto, status) "
            "VALUES (:id, :t, :nome, :cid, 'confidencial', 'sandbox', "
            "        ARRAY['webhooks:ler']::text[], 600, 'ativo')"
        ),
        {
            "id": api_client_id,
            "t": tenant_id,
            "nome": f"Cliente worker teste {sufixo}",
            "cid": f"cli_worker_{sufixo}",
        },
    )

    webhook_id = uuid.uuid4()
    await sessao_worker_f13.execute(
        text(
            "INSERT INTO webhooks "
            "(id, tenant_id, api_client_id, nome, url, eventos, segredo_hmac_cifrado, "
            " chave_id, max_tentativas, timeout_segundos, status) "
            "VALUES (:id, :t, :api, :nome, :url, "
            "        ARRAY['colaborador.admitido']::text[], :segredo, 'webh-v1', 8, 10, 'ativo')"
        ),
        {
            "id": webhook_id,
            "t": tenant_id,
            "api": api_client_id,
            "nome": f"webhook-worker-{sufixo}",
            "url": "https://example.invalid/receber",
            "segredo": b"\x00" * 28,
        },
    )

    await sessao_worker_f13.commit()
    await aplicar_tenant(sessao_worker_f13, tenant_id)

    return ContextoWebhooksWorkerF13(
        tenant_id=tenant_id, api_client_id=api_client_id, webhook_id=webhook_id
    )
