"""Fumaça de `worker.tarefas.relatorios.executar_relatorio` (F11, T6,
ownership conjunto A1/A3) -- roda a partir do venv de `apps/api` (`apps/
worker` instalado como dependência de teste, mesmo padrão que `tests/f4/
banco_horas/test_vencimento.py` já usa para o mesmo tipo de teste
cross-pacote, ADR-009).

Prova o critério de aceite de T6: uma execução real conclui com
`progresso=100`, `status='concluido'`, `hashSha256` presente e batendo com
o conteúdo gravado no MinIO; e que uma falha (dataset inexistente) marca
`status='falhou'` sem deixar a linha presa em `'processando'`.
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from ponto_contracts import RelatorioDefinicao, RelatorioExecucao
from sqlalchemy.ext.asyncio import AsyncSession

from tests.f11.conftest import ContextoF11


@pytest_asyncio.fixture(autouse=True)
async def _descartar_engine_global_apos_teste() -> AsyncIterator[None]:
    """`worker.tarefas.relatorios.executar_relatorio` abre a própria sessão
    via `app.db.sessao.fabrica_de_sessoes()` (engine GLOBAL do processo,
    cacheada em módulo -- diferente da engine `engine_f11` que `sessao_f11`
    usa, criada por teste). No Windows (`ProactorEventLoop`), uma conexão
    asyncpg aberta no loop de UM teste e finalizada no loop de outro
    (`asyncio_default_fixture_loop_scope=function`, um loop novo por teste)
    quebra o `pool_pre_ping` do SQLAlchemy com `RuntimeError: Event loop is
    closed` -- achado real de infraestrutura de teste, não um bug de
    `executar_relatorio` (confirmado rodando os dois testes deste módulo
    isoladamente: cada um passa sozinho). Descartar a engine global ao fim
    de cada teste força a recriação limpa no loop seguinte."""
    yield
    from app.db.sessao import encerrar_engine

    await encerrar_engine()


@pytest.mark.asyncio
async def test_executar_relatorio_conclui_com_sucesso(
    sessao_f11: AsyncSession, contexto_f11: ContextoF11
) -> None:
    from worker.tarefas.relatorios import executar_relatorio

    definicao_id = contexto_f11.relatorio_ids["auditoria"]
    execucao_id = uuid.uuid4()
    execucao = RelatorioExecucao(
        id=execucao_id,
        tenant_id=contexto_f11.tenant_id,
        relatorio_definicao_id=definicao_id,
        formato="csv",
        status="enfileirado",
        progresso=0,
    )
    sessao_f11.add(execucao)
    await sessao_f11.commit()
    from tests.f11.conftest import aplicar_tenant_teste

    await aplicar_tenant_teste(sessao_f11, contexto_f11.tenant_id)

    resultado = await executar_relatorio(
        {"job_id": "teste-smoke"},
        tenant_id=str(contexto_f11.tenant_id),
        execucao_id=str(execucao_id),
        codigo="auditoria",
        parametros={},
        formato="csv",
    )
    assert resultado["sucesso"] is True

    recarregada = await sessao_f11.get(RelatorioExecucao, execucao_id, populate_existing=True)
    assert recarregada is not None
    assert recarregada.status == "concluido"
    assert recarregada.progresso == 100
    assert recarregada.hash_sha256 is not None
    assert recarregada.conteudo_ref is not None
    assert recarregada.tamanho_bytes is not None and recarregada.tamanho_bytes > 0

    from app.comum.armazenamento import obter_objeto

    conteudo = await obter_objeto(recarregada.conteudo_ref)
    assert hashlib.sha256(conteudo).hexdigest() == recarregada.hash_sha256


@pytest.mark.asyncio
async def test_executar_relatorio_falha_marca_status_falhou(
    sessao_f11: AsyncSession, contexto_f11: ContextoF11
) -> None:
    from worker.tarefas.relatorios import executar_relatorio

    # `RelatorioDefinicao` com `dataset` inexistente no catalogo -- provoca
    # falha dentro de `_executar` (catalogo.obter_dataset levanta PONTO-
    # INT-005), sem tocar apurar_dia/recalcular_periodo.
    definicao_id = uuid.uuid4()
    sessao_f11.add(
        RelatorioDefinicao(
            id=definicao_id,
            tenant_id=contexto_f11.tenant_id,
            codigo="dataset-inexistente-de-teste",
            nome="Dataset inexistente de teste",
            categoria="gerencial",
            sistema=True,
            dataset="dataset_que_nao_existe",
            formatos=["csv"],
        )
    )
    execucao_id = uuid.uuid4()
    sessao_f11.add(
        RelatorioExecucao(
            id=execucao_id,
            tenant_id=contexto_f11.tenant_id,
            relatorio_definicao_id=definicao_id,
            formato="csv",
            status="enfileirado",
            progresso=0,
        )
    )
    await sessao_f11.commit()
    from tests.f11.conftest import aplicar_tenant_teste

    await aplicar_tenant_teste(sessao_f11, contexto_f11.tenant_id)

    resultado = await executar_relatorio(
        {"job_id": "teste-smoke-falha"},
        tenant_id=str(contexto_f11.tenant_id),
        execucao_id=str(execucao_id),
        codigo="dataset-inexistente-de-teste",
        parametros={},
        formato="csv",
    )
    assert resultado["sucesso"] is False

    recarregada = await sessao_f11.get(RelatorioExecucao, execucao_id, populate_existing=True)
    assert recarregada is not None
    assert recarregada.status == "falhou"
    assert recarregada.erro is not None
