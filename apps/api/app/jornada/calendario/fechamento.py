"""Consulta somente leitura de `periodos`/`fechamentos`, para honrar
`PONTO-PER-001` em `atualizarAfastamento` (contrato: 4, ultimo paragrafo do
PCF da F3). Nunca escreve nessas duas tabelas -- a API de fechamento e da
F10, ainda nao construida. Como nenhuma fase anterior a esta popula
`fechamentos`, esta consulta nunca encontra nada hoje; o codigo precisa
estar correto para quando a F10 existir.
"""

from __future__ import annotations

import datetime as dt
from uuid import UUID

import sqlalchemy as sa
from ponto_contracts import Fechamento, Periodo
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.erros import ErroDeAplicacao

CODIGO_PERIODO_FECHADO = "PONTO-PER-001"


async def verificar_periodo_aberto(
    sessao: AsyncSession,
    tenant_id: UUID,
    *,
    empresa_id: UUID,
    unidade_id: UUID | None,
    data: dt.date,
) -> None:
    """Levanta `PONTO-PER-001` se `data` cai num `fechamentos.status = 'fechado'`
    cujo periodo (`periodos`) cobre a data e cujo escopo alcanca o alvo:
    escopo `empresa` sempre se aplica; escopo `unidade` so quando
    `unidade_id` bate com o do fechamento.

    So leitura: nenhuma linha e escrita em `periodos` nem em `fechamentos`.
    """
    escopos_alcancados = [Fechamento.escopo == "empresa"]
    if unidade_id is not None:
        escopos_alcancados.append(
            sa.and_(Fechamento.escopo == "unidade", Fechamento.unidade_id == unidade_id)
        )

    consulta = (
        select(Fechamento.id)
        .join(Periodo, Periodo.id == Fechamento.periodo_id)
        .where(
            Fechamento.tenant_id == tenant_id,
            Fechamento.empresa_id == empresa_id,
            Fechamento.status == "fechado",
            Periodo.data_inicio <= data,
            Periodo.data_fim >= data,
            sa.or_(*escopos_alcancados),
        )
        .limit(1)
    )
    resultado = await sessao.execute(consulta)
    if resultado.scalar_one_or_none() is not None:
        raise ErroDeAplicacao(
            CODIGO_PERIODO_FECHADO,
            detalhe="A data pertence a um periodo ja fechado para este escopo.",
        )
