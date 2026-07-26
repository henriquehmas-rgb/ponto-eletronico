"""Resolvedor: escala 12x36 pura e virada de mes (PCF T7, "Pronto quando":
"12x36 puro" e "12x36 atravessando virada de mes"; criterio de aceite 3).

`data_referencia` da escala em 01/01/2026 (posicao 1 = trabalho), atribuicao
com `vigenciaInicio` em janeiro e `posicaoInicial=1`. A posicao do ciclo e
`((dias_desde_inicio + posicao_inicial - 1) % 2) + 1` -- com `dias_ciclo=2` e
`posicao_inicial=1`, todo dia par desde a vigencia cai em trabalho (posicao 1)
e todo dia impar em folga (posicao 2). A virada de mes (31/01 -> 01/02) nao
tem nada de especial: e so mais um dia na diferenca inteira.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy.ext.asyncio import AsyncSession

from app.jornada.resolvedor.servico import resolver_jornada_do_dia
from tests.f3.conftest import ContextoF3
from tests.f3.resolvedor import apoio


async def _montar_escala_12x36(
    contexto_f3: ContextoF3, sessao_f3: AsyncSession
) -> tuple[dt.date, object]:
    horario = await apoio.criar_horario(
        sessao_f3,
        contexto_f3.tenant_id,
        contexto_f3.empresa_id,
        codigo="PLANTAO-12H",
        entrada="07:00",
        saida="19:00",
        carga_minutos=660,
    )
    turno = await apoio.criar_turno(
        sessao_f3,
        contexto_f3.tenant_id,
        contexto_f3.empresa_id,
        codigo="TURNO-PLANTAO",
        horario_id=horario.id,
    )
    vigencia_inicio = dt.date(2026, 1, 1)
    escala = await apoio.criar_escala_12x36(
        sessao_f3,
        contexto_f3.tenant_id,
        contexto_f3.empresa_id,
        codigo="ESCALA-12X36",
        turno_trabalho_id=turno.id,
        data_referencia=vigencia_inicio,
        carga_trabalho_minutos=660,
    )
    await apoio.atribuir_escala(
        sessao_f3,
        contexto_f3.tenant_id,
        escala.id,
        contexto_f3.vinculo_sp_id,
        vigencia_inicio=vigencia_inicio,
        posicao_inicial=1,
    )
    return vigencia_inicio, escala


async def test_12x36_puro_trabalho_e_folga_alternados(
    contexto_f3: ContextoF3, sessao_f3: AsyncSession
) -> None:
    _, escala = await _montar_escala_12x36(contexto_f3, sessao_f3)

    # dias_desde_inicio par (0, 2, 4, ...) -> posicao 1 (trabalho).
    trabalho = await resolver_jornada_do_dia(
        sessao_f3, contexto_f3.tenant_id, contexto_f3.vinculo_sp_id, dt.date(2026, 1, 1)
    )
    assert trabalho.posicao_ciclo == 1
    assert trabalho.tipo_dia == "util"
    assert trabalho.origem == "escala"
    assert trabalho.escala_id == escala.id
    assert trabalho.carga_prevista_minutos == 660
    assert trabalho.entrada_prevista is not None

    # dias_desde_inicio impar (1, 3, 5, ...) -> posicao 2 (folga).
    folga = await resolver_jornada_do_dia(
        sessao_f3, contexto_f3.tenant_id, contexto_f3.vinculo_sp_id, dt.date(2026, 1, 2)
    )
    assert folga.posicao_ciclo == 2
    assert folga.tipo_dia == "folga"
    assert folga.origem == "escala"
    assert folga.carga_prevista_minutos == 0
    assert folga.entrada_prevista is None
    assert folga.horario_id is None


async def test_12x36_atravessa_virada_de_mes(
    contexto_f3: ContextoF3, sessao_f3: AsyncSession
) -> None:
    """31/01/2026 (dia 30 desde a vigencia, par -> trabalho) e 01/02/2026
    (dia 31, impar -> folga): a aritmetica de dias nao trata o dia 1o do mes
    como especial (PCF, criterio de aceite 3)."""
    await _montar_escala_12x36(contexto_f3, sessao_f3)

    dia_31_jan = await resolver_jornada_do_dia(
        sessao_f3, contexto_f3.tenant_id, contexto_f3.vinculo_sp_id, dt.date(2026, 1, 31)
    )
    dia_1_fev = await resolver_jornada_do_dia(
        sessao_f3, contexto_f3.tenant_id, contexto_f3.vinculo_sp_id, dt.date(2026, 2, 1)
    )

    # (31/01/2026 - 01/01/2026).dias == 30 -> par -> posicao 1 (trabalho).
    assert dia_31_jan.posicao_ciclo == 1
    assert dia_31_jan.tipo_dia == "util"
    # (01/02/2026 - 01/01/2026).dias == 31 -> impar -> posicao 2 (folga).
    assert dia_1_fev.posicao_ciclo == 2
    assert dia_1_fev.tipo_dia == "folga"


async def test_escala_tem_precedencia_sobre_jornada_do_mesmo_vinculo(
    contexto_f3: ContextoF3, sessao_f3: AsyncSession
) -> None:
    """Se o vinculo tiver escala E jornada vigentes na mesma data, a escala
    manda (PCF, secao 2: "a precedencia de resolucao fixada neste PCF")."""
    vigencia_inicio, escala = await _montar_escala_12x36(contexto_f3, sessao_f3)

    horario_jornada = await apoio.criar_horario(
        sessao_f3,
        contexto_f3.tenant_id,
        contexto_f3.empresa_id,
        codigo="HORARIO-JORNADA-CONCORRENTE",
        entrada="09:00",
        saida="17:00",
        carga_minutos=480,
    )
    jornada = await apoio.criar_jornada_fixa_semanal(
        sessao_f3,
        contexto_f3.tenant_id,
        contexto_f3.empresa_id,
        codigo="JOR-CONCORRENTE",
        horario_util_id=horario_jornada.id,
        carga_minutos_util=480,
        vigencia_inicio=vigencia_inicio,
    )
    await apoio.atribuir_jornada(
        sessao_f3,
        contexto_f3.tenant_id,
        contexto_f3.vinculo_sp_id,
        jornada.id,
        vigencia_inicio=vigencia_inicio,
    )

    resolucao = await resolver_jornada_do_dia(
        sessao_f3, contexto_f3.tenant_id, contexto_f3.vinculo_sp_id, dt.date(2026, 1, 1)
    )
    assert resolucao.origem == "escala"
    assert resolucao.escala_id == escala.id
    assert resolucao.jornada_id is None
