"""Resolução do escopo de um fechamento (`empresa`/`unidade`/`departamento`/
`equipe`/`colaborador`) em vínculos concretos -- compartilhado por
`conferencia.py`, `servico.py` e `apps/worker/worker/tarefas/fechamento.py`
(F10/A2).

Mesmo enum de `fechamentos.escopo`/`FechamentoCriar.escopo` (`schema.sql`
seção 12, `openapi.yaml`). `escopo='equipe'` resolve por
`equipe_membros` (vigência cobrindo ao menos um dia do período, F1); os
demais escopos filtram `vinculos` diretamente.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from uuid import UUID

import sqlalchemy as sa
from ponto_contracts import EquipeMembro, Vinculo
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.erros import ErroDeAplicacao

CODIGO_CORPO_INVALIDO = "PONTO-VAL-001"

_ESCOPOS_VALIDOS = frozenset({"empresa", "unidade", "departamento", "equipe", "colaborador"})


async def resolver_vinculos_do_escopo(
    sessao: AsyncSession,
    tenant_id: UUID,
    *,
    escopo: str,
    empresa_id: UUID,
    unidade_id: UUID | None = None,
    departamento_id: UUID | None = None,
    equipe_id: UUID | None = None,
    colaborador_id: UUID | None = None,
    periodo_inicio: dt.date | None = None,
    periodo_fim: dt.date | None = None,
) -> list[Vinculo]:
    """Resolve o escopo pedido em vínculos concretos, sempre restrito a
    `apura_ponto = true` e não excluídos (mesmo filtro que `app.apuracao.
    tratamento.recalculo._resolver_vinculos` já usa -- cópia própria, não
    importada, porque aquele módulo é ownership congelado de F4)."""
    if escopo not in _ESCOPOS_VALIDOS:
        raise ErroDeAplicacao(CODIGO_CORPO_INVALIDO, detalhe=f"escopo invalido: {escopo!r}.")

    condicoes = [
        Vinculo.tenant_id == tenant_id,
        Vinculo.empresa_id == empresa_id,
        Vinculo.excluido_em.is_(None),
        Vinculo.apura_ponto.is_(True),
    ]

    if escopo == "empresa":
        pass
    elif escopo == "unidade":
        if unidade_id is None:
            raise ErroDeAplicacao(
                CODIGO_CORPO_INVALIDO, detalhe="unidadeId e obrigatorio quando escopo e unidade."
            )
        condicoes.append(Vinculo.unidade_id == unidade_id)
    elif escopo == "departamento":
        if departamento_id is None:
            raise ErroDeAplicacao(
                CODIGO_CORPO_INVALIDO,
                detalhe="departamentoId e obrigatorio quando escopo e departamento.",
            )
        condicoes.append(Vinculo.departamento_id == departamento_id)
    elif escopo == "colaborador":
        if colaborador_id is None:
            raise ErroDeAplicacao(
                CODIGO_CORPO_INVALIDO,
                detalhe="colaboradorId e obrigatorio quando escopo e colaborador.",
            )
        condicoes.append(Vinculo.colaborador_id == colaborador_id)
    elif escopo == "equipe":
        if equipe_id is None:
            raise ErroDeAplicacao(
                CODIGO_CORPO_INVALIDO, detalhe="equipeId e obrigatorio quando escopo e equipe."
            )
        subconsulta = sa.select(EquipeMembro.colaborador_id).where(
            EquipeMembro.tenant_id == tenant_id,
            EquipeMembro.equipe_id == equipe_id,
        )
        if periodo_inicio is not None:
            subconsulta = subconsulta.where(
                sa.or_(
                    EquipeMembro.vigencia_fim.is_(None),
                    EquipeMembro.vigencia_fim >= periodo_inicio,
                )
            )
        if periodo_fim is not None:
            subconsulta = subconsulta.where(EquipeMembro.vigencia_inicio <= periodo_fim)
        condicoes.append(Vinculo.colaborador_id.in_(subconsulta))

    consulta = sa.select(Vinculo).where(*condicoes)
    resultado = await sessao.execute(consulta)
    return list(resultado.scalars().all())


def dias_do_intervalo(inicio: dt.date, fim: dt.date) -> Sequence[dt.date]:
    """Lista os dias `[inicio, fim]`, inclusive."""
    return [inicio + dt.timedelta(days=n) for n in range((fim - inicio).days + 1)]
