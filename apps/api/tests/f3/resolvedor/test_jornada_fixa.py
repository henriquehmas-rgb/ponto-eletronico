"""Resolvedor: jornada fixa simples (PCF T7, "Pronto quando" -- caso de mesa
"jornada fixa simples").
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy.ext.asyncio import AsyncSession

from app.jornada.resolvedor.servico import resolver_jornada_do_dia
from tests.f3.conftest import ContextoF3
from tests.f3.resolvedor import apoio


async def test_dia_util_resolve_pela_jornada_fixa(
    contexto_f3: ContextoF3, sessao_f3: AsyncSession
) -> None:
    horario = await apoio.criar_horario(
        sessao_f3,
        contexto_f3.tenant_id,
        contexto_f3.empresa_id,
        codigo="COM-44H",
        entrada="08:00",
        saida="18:00",
        intervalo_inicio="12:00",
        intervalo_fim="13:00",
        carga_minutos=540,
    )
    jornada = await apoio.criar_jornada_fixa_semanal(
        sessao_f3,
        contexto_f3.tenant_id,
        contexto_f3.empresa_id,
        codigo="JOR-FIXA",
        horario_util_id=horario.id,
        carga_minutos_util=540,
        vigencia_inicio=dt.date(2026, 1, 1),
    )
    await apoio.atribuir_jornada(
        sessao_f3,
        contexto_f3.tenant_id,
        contexto_f3.vinculo_sp_id,
        jornada.id,
        vigencia_inicio=dt.date(2026, 1, 1),
    )

    # 27/07/2026 e segunda-feira: dia util na jornada fixa.
    data_consultada = dt.date(2026, 7, 27)
    resolucao = await resolver_jornada_do_dia(
        sessao_f3, contexto_f3.tenant_id, contexto_f3.vinculo_sp_id, data_consultada
    )

    assert resolucao.vinculo_id == contexto_f3.vinculo_sp_id
    assert resolucao.colaborador_id == contexto_f3.colaborador_sp_id
    assert resolucao.tipo_dia == "util"
    assert resolucao.origem == "jornada"
    assert resolucao.jornada_id == jornada.id
    assert resolucao.jornada_codigo == "JOR-FIXA"
    assert resolucao.escala_id is None
    assert resolucao.posicao_ciclo is None
    assert resolucao.horario_id == horario.id
    assert resolucao.carga_prevista_minutos == 540
    assert resolucao.cruza_meia_noite is False
    assert resolucao.fuso_horario == "America/Sao_Paulo"
    assert resolucao.entrada_prevista is not None
    assert resolucao.saida_prevista is not None
    assert resolucao.entrada_prevista.isoformat() == "2026-07-27T08:00:00-03:00"
    assert resolucao.saida_prevista.isoformat() == "2026-07-27T18:00:00-03:00"
    assert resolucao.intervalos_previstos == {
        "intervalos": [{"inicio": "12:00", "fim": "13:00", "minutos": 60}]
    }
    assert resolucao.feriado_id is None
    assert resolucao.afastamento_id is None


async def test_domingo_resolve_como_dsr(contexto_f3: ContextoF3, sessao_f3: AsyncSession) -> None:
    horario = await apoio.criar_horario(
        sessao_f3,
        contexto_f3.tenant_id,
        contexto_f3.empresa_id,
        codigo="COM-44H-2",
        entrada="08:00",
        saida="18:00",
        carga_minutos=540,
    )
    jornada = await apoio.criar_jornada_fixa_semanal(
        sessao_f3,
        contexto_f3.tenant_id,
        contexto_f3.empresa_id,
        codigo="JOR-FIXA-2",
        horario_util_id=horario.id,
        carga_minutos_util=540,
        vigencia_inicio=dt.date(2026, 1, 1),
    )
    await apoio.atribuir_jornada(
        sessao_f3,
        contexto_f3.tenant_id,
        contexto_f3.vinculo_sp_id,
        jornada.id,
        vigencia_inicio=dt.date(2026, 1, 1),
    )

    # 26/07/2026 e domingo (dia_dsr padrao = 0).
    resolucao = await resolver_jornada_do_dia(
        sessao_f3, contexto_f3.tenant_id, contexto_f3.vinculo_sp_id, dt.date(2026, 7, 26)
    )

    assert resolucao.tipo_dia == "dsr"
    assert resolucao.origem == "jornada"
    assert resolucao.horario_id is None
    assert resolucao.entrada_prevista is None
    assert resolucao.saida_prevista is None
    assert resolucao.carga_prevista_minutos == 0
