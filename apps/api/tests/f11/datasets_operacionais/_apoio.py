"""Apoio compartilhado entre os módulos de teste de `datasets_operacionais`
(ownership exclusivo de A2, T7/T8). **Não é um módulo de teste** -- o nome
não casa com `test_*.py`, então o pytest não o coleta; existe só para não
duplicar o mesmo helper em onze arquivos.

Importar este módulo garante, como efeito colateral, que `app.relatorios.
datasets.operacionais` foi importado e portanto que os onze datasets desta
fase já chamaram `registrar_dataset` (`app.relatorios.catalogo`) -- sem essa
importação, `executar_dataset` responderia `PONTO-INT-005` (dataset semeado
no catálogo mas sem função registrada, ver `catalogo.py::obter_dataset`).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from ponto_contracts import RelatorioDefinicao
from sqlalchemy.ext.asyncio import AsyncSession

import app.relatorios.datasets.operacionais as _operacionais  # noqa: F401 -- efeito colateral de registro
from app.relatorios.motor import ContextoConsulta, ResultadoRelatorio, executar_dataset


async def obter_definicao(
    sessao: AsyncSession, tenant_id: UUID, codigo: str, relatorio_ids: dict[str, UUID]
) -> RelatorioDefinicao:
    definicao = await sessao.get(RelatorioDefinicao, relatorio_ids[codigo])
    assert definicao is not None, f"relatorio_definicoes sem linha para o codigo '{codigo}'"
    assert definicao.tenant_id == tenant_id
    return definicao


async def executar(
    sessao: AsyncSession,
    tenant_id: UUID,
    codigo: str,
    relatorio_ids: dict[str, UUID],
    *,
    filtros: ContextoConsulta,
    colunas: Sequence[str] | None = None,
    agrupamento: str | None = None,
    limite: int | None = None,
) -> ResultadoRelatorio:
    """Executa o dataset do `codigo` pedido através do motor genérico real
    (`app.relatorios.motor.executar_dataset`) -- não chama a função de
    consulta diretamente, para o teste provar o caminho real (resolução do
    catálogo + projeção de colunas + paginação), não só a query isolada."""
    definicao = await obter_definicao(sessao, tenant_id, codigo, relatorio_ids)
    return await executar_dataset(
        sessao,
        tenant_id,
        definicao,
        filtros=filtros,
        colunas=list(colunas) if colunas is not None else None,
        agrupamento=agrupamento,
        limite=limite or 500,
    )


async def executar_bruto(
    sessao: AsyncSession,
    tenant_id: UUID,
    construtor: Callable[[AsyncSession, UUID, ContextoConsulta], sa.Select[Any]],
    *,
    filtros: ContextoConsulta,
) -> list[dict[str, Any]]:
    """Chama a função de dataset DIRETAMENTE (sem passar por `executar_
    dataset`/`RelatorioDefinicao.colunas_disponiveis`) e devolve todas as
    linhas como dicionários.

    Only used where o teste precisa inspecionar uma coluna que este módulo
    expõe além do mínimo já fixado por `tests/f11/conftest.py::_CATALOGO_
    RELATORIOS` (identidade `colaborador`/`vinculo` em UUID,
    `possuiAfastamentoRetroativo`, etc.) -- em modo não agrupado, o motor só
    projeta as colunas declaradas em `colunas_disponiveis` (`_resolver_
    colunas_pedidas`, `motor.py`), então uma coluna extra do `Select` bruto
    nunca aparece em `executar_dataset` a menos que também esteja declarada
    no catálogo semeado. Isto prova a função de consulta em si (a entrega
    real desta tarefa), não a integração com um catálogo de produção que
    esta fase ainda não decidiu como semear (PCF §4)."""
    consulta = construtor(sessao, tenant_id, filtros)
    resultado = await sessao.execute(consulta)
    return [dict(linha) for linha in resultado.mappings().all()]
