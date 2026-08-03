"""Testes de `app.integracoes.folha.comum.processamento` (F13/A5, T15)
contra Redis real (via `arq`, sem worker rodando de verdade -- so o
estado "enfileirado" e o isolamento de tenant sao exercitados aqui; os
estados "processando"/"concluido"/"falhou" dependem de um worker real
processar o job, cobertos por inspecao manual/teste de integracao ponta a
ponta documentado no relatorio da fase, nao neste arquivo)."""

from __future__ import annotations

import os
from uuid import uuid4

import pytest
import pytest_asyncio
from arq import create_pool
from arq.connections import RedisSettings

from app.core.filas import FILA_PADRAO
from app.integracoes.folha.comum import processamento as proc

pytestmark = pytest.mark.asyncio

_URL_REDIS_PADRAO = "redis://localhost:6379/0"


def _url_redis_teste() -> str:
    return os.environ.get("PONTO_TEST_REDIS_URL", _URL_REDIS_PADRAO)


@pytest_asyncio.fixture
async def pool_arq():
    pool = await create_pool(
        RedisSettings.from_dsn(_url_redis_teste()), default_queue_name=FILA_PADRAO
    )
    try:
        yield pool
    finally:
        await pool.aclose()


async def test_processamento_inexistente_devolve_none(pool_arq) -> None:
    estado = await proc.obter_estado(
        pool_arq,
        processamento_id=uuid4(),
        tenant_id=uuid4(),
        integracao_id=uuid4(),
    )
    assert estado is None


async def test_processamento_enfileirado_reporta_status_correto(pool_arq) -> None:
    processamento_id = uuid4()
    tenant_id = uuid4()
    integracao_id = uuid4()

    await pool_arq.enqueue_job(
        "exportar_folha",
        _job_id=str(processamento_id),
        tenant_id=str(tenant_id),
        integracao_id=str(integracao_id),
        empresa_id=str(uuid4()),
        parceiro="generico_csv",
        periodo_id=None,
        competencia_folha="2026-07",
        unidade_id=None,
        somente_fechados=True,
    )

    estado = await proc.obter_estado(
        pool_arq,
        processamento_id=processamento_id,
        tenant_id=tenant_id,
        integracao_id=integracao_id,
    )
    assert estado is not None
    assert estado.status == "enfileirado"
    assert estado.progresso == 0
    assert estado.resultado_ref is None


async def test_isolamento_de_tenant_nunca_confirma_nem_nega(pool_arq) -> None:
    processamento_id = uuid4()
    tenant_id_dono = uuid4()
    integracao_id = uuid4()

    await pool_arq.enqueue_job(
        "exportar_folha",
        _job_id=str(processamento_id),
        tenant_id=str(tenant_id_dono),
        integracao_id=str(integracao_id),
        empresa_id=str(uuid4()),
        parceiro="generico_csv",
        periodo_id=None,
        competencia_folha="2026-07",
        unidade_id=None,
        somente_fechados=True,
    )

    # Mesmo processamentoId, tenant DIFERENTE -- nunca deve devolver o
    # estado de outro tenant (isolamento, ver docstring do modulo).
    estado_outro_tenant = await proc.obter_estado(
        pool_arq,
        processamento_id=processamento_id,
        tenant_id=uuid4(),
        integracao_id=integracao_id,
    )
    assert estado_outro_tenant is None

    # Mesmo processamentoId/tenant, integracao DIFERENTE -- idem.
    estado_outra_integracao = await proc.obter_estado(
        pool_arq,
        processamento_id=processamento_id,
        tenant_id=tenant_id_dono,
        integracao_id=uuid4(),
    )
    assert estado_outra_integracao is None

    # Tenant/integracao corretos -- encontra normalmente.
    estado_correto = await proc.obter_estado(
        pool_arq,
        processamento_id=processamento_id,
        tenant_id=tenant_id_dono,
        integracao_id=integracao_id,
    )
    assert estado_correto is not None
