"""Resolvedor: vinculo sem nenhuma atribuicao vigente responde
`PONTO-APUR-002`, nunca um 500 nem um resultado inventado (PCF, criterio de
aceite 10).
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.erros import ErroDeAplicacao
from app.jornada.resolvedor.servico import resolver_jornada_do_dia
from tests.f3.conftest import ContextoF3
from tests.f3.resolvedor import apoio


async def test_vinculo_sem_atribuicao_responde_apur_002(
    contexto_f3: ContextoF3, sessao_f3: AsyncSession
) -> None:
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await resolver_jornada_do_dia(
            sessao_f3, contexto_f3.tenant_id, contexto_f3.vinculo_ba_id, dt.date(2026, 7, 27)
        )
    assert excinfo.value.codigo == "PONTO-APUR-002"
    assert excinfo.value.http_status == 422


async def test_vigencia_encerrada_antes_da_data_tambem_e_apur_002(
    contexto_f3: ContextoF3, sessao_f3: AsyncSession
) -> None:
    """Uma jornada com `vigenciaFim` anterior a data consultada nao conta:
    a atribuicao ja nao esta vigente naquele dia."""
    horario = await apoio.criar_horario(
        sessao_f3,
        contexto_f3.tenant_id,
        contexto_f3.empresa_id,
        codigo="HORARIO-ENCERRADO",
        entrada="08:00",
        saida="17:00",
        carga_minutos=480,
    )
    jornada = await apoio.criar_jornada_fixa_semanal(
        sessao_f3,
        contexto_f3.tenant_id,
        contexto_f3.empresa_id,
        codigo="JOR-ENCERRADA",
        horario_util_id=horario.id,
        carga_minutos_util=480,
        vigencia_inicio=dt.date(2026, 1, 1),
        dia_dsr=-1,
    )
    atribuicao = await apoio.atribuir_jornada(
        sessao_f3,
        contexto_f3.tenant_id,
        contexto_f3.vinculo_ba_id,
        jornada.id,
        vigencia_inicio=dt.date(2026, 1, 1),
    )
    await apoio.encerrar_vigencia_jornada(sessao_f3, atribuicao, dt.date(2026, 6, 30))

    with pytest.raises(ErroDeAplicacao) as excinfo:
        await resolver_jornada_do_dia(
            sessao_f3, contexto_f3.tenant_id, contexto_f3.vinculo_ba_id, dt.date(2026, 7, 1)
        )
    assert excinfo.value.codigo == "PONTO-APUR-002"
