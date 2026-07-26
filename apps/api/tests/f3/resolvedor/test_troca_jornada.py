"""Resolvedor: troca de jornada no meio do mes respeita vigencia -- o dia
anterior a troca resolve pela jornada antiga, o dia da troca em diante pela
nova, sem reescrever o passado (PCF, criterio de aceite 4).
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy.ext.asyncio import AsyncSession

from app.jornada.resolvedor.servico import resolver_jornada_do_dia
from tests.f3.conftest import ContextoF3
from tests.f3.resolvedor import apoio


async def test_troca_de_jornada_no_meio_do_mes(
    contexto_f3: ContextoF3, sessao_f3: AsyncSession
) -> None:
    horario_antigo = await apoio.criar_horario(
        sessao_f3,
        contexto_f3.tenant_id,
        contexto_f3.empresa_id,
        codigo="HORARIO-ANTIGO",
        entrada="08:00",
        saida="17:00",
        carga_minutos=480,
    )
    jornada_antiga = await apoio.criar_jornada_fixa_semanal(
        sessao_f3,
        contexto_f3.tenant_id,
        contexto_f3.empresa_id,
        codigo="JOR-ANTIGA",
        horario_util_id=horario_antigo.id,
        carga_minutos_util=480,
        vigencia_inicio=dt.date(2026, 1, 1),
    )
    atribuicao_antiga = await apoio.atribuir_jornada(
        sessao_f3,
        contexto_f3.tenant_id,
        contexto_f3.vinculo_sp_id,
        jornada_antiga.id,
        vigencia_inicio=dt.date(2026, 1, 1),
    )

    # Encerra a vigencia antiga no dia 13 e abre a nova no dia 14 -- as duas
    # vigencias nao se sobrepoem (a constraint EXCLUDE recusaria se
    # sobrepusessem).
    await apoio.encerrar_vigencia_jornada(sessao_f3, atribuicao_antiga, dt.date(2026, 7, 13))

    horario_novo = await apoio.criar_horario(
        sessao_f3,
        contexto_f3.tenant_id,
        contexto_f3.empresa_id,
        codigo="HORARIO-NOVO",
        entrada="10:00",
        saida="19:00",
        carga_minutos=480,
    )
    jornada_nova = await apoio.criar_jornada_fixa_semanal(
        sessao_f3,
        contexto_f3.tenant_id,
        contexto_f3.empresa_id,
        codigo="JOR-NOVA",
        horario_util_id=horario_novo.id,
        carga_minutos_util=480,
        vigencia_inicio=dt.date(2026, 7, 14),
    )
    await apoio.atribuir_jornada(
        sessao_f3,
        contexto_f3.tenant_id,
        contexto_f3.vinculo_sp_id,
        jornada_nova.id,
        vigencia_inicio=dt.date(2026, 7, 14),
    )

    # 13/07/2026 (segunda-feira): ainda a jornada antiga.
    dia_13 = await resolver_jornada_do_dia(
        sessao_f3, contexto_f3.tenant_id, contexto_f3.vinculo_sp_id, dt.date(2026, 7, 13)
    )
    assert dia_13.jornada_id == jornada_antiga.id
    assert dia_13.jornada_codigo == "JOR-ANTIGA"
    assert dia_13.horario_id == horario_antigo.id
    assert dia_13.entrada_prevista is not None
    assert dia_13.entrada_prevista.isoformat() == "2026-07-13T08:00:00-03:00"

    # 14/07/2026 (terca-feira): a partir daqui, a jornada nova.
    dia_14 = await resolver_jornada_do_dia(
        sessao_f3, contexto_f3.tenant_id, contexto_f3.vinculo_sp_id, dt.date(2026, 7, 14)
    )
    assert dia_14.jornada_id == jornada_nova.id
    assert dia_14.jornada_codigo == "JOR-NOVA"
    assert dia_14.horario_id == horario_novo.id
    assert dia_14.entrada_prevista is not None
    assert dia_14.entrada_prevista.isoformat() == "2026-07-14T10:00:00-03:00"

    # O passado (dia 13) continua resolvendo igual, mesmo depois da troca --
    # nao ha reescrita do passado.
    dia_13_de_novo = await resolver_jornada_do_dia(
        sessao_f3, contexto_f3.tenant_id, contexto_f3.vinculo_sp_id, dt.date(2026, 7, 13)
    )
    assert dia_13_de_novo.jornada_id == jornada_antiga.id
