"""Consulta somente-leitura a `periodos`/`fechamentos`, para honrar
`PONTO-PER-001` em `atribuirJornadaVinculo` e `atribuirEscalaVinculo` (PCF da
fase, secao 2, ultimo paragrafo; secao 4, "Nao toca"). A **API** de
fechamento de periodo e da F10 -- este modulo nunca escreve nessas duas
tabelas, so consulta se ha um fechamento `status = 'fechado'` cobrindo a
data e o escopo do vinculo (empresa sempre; unidade/departamento quando o
fechamento for desse escopo).

Como nenhuma fase anterior a esta popula `fechamentos`, esta consulta nunca
encontra nada hoje -- mas o codigo precisa estar correto para quando a F10
existir (PCF, secao 2).
"""

from __future__ import annotations

import datetime as dt
from uuid import UUID

import sqlalchemy as sa
from ponto_contracts import Fechamento, Periodo
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.erros import ErroDeAplicacao

CODIGO_PERIODO_FECHADO = "PONTO-PER-001"


async def verificar_periodo_aberto(
    sessao: AsyncSession,
    tenant_id: UUID,
    *,
    empresa_id: UUID,
    data: dt.date,
    unidade_id: UUID | None = None,
    departamento_id: UUID | None = None,
) -> None:
    """Levanta `PONTO-PER-001` se algum `fechamentos.status = 'fechado'`
    cobrir `data` no escopo do vinculo. `empresa_id` sempre participa da
    checagem (escopo `empresa`); `unidade_id`/`departamento_id` so entram
    quando o fechamento e desse escopo especifico -- um fechamento de
    unidade nunca trava um vinculo de outra unidade da mesma empresa."""
    condicoes_escopo = [
        sa.and_(Fechamento.escopo == "empresa", Fechamento.empresa_id == empresa_id)
    ]
    if unidade_id is not None:
        condicoes_escopo.append(
            sa.and_(Fechamento.escopo == "unidade", Fechamento.unidade_id == unidade_id)
        )
    if departamento_id is not None:
        condicoes_escopo.append(
            sa.and_(
                Fechamento.escopo == "departamento",
                Fechamento.departamento_id == departamento_id,
            )
        )

    consulta = (
        sa.select(Fechamento.id)
        .join(Periodo, Periodo.id == Fechamento.periodo_id)
        .where(
            Fechamento.tenant_id == tenant_id,
            Fechamento.status == "fechado",
            Periodo.data_inicio <= data,
            Periodo.data_fim >= data,
            sa.or_(*condicoes_escopo),
        )
        .limit(1)
    )
    resultado = await sessao.execute(consulta)
    if resultado.scalar_one_or_none() is not None:
        raise ErroDeAplicacao(
            CODIGO_PERIODO_FECHADO,
            detalhe="O periodo desta data ja foi fechado para este escopo.",
        )
