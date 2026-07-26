"""Resolvedor: detalhes de montagem do horario previsto -- intervalo que
cruza a meia-noite, pausas extras (`intervalos_extras`) e jornada vigente sem
desdobramento completo dos 7 dias da semana (cai em `PONTO-APUR-002` para o
dia sem `jornada_dias`, nunca 500 nem resultado inventado).
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.erros import ErroDeAplicacao
from app.jornada.modelagem import horarios as servico_horarios
from app.jornada.modelagem import jornadas as servico_jornadas
from app.jornada.resolvedor.servico import resolver_jornada_do_dia
from app.schemas import contrato as esquemas
from tests.f3.conftest import ContextoF3
from tests.f3.resolvedor import apoio


async def test_intervalo_que_cruza_meia_noite_soma_minutos_corretamente(
    contexto_f3: ContextoF3, sessao_f3: AsyncSession
) -> None:
    """`intervalo_inicio` > `intervalo_fim` (ex.: pausa entre 23:30 e 00:30
    de um turno noturno) precisa somar os minutos sobre a virada de dia, nao
    dar negativo."""
    horario = await apoio.criar_horario(
        sessao_f3,
        contexto_f3.tenant_id,
        contexto_f3.empresa_id,
        codigo="NOTURNO-INTERVALO-VIRADA",
        entrada="22:00",
        saida="06:00",
        cruza_meia_noite=True,
        intervalo_inicio="23:30",
        intervalo_fim="00:30",
        carga_minutos=420,
    )
    jornada = await apoio.criar_jornada_fixa_semanal(
        sessao_f3,
        contexto_f3.tenant_id,
        contexto_f3.empresa_id,
        codigo="JOR-NOTURNO",
        horario_util_id=horario.id,
        carga_minutos_util=420,
        vigencia_inicio=dt.date(2026, 1, 1),
        dia_dsr=-1,
    )
    await apoio.atribuir_jornada(
        sessao_f3,
        contexto_f3.tenant_id,
        contexto_f3.vinculo_sp_id,
        jornada.id,
        vigencia_inicio=dt.date(2026, 1, 1),
    )

    resolucao = await resolver_jornada_do_dia(
        sessao_f3, contexto_f3.tenant_id, contexto_f3.vinculo_sp_id, dt.date(2026, 7, 27)
    )
    assert resolucao.cruza_meia_noite is True
    assert resolucao.entrada_prevista is not None
    assert resolucao.saida_prevista is not None
    assert resolucao.saida_prevista.date() == dt.date(2026, 7, 28)
    assert resolucao.intervalos_previstos == {
        "intervalos": [{"inicio": "23:30", "fim": "00:30", "minutos": 60}]
    }


async def test_intervalos_extras_do_horario_sao_repassados(
    contexto_f3: ContextoF3, sessao_f3: AsyncSession
) -> None:
    """`horarios.intervalos_extras` (pausas NR-17, por exemplo) e somado a
    `intervalosPrevistos.intervalos` da resposta."""
    corpo = esquemas.HorarioCriar(
        empresa_id=contexto_f3.empresa_id,
        codigo="HORARIO-NR17",
        nome="HORARIO-NR17",
        entrada="08:00",
        saida="17:00",
        carga_minutos=480,
        intervalos_extras={"intervalos": [{"inicio": "10:00", "fim": "10:10", "minutos": 10}]},
    )
    horario = await servico_horarios.criar_horario(sessao_f3, contexto_f3.tenant_id, corpo)
    jornada = await apoio.criar_jornada_fixa_semanal(
        sessao_f3,
        contexto_f3.tenant_id,
        contexto_f3.empresa_id,
        codigo="JOR-NR17",
        horario_util_id=horario.id,
        carga_minutos_util=480,
        vigencia_inicio=dt.date(2026, 1, 1),
        dia_dsr=-1,
    )
    await apoio.atribuir_jornada(
        sessao_f3,
        contexto_f3.tenant_id,
        contexto_f3.vinculo_sp_id,
        jornada.id,
        vigencia_inicio=dt.date(2026, 1, 1),
    )

    resolucao = await resolver_jornada_do_dia(
        sessao_f3, contexto_f3.tenant_id, contexto_f3.vinculo_sp_id, dt.date(2026, 7, 27)
    )
    assert resolucao.intervalos_previstos is not None
    assert {"inicio": "10:00", "fim": "10:10", "minutos": 10} in resolucao.intervalos_previstos[
        "intervalos"
    ]


async def test_jornada_vigente_sem_dia_da_semana_e_apur_002(
    contexto_f3: ContextoF3, sessao_f3: AsyncSession
) -> None:
    """Jornada vigente mas com `jornada_dias` cobrindo so alguns dias da
    semana: consultar um dia sem linha correspondente e tratado como sem
    regra para o dia (`PONTO-APUR-002`), nunca 500 nem resultado inventado."""
    horario = await apoio.criar_horario(
        sessao_f3,
        contexto_f3.tenant_id,
        contexto_f3.empresa_id,
        codigo="HORARIO-PARCIAL",
        entrada="08:00",
        saida="17:00",
        carga_minutos=480,
    )
    corpo = esquemas.JornadaCriar(
        empresa_id=contexto_f3.empresa_id,
        codigo="JOR-PARCIAL",
        nome="JOR-PARCIAL",
        tipo=esquemas.Tipo14.fixa,
        vigencia_inicio=dt.date(2026, 1, 1),
        # So segunda-feira (dia_semana=1) tem linha em jornada_dias.
        dias=[
            esquemas.JornadaDia(
                dia_semana=1,
                tipo_dia=esquemas.TipoDia.util,
                horario_id=horario.id,
                carga_minutos=480,
            )
        ],
    )
    jornada = await servico_jornadas.criar_jornada(sessao_f3, contexto_f3.tenant_id, corpo)
    await apoio.atribuir_jornada(
        sessao_f3,
        contexto_f3.tenant_id,
        contexto_f3.vinculo_ba_id,
        jornada.id,
        vigencia_inicio=dt.date(2026, 1, 1),
    )

    # 28/07/2026 e terca-feira (dia_semana=2): sem linha em jornada_dias.
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await resolver_jornada_do_dia(
            sessao_f3, contexto_f3.tenant_id, contexto_f3.vinculo_ba_id, dt.date(2026, 7, 28)
        )
    assert excinfo.value.codigo == "PONTO-APUR-002"

    # 27/07/2026 e segunda-feira (dia_semana=1): tem linha, resolve normal.
    resolucao = await resolver_jornada_do_dia(
        sessao_f3, contexto_f3.tenant_id, contexto_f3.vinculo_ba_id, dt.date(2026, 7, 27)
    )
    assert resolucao.tipo_dia == "util"
