"""Dataset `absenteismo` (item 6, `PROJETO.md` §9, dataset `absenteismo`) --
T7 do PCF F11/A2.

**Pronto quando (T7):** prova que a soma das colunas numéricas bate com a
soma direta em `apuracoes_dia` para o mesmo escopo.
"""

from __future__ import annotations

import sqlalchemy as sa
from ponto_contracts import ApuracaoDia
from sqlalchemy.ext.asyncio import AsyncSession

from app.relatorios.motor import ContextoConsulta
from tests.f11.conftest import ContextoF11
from tests.f11.datasets_operacionais._apoio import executar


async def _soma_direta_falta(sessao: AsyncSession, tenant_id: object) -> int:
    resultado = await sessao.execute(
        sa.select(sa.func.coalesce(sa.func.sum(ApuracaoDia.falta_minutos), 0)).where(
            ApuracaoDia.tenant_id == tenant_id
        )
    )
    return int(resultado.scalar_one())


async def test_soma_falta_minutos_bate_com_apuracoes_dia(
    sessao_f11: AsyncSession, contexto_f11: ContextoF11
) -> None:
    contexto = ContextoConsulta(
        tenant_id=contexto_f11.tenant_id,
        de=contexto_f11.dias_uteis[0],
        ate=contexto_f11.dias_uteis[-1],
    )
    resultado = await executar(
        sessao_f11,
        contexto_f11.tenant_id,
        "absenteismo",
        contexto_f11.relatorio_ids,
        filtros=contexto,
    )
    assert len(resultado.linhas) == 9
    soma_falta = sum(linha["faltaMinutos"] for linha in resultado.linhas)
    soma_dias_com_falta = sum(linha["diasComFalta"] for linha in resultado.linhas)
    assert soma_falta == 480
    assert soma_falta == await _soma_direta_falta(sessao_f11, contexto_f11.tenant_id)
    # So um dia (colaborador C, ultimo dia util) tem falta > 0.
    assert soma_dias_com_falta == 1


async def test_agrupamento_por_departamento(
    sessao_f11: AsyncSession, contexto_f11: ContextoF11
) -> None:
    contexto = ContextoConsulta(
        tenant_id=contexto_f11.tenant_id,
        de=contexto_f11.dias_uteis[0],
        ate=contexto_f11.dias_uteis[-1],
    )
    resultado = await executar(
        sessao_f11,
        contexto_f11.tenant_id,
        "absenteismo",
        contexto_f11.relatorio_ids,
        filtros=contexto,
        agrupamento="departamento",
    )
    por_departamento = {linha["departamento"]: linha for linha in resultado.linhas}
    assert por_departamento["Financeiro"]["faltaMinutos"] == 480
    assert por_departamento["Financeiro"]["diasComFalta"] == 1
    assert por_departamento["Operacoes"]["faltaMinutos"] == 0
    assert por_departamento["Operacoes"]["diasComFalta"] == 0
