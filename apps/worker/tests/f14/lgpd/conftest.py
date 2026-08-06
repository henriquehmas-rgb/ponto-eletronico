"""Fixture do subarvore `lgpd` no lado worker da fase F14 (A3), mesmo padrao
ja usado por `apps/worker/tests/f13/webhooks/conftest.py`: self-contained,
conecta DIRETO no banco de teste ja migrado (`PONTO_TEST_DATABASE_URL`) --
`worker.tarefas.lgpd.expurgo_lgpd` so encaminha para `app.lgpd.expurgo.
aplicar_politicas_vencidas` (ADR-009), cuja logica de negocio ja tem
cobertura propria em `apps/api/tests/f14/lgpd/test_expurgo.py`. Este arquivo
cobre so a fiacao do wrapper do worker (tenant aplicado, simulacao=True faz
ROLLBACK de verdade, formato do retorno)."""

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

_URL_PADRAO_LOCAL = "postgresql+asyncpg://ponto:ponto@localhost:5432/ponto"


def _url_banco_teste() -> str:
    return os.environ.get("PONTO_TEST_DATABASE_URL", _URL_PADRAO_LOCAL)


async def _reiniciar_engines_compartilhadas() -> None:
    """Mesma razao de `apps/worker/tests/f13/webhooks/conftest.py`:
    `app.db.sessao` (apps/api) cacheia sua PROPRIA engine, presa ao event
    loop do teste que a criou primeiro -- sem descarta-la entre testes, o
    segundo teste desta suite (loop novo por teste, pytest-asyncio) herda
    uma engine presa a um loop ja fechado."""
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

    obter_configuracao.cache_clear()
    await _reiniciar_engines_compartilhadas()
    yield
    await _reiniciar_engines_compartilhadas()


@pytest_asyncio.fixture
async def engine_worker_f14(request: object) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(_url_banco_teste(), pool_pre_ping=True)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def sessao_worker_f14(engine_worker_f14: AsyncEngine) -> AsyncIterator[AsyncSession]:
    fabrica = async_sessionmaker(engine_worker_f14, expire_on_commit=False, autoflush=False)
    async with fabrica() as sessao:
        yield sessao
        await sessao.rollback()


async def aplicar_tenant(sessao: AsyncSession, tenant_id: uuid.UUID) -> None:
    await sessao.execute(
        text("SELECT set_config('app.tenant_id', :tenant, true)"), {"tenant": str(tenant_id)}
    )


@dataclass(frozen=True, slots=True)
class ContextoLgpdWorkerF14:
    tenant_id: uuid.UUID


@pytest_asyncio.fixture
async def contexto_lgpd_worker_f14(
    sessao_worker_f14: AsyncSession,
) -> ContextoLgpdWorkerF14:
    """Semeia so o tenant -- cada teste semeia sua propria politica/registro,
    o cenario varia por teste (simulacao vs. real)."""
    sufixo = uuid.uuid4().hex[:10]
    tenant_id = uuid.uuid4()
    await aplicar_tenant(sessao_worker_f14, tenant_id)

    await sessao_worker_f14.execute(
        text(
            "INSERT INTO tenants (id, slug, razao_social, nome_exibicao, status) "
            "VALUES (:id, :slug, :r, :n, 'ativo')"
        ),
        {
            "id": tenant_id,
            "slug": f"f14a3-worker-{sufixo}",
            "r": "Tenant worker F14 A3",
            "n": "Tenant worker F14 A3",
        },
    )
    await sessao_worker_f14.commit()
    await aplicar_tenant(sessao_worker_f14, tenant_id)

    return ContextoLgpdWorkerF14(tenant_id=tenant_id)
