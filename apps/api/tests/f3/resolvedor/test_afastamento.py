"""Resolvedor: afastamento aprovado e integral sobrepoe um dia que seria
util pela jornada (PCF, criterio de aceite -- caso de mesa "afastamento
sobrepondo dia de trabalho"); afastamento parcial NAO sobrepoe (PCF secao 2:
a constraint `ex_afastamentos_sobreposicao` so vale para integrais aprovados,
e a precedencia do resolvedor so olha para afastamento aprovado e integral).
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy.ext.asyncio import AsyncSession

from app.jornada.calendario import afastamentos as servico_afastamentos
from app.jornada.resolvedor.servico import resolver_jornada_do_dia
from app.schemas import contrato as esquemas
from tests.f3.conftest import ContextoF3
from tests.f3.resolvedor import apoio


async def _montar_jornada_fixa(contexto_f3: ContextoF3, sessao_f3: AsyncSession) -> None:
    horario = await apoio.criar_horario(
        sessao_f3,
        contexto_f3.tenant_id,
        contexto_f3.empresa_id,
        codigo="HORARIO-AFASTAMENTO",
        entrada="08:00",
        saida="17:00",
        carga_minutos=480,
    )
    jornada = await apoio.criar_jornada_fixa_semanal(
        sessao_f3,
        contexto_f3.tenant_id,
        contexto_f3.empresa_id,
        codigo="JOR-AFASTAMENTO",
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


async def test_afastamento_aprovado_integral_sobrepoe_dia_util(
    contexto_f3: ContextoF3, sessao_f3: AsyncSession
) -> None:
    await _montar_jornada_fixa(contexto_f3, sessao_f3)
    tipo = await apoio.criar_tipo_afastamento(
        sessao_f3, contexto_f3.tenant_id, codigo="FERIAS", categoria="ferias"
    )
    afastamento = await apoio.criar_afastamento(
        sessao_f3,
        contexto_f3.tenant_id,
        colaborador_id=contexto_f3.colaborador_sp_id,
        tipo_afastamento_id=tipo.id,
        data_inicio=dt.date(2026, 7, 6),
        data_fim=dt.date(2026, 7, 20),
        status="aprovado",
    )

    resolucao = await resolver_jornada_do_dia(
        sessao_f3, contexto_f3.tenant_id, contexto_f3.vinculo_sp_id, dt.date(2026, 7, 10)
    )

    assert resolucao.tipo_dia == "afastamento"
    assert resolucao.origem == "afastamento"
    assert resolucao.afastamento_id == afastamento.id
    # jornadaId/horarioId/entradaPrevista continuam refletindo o que era
    # previsto, mesmo com origem == 'afastamento' (PCF secao 2).
    assert resolucao.jornada_id is not None
    assert resolucao.horario_id is not None
    assert resolucao.entrada_prevista is not None


async def test_afastamento_fora_do_periodo_nao_afeta_o_dia(
    contexto_f3: ContextoF3, sessao_f3: AsyncSession
) -> None:
    await _montar_jornada_fixa(contexto_f3, sessao_f3)
    tipo = await apoio.criar_tipo_afastamento(
        sessao_f3, contexto_f3.tenant_id, codigo="FERIAS-2", categoria="ferias"
    )
    await apoio.criar_afastamento(
        sessao_f3,
        contexto_f3.tenant_id,
        colaborador_id=contexto_f3.colaborador_sp_id,
        tipo_afastamento_id=tipo.id,
        data_inicio=dt.date(2026, 7, 6),
        data_fim=dt.date(2026, 7, 20),
        status="aprovado",
    )

    resolucao = await resolver_jornada_do_dia(
        sessao_f3, contexto_f3.tenant_id, contexto_f3.vinculo_sp_id, dt.date(2026, 7, 21)
    )
    assert resolucao.tipo_dia == "util"
    assert resolucao.origem == "jornada"
    assert resolucao.afastamento_id is None


async def test_afastamento_parcial_nao_sobrepoe_dia_util(
    contexto_f3: ContextoF3, sessao_f3: AsyncSession
) -> None:
    """Afastamento parcial (algumas horas do dia) coexiste com a jornada
    normal -- a precedencia do resolvedor so considera afastamento aprovado
    e integral (PCF secao 2)."""
    await _montar_jornada_fixa(contexto_f3, sessao_f3)
    tipo = await apoio.criar_tipo_afastamento(
        sessao_f3, contexto_f3.tenant_id, codigo="CONSULTA", categoria="atestado"
    )
    corpo = esquemas.AfastamentoCriar(
        colaborador_id=contexto_f3.colaborador_sp_id,
        tipo_afastamento_id=tipo.id,
        data_inicio=dt.date(2026, 7, 8),
        periodo_parcial=True,
        hora_inicio="09:00",
        hora_fim="11:00",
        status="aprovado",  # type: ignore[arg-type]
    )
    afastamento_parcial = await servico_afastamentos.criar_afastamento(
        sessao_f3, contexto_f3.tenant_id, corpo
    )

    resolucao = await resolver_jornada_do_dia(
        sessao_f3, contexto_f3.tenant_id, contexto_f3.vinculo_sp_id, dt.date(2026, 7, 8)
    )
    assert resolucao.tipo_dia == "util"
    assert resolucao.origem == "jornada"
    assert resolucao.afastamento_id is None
    assert afastamento_parcial.periodo_parcial is True
