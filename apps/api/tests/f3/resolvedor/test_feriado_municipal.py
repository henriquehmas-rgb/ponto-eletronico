"""Resolvedor: feriado municipal aplica so na unidade certa (PCF, criterio de
aceite 5). As duas unidades da fixture da fase (`unidade_sp`/`unidade_ba`)
sao de municipios de UFs diferentes -- o feriado municipal associado so a
`unidade_sp` nunca deve aparecer resolvendo `vinculo_ba`.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy.ext.asyncio import AsyncSession

from app.jornada.resolvedor.servico import resolver_jornada_do_dia
from tests.f3.conftest import ContextoF3
from tests.f3.resolvedor import apoio


async def _montar_jornada_util_todo_dia(
    contexto_f3: ContextoF3, sessao_f3: AsyncSession, *, vinculo_id: object
) -> None:
    horario = await apoio.criar_horario(
        sessao_f3,
        contexto_f3.tenant_id,
        contexto_f3.empresa_id,
        codigo=f"HORARIO-{vinculo_id}",
        entrada="08:00",
        saida="17:00",
        carga_minutos=480,
    )
    jornada = await apoio.criar_jornada_fixa_semanal(
        sessao_f3,
        contexto_f3.tenant_id,
        contexto_f3.empresa_id,
        codigo=f"JOR-{vinculo_id}",
        horario_util_id=horario.id,
        carga_minutos_util=480,
        vigencia_inicio=dt.date(2026, 1, 1),
        dia_dsr=-1,  # nenhum dia e DSR: todo dia da semana e util neste teste.
    )
    await apoio.atribuir_jornada(
        sessao_f3,
        contexto_f3.tenant_id,
        vinculo_id,  # type: ignore[arg-type]
        jornada.id,
        vigencia_inicio=dt.date(2026, 1, 1),
    )


async def test_feriado_municipal_nao_vaza_para_outra_unidade(
    contexto_f3: ContextoF3, sessao_f3: AsyncSession
) -> None:
    vinculo_sp_id = contexto_f3.vinculo_sp_id
    vinculo_ba_id = contexto_f3.vinculo_ba_id
    await _montar_jornada_util_todo_dia(contexto_f3, sessao_f3, vinculo_id=vinculo_sp_id)
    await _montar_jornada_util_todo_dia(contexto_f3, sessao_f3, vinculo_id=vinculo_ba_id)

    conjunto = await apoio.criar_feriado_conjunto_municipal(
        sessao_f3,
        contexto_f3.tenant_id,
        codigo="ANIVERSARIO-SP",
        codigo_ibge=contexto_f3.unidade_sp_codigo_ibge,
        unidade_ids=[contexto_f3.unidade_sp_id],
    )
    data_feriado = dt.date(2026, 1, 25)  # aniversario do municipio de Sao Paulo
    await apoio.criar_feriado_fixo(
        sessao_f3,
        contexto_f3.tenant_id,
        conjunto.id,
        nome="Aniversario de Sao Paulo",
        data=data_feriado,
    )

    resolucao_sp = await resolver_jornada_do_dia(
        sessao_f3, contexto_f3.tenant_id, contexto_f3.vinculo_sp_id, data_feriado
    )
    resolucao_ba = await resolver_jornada_do_dia(
        sessao_f3, contexto_f3.tenant_id, contexto_f3.vinculo_ba_id, data_feriado
    )

    assert resolucao_sp.tipo_dia == "feriado"
    assert resolucao_sp.origem == "feriado"
    assert resolucao_sp.feriado_nome == "Aniversario de Sao Paulo"
    # jornadaId/horarioId continuam refletindo o que era previsto (PCF secao 2).
    assert resolucao_sp.jornada_id is not None
    assert resolucao_sp.horario_id is not None

    assert resolucao_ba.tipo_dia == "util"
    assert resolucao_ba.origem == "jornada"
    assert resolucao_ba.feriado_id is None
    assert resolucao_ba.feriado_nome is None


async def test_vinculo_sem_unidade_nunca_resolve_feriado(
    contexto_f3: ContextoF3, sessao_f3: AsyncSession
) -> None:
    """Decisao fixada no PCF (secao 2): sem `unidade_id`, o vinculo e tratado
    como sem nenhum `feriado_conjunto` aplicavel, mesmo que exista um
    conjunto nacional na base."""
    await _montar_jornada_util_todo_dia(
        contexto_f3, sessao_f3, vinculo_id=contexto_f3.vinculo_sem_unidade_id
    )

    conjunto = await apoio.criar_feriado_conjunto_municipal(
        sessao_f3,
        contexto_f3.tenant_id,
        codigo="ANIVERSARIO-SP-2",
        codigo_ibge=contexto_f3.unidade_sp_codigo_ibge,
        unidade_ids=[contexto_f3.unidade_sp_id],
    )
    data_feriado = dt.date(2026, 1, 26)
    await apoio.criar_feriado_fixo(
        sessao_f3, contexto_f3.tenant_id, conjunto.id, nome="Feriado SP 2", data=data_feriado
    )

    resolucao = await resolver_jornada_do_dia(
        sessao_f3, contexto_f3.tenant_id, contexto_f3.vinculo_sem_unidade_id, data_feriado
    )
    assert resolucao.tipo_dia == "util"
    assert resolucao.feriado_id is None
    assert resolucao.fuso_horario == contexto_f3.empresa_fuso_horario


async def test_feriado_nao_integral_usa_carga_reduzida(
    contexto_f3: ContextoF3, sessao_f3: AsyncSession
) -> None:
    """`feriados.integral = false` -> `cargaPrevistaMinutos` usa
    `carga_reduzida_minutos` no lugar da carga da jornada/escala (PCF secao 2)."""
    vinculo_id = contexto_f3.vinculo_sp_id
    await _montar_jornada_util_todo_dia(contexto_f3, sessao_f3, vinculo_id=vinculo_id)

    conjunto = await apoio.criar_feriado_conjunto_municipal(
        sessao_f3,
        contexto_f3.tenant_id,
        codigo="EXPEDIENTE-REDUZIDO",
        codigo_ibge=contexto_f3.unidade_sp_codigo_ibge,
        unidade_ids=[contexto_f3.unidade_sp_id],
    )
    data_feriado = dt.date(2026, 1, 27)
    await apoio.criar_feriado_fixo(
        sessao_f3,
        contexto_f3.tenant_id,
        conjunto.id,
        nome="Vespera reduzida",
        data=data_feriado,
        integral=False,
        carga_reduzida_minutos=240,
    )

    resolucao = await resolver_jornada_do_dia(
        sessao_f3, contexto_f3.tenant_id, vinculo_id, data_feriado
    )
    assert resolucao.tipo_dia == "feriado"
    assert resolucao.origem == "feriado"
    assert resolucao.carga_prevista_minutos == 240


async def test_feriado_data_comemorativa_nao_sobrescreve_tipo_dia(
    contexto_f3: ContextoF3, sessao_f3: AsyncSession
) -> None:
    """`feriados.tipo = 'data_comemorativa'` so preenche `feriadoId`/
    `feriadoNome` -- nao sobrescreve `tipoDia`/`origem`/carga (PCF secao 2:
    "os demais tipos ... nao sobrescrevem o tipo do dia")."""
    vinculo_id = contexto_f3.vinculo_sp_id
    await _montar_jornada_util_todo_dia(contexto_f3, sessao_f3, vinculo_id=vinculo_id)

    conjunto = await apoio.criar_feriado_conjunto_municipal(
        sessao_f3,
        contexto_f3.tenant_id,
        codigo="DATA-COMEMORATIVA",
        codigo_ibge=contexto_f3.unidade_sp_codigo_ibge,
        unidade_ids=[contexto_f3.unidade_sp_id],
    )
    data_comemorativa = dt.date(2026, 1, 28)
    await apoio.criar_feriado_fixo(
        sessao_f3,
        contexto_f3.tenant_id,
        conjunto.id,
        nome="Dia do Trabalhador Anonimo",
        data=data_comemorativa,
        tipo="data_comemorativa",
    )

    resolucao = await resolver_jornada_do_dia(
        sessao_f3, contexto_f3.tenant_id, vinculo_id, data_comemorativa
    )
    assert resolucao.tipo_dia == "util"
    assert resolucao.origem == "jornada"
    assert resolucao.feriado_id is not None
    assert resolucao.feriado_nome == "Dia do Trabalhador Anonimo"
