"""Períodos de apuração, tag `fechamentos` do contrato (T5, F10/A2).

`periodos` é a janela de apuração da empresa -- independente do período de
banco de horas (`periodos.tipo = 'banco_horas'` é um valor próprio, não
reaproveita `bh_contas.periodo_inicio/fim`, ver comentário do `schema.sql`).
Este módulo é só CRUD leve (criar/listar); o ciclo de vida do fechamento em
si (`criarFechamento`/`conferirFechamento`/`reabrirFechamento`) vive em
`servico.py`/`conferencia.py`.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from ponto_contracts import Periodo
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.erros import ErroDeAplicacao
from app.schemas import contrato as esquemas
from app.workflow.fechamento.erros_bd import traduzir_integridade
from app.workflow.fechamento.paginacao import (
    CampoOrdenacao,
    codificar_cursor,
    executar_pagina,
    interpretar_ordenar,
    montar_paginacao,
    normalizar_limite,
)

CODIGO_CORPO_INVALIDO = "PONTO-VAL-001"
CODIGO_INTERVALO_INVALIDO = "PONTO-VAL-007"
CODIGO_RECURSO_NAO_ENCONTRADO = "PONTO-REC-001"

_CAMPOS_ORDENACAO_PERIODO: dict[str, CampoOrdenacao] = {
    "dataInicio": CampoOrdenacao(Periodo.data_inicio, dt.date.fromisoformat),
    "codigo": CampoOrdenacao(Periodo.codigo, str),
}


def _valor(bruto: Any) -> Any:
    return bruto.value if hasattr(bruto, "value") else bruto


async def obter_periodo(sessao: AsyncSession, periodo_id: UUID) -> Periodo:
    periodo = await sessao.get(Periodo, periodo_id)
    if periodo is None:
        raise ErroDeAplicacao(CODIGO_RECURSO_NAO_ENCONTRADO, detalhe="Periodo nao encontrado.")
    return periodo


async def criar_periodo(
    sessao: AsyncSession,
    tenant_id: UUID,
    dados: esquemas.PeriodoCriar,
    *,
    usuario_id: UUID | None,
) -> Periodo:
    if dados.data_fim < dados.data_inicio:
        raise ErroDeAplicacao(
            CODIGO_INTERVALO_INVALIDO, detalhe="dataFim nao pode ser anterior a dataInicio."
        )

    campos: dict[str, Any] = dados.model_dump(exclude_unset=True)
    for chave in ("tipo", "status"):
        if chave in campos and campos[chave] is not None:
            campos[chave] = _valor(campos[chave])

    periodo = Periodo(tenant_id=tenant_id, criado_por=usuario_id, **campos)
    sessao.add(periodo)
    try:
        await sessao.flush()
    except IntegrityError as exc:
        raise traduzir_integridade(exc, padrao=CODIGO_CORPO_INVALIDO) from exc
    return periodo


async def listar_periodos(
    sessao: AsyncSession,
    tenant_id: UUID,
    *,
    empresa_id: UUID | None = None,
    tipo: str | None = None,
    status: str | None = None,
    competencia_folha: str | None = None,
    cursor: str | None = None,
    limite: int | None = None,
    ordenar: str | None = None,
) -> tuple[Sequence[Periodo], esquemas.Paginacao]:
    ordenacao = interpretar_ordenar(
        ordenar, campos_aceitos=frozenset(_CAMPOS_ORDENACAO_PERIODO), padrao="dataInicio"
    )
    limite_efetivo = normalizar_limite(limite)

    consulta = sa.select(Periodo).where(Periodo.tenant_id == tenant_id)
    if empresa_id is not None:
        consulta = consulta.where(Periodo.empresa_id == empresa_id)
    if tipo is not None:
        consulta = consulta.where(Periodo.tipo == tipo)
    if status is not None:
        consulta = consulta.where(Periodo.status == status)
    if competencia_folha is not None:
        consulta = consulta.where(Periodo.competencia_folha == competencia_folha)

    campo = _CAMPOS_ORDENACAO_PERIODO[ordenacao.campo]
    linhas, tem_mais = await executar_pagina(
        sessao,
        consulta,
        ordenacao=ordenacao,
        campo=campo,
        coluna_id=Periodo.id,
        cursor=cursor,
        limite=limite_efetivo,
    )
    atributo = "data_inicio" if ordenacao.campo == "dataInicio" else "codigo"
    proximo_cursor = None
    if tem_mais and linhas:
        ultimo = linhas[-1]
        proximo_cursor = codificar_cursor(ordenacao, getattr(ultimo, atributo), ultimo.id)
    paginacao = montar_paginacao(
        proximo_cursor=proximo_cursor, tem_mais=tem_mais, limite=limite_efetivo
    )
    return linhas, paginacao
