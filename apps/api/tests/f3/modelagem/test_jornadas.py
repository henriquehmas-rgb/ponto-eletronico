"""Testes de `app.jornada.modelagem.jornadas` (F3 / A1, T2).

Cobre o terceiro criterio de aceite da T2: `uq_jornadas_codigo` colide para o
mesmo `codigo` + `vigenciaInicio`, mas aceita o mesmo `codigo` com
`vigenciaInicio` diferente -- e assim que a jornada versiona (PCF secao 6).
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
from ponto_contracts import Horario
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.erros import ErroDeAplicacao
from app.jornada.modelagem import jornadas as servico
from app.schemas import contrato as esquemas
from tests.f3.conftest import ContextoF3

pytestmark = pytest.mark.asyncio


async def test_duas_jornadas_mesmo_codigo_e_mesma_vigencia_colidem(
    sessao_f3: AsyncSession, contexto_f3: ContextoF3
) -> None:
    primeira = esquemas.JornadaCriar(
        empresa_id=contexto_f3.empresa_id,
        codigo="JOR-FIXA-01",
        nome="Jornada fixa",
        tipo=esquemas.Tipo14.fixa,
        vigencia_inicio=dt.date(2026, 1, 1),
    )
    await servico.criar_jornada(sessao_f3, contexto_f3.tenant_id, primeira)
    await sessao_f3.flush()

    segunda = esquemas.JornadaCriar(
        empresa_id=contexto_f3.empresa_id,
        codigo="JOR-FIXA-01",
        nome="Jornada fixa duplicada",
        tipo=esquemas.Tipo14.fixa,
        vigencia_inicio=dt.date(2026, 1, 1),
    )
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.criar_jornada(sessao_f3, contexto_f3.tenant_id, segunda)
    assert excinfo.value.codigo == "PONTO-CONF-001"


async def test_mesmo_codigo_com_vigencia_inicio_diferente_e_aceito(
    sessao_f3: AsyncSession, contexto_f3: ContextoF3
) -> None:
    primeira = esquemas.JornadaCriar(
        empresa_id=contexto_f3.empresa_id,
        codigo="JOR-FIXA-02",
        nome="Jornada fixa (versao 1)",
        tipo=esquemas.Tipo14.fixa,
        vigencia_inicio=dt.date(2026, 1, 1),
        vigencia_fim=dt.date(2026, 1, 31),
    )
    await servico.criar_jornada(sessao_f3, contexto_f3.tenant_id, primeira)
    await sessao_f3.flush()

    segunda = esquemas.JornadaCriar(
        empresa_id=contexto_f3.empresa_id,
        codigo="JOR-FIXA-02",
        nome="Jornada fixa (versao 2)",
        tipo=esquemas.Tipo14.fixa,
        vigencia_inicio=dt.date(2026, 2, 1),
    )
    nova = await servico.criar_jornada(sessao_f3, contexto_f3.tenant_id, segunda)
    assert nova.codigo == "JOR-FIXA-02"
    assert nova.vigencia_inicio == dt.date(2026, 2, 1)


async def test_criar_jornada_com_dias_grava_jornada_dias(
    sessao_f3: AsyncSession, contexto_f3: ContextoF3
) -> None:
    horario = await _criar_horario_auxiliar(sessao_f3, contexto_f3, "HOR-JORNADA-DIAS")
    dados = esquemas.JornadaCriar(
        empresa_id=contexto_f3.empresa_id,
        codigo="JOR-COM-DIAS",
        nome="Jornada com dias",
        tipo=esquemas.Tipo14.fixa,
        vigencia_inicio=dt.date(2026, 1, 1),
        dias=[
            esquemas.JornadaDia(
                dia_semana=dia,
                tipo_dia=esquemas.TipoDia.util,
                horario_id=horario.id,
                carga_minutos=480,
            )
            for dia in range(1, 6)
        ]
        + [
            esquemas.JornadaDia(dia_semana=0, tipo_dia=esquemas.TipoDia.dsr, carga_minutos=0),
            esquemas.JornadaDia(dia_semana=6, tipo_dia=esquemas.TipoDia.folga, carga_minutos=0),
        ],
    )
    jornada = await servico.criar_jornada(sessao_f3, contexto_f3.tenant_id, dados)
    await sessao_f3.flush()
    dias = await servico.listar_dias_da_jornada(sessao_f3, jornada.id)
    assert len(dias) == 7
    assert {d.dia_semana for d in dias} == set(range(7))


async def test_excluir_jornada_inexistente_e_rec_001(
    sessao_f3: AsyncSession, contexto_f3: ContextoF3
) -> None:
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.excluir_jornada(sessao_f3, contexto_f3.tenant_id, uuid.uuid4())
    assert excinfo.value.codigo == "PONTO-REC-001"


async def test_excluir_jornada_em_uso_por_vinculo_vigente_e_conf_004(
    sessao_f3: AsyncSession, contexto_f3: ContextoF3
) -> None:
    from app.jornada.modelagem import vinculo_jornadas

    dados = esquemas.JornadaCriar(
        empresa_id=contexto_f3.empresa_id,
        codigo="JOR-EM-USO",
        nome="Jornada em uso",
        tipo=esquemas.Tipo14.livre,
        vigencia_inicio=dt.date(2026, 1, 1),
    )
    jornada = await servico.criar_jornada(sessao_f3, contexto_f3.tenant_id, dados)
    await sessao_f3.flush()

    atribuicao = esquemas.VinculoJornadaCriar(
        jornada_id=jornada.id, vigencia_inicio=dt.date(2026, 1, 1)
    )
    await vinculo_jornadas.atribuir_jornada_vinculo(
        sessao_f3, contexto_f3.tenant_id, contexto_f3.vinculo_sp_id, atribuicao
    )
    await sessao_f3.flush()

    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.excluir_jornada(sessao_f3, contexto_f3.tenant_id, jornada.id)
    assert excinfo.value.codigo == "PONTO-CONF-004"


async def test_excluir_jornada_com_sucesso(
    sessao_f3: AsyncSession, contexto_f3: ContextoF3
) -> None:
    dados = esquemas.JornadaCriar(
        empresa_id=contexto_f3.empresa_id,
        codigo="JOR-EXCLUIVEL",
        nome="Jornada excluivel",
        tipo=esquemas.Tipo14.livre,
        vigencia_inicio=dt.date(2026, 1, 1),
    )
    jornada = await servico.criar_jornada(sessao_f3, contexto_f3.tenant_id, dados)
    await sessao_f3.flush()

    await servico.excluir_jornada(sessao_f3, contexto_f3.tenant_id, jornada.id)
    await sessao_f3.flush()

    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.obter_jornada(sessao_f3, jornada.id)
    assert excinfo.value.codigo == "PONTO-REC-001"


async def test_excluir_jornada_em_uso_por_escala_e_conf_004(
    sessao_f3: AsyncSession, contexto_f3: ContextoF3
) -> None:
    from app.jornada.modelagem import escalas

    dados = esquemas.JornadaCriar(
        empresa_id=contexto_f3.empresa_id,
        codigo="JOR-BASE-ESCALA",
        nome="Jornada base de escala",
        tipo=esquemas.Tipo14.livre,
        vigencia_inicio=dt.date(2026, 1, 1),
    )
    jornada = await servico.criar_jornada(sessao_f3, contexto_f3.tenant_id, dados)
    await sessao_f3.flush()

    escala_dados = esquemas.EscalaCriar(
        empresa_id=contexto_f3.empresa_id,
        jornada_id=jornada.id,
        codigo="ESC-COM-JORNADA",
        nome="Escala com jornada associada",
        tipo=esquemas.Tipo20.field_5x2,
        dias_ciclo=7,
        data_referencia=dt.date(2026, 1, 1),
    )
    await escalas.criar_escala(sessao_f3, contexto_f3.tenant_id, escala_dados)
    await sessao_f3.flush()

    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.excluir_jornada(sessao_f3, contexto_f3.tenant_id, jornada.id)
    assert excinfo.value.codigo == "PONTO-CONF-004"


async def test_atualizar_jornada_substitui_dias(
    sessao_f3: AsyncSession, contexto_f3: ContextoF3
) -> None:
    dados = esquemas.JornadaCriar(
        empresa_id=contexto_f3.empresa_id,
        codigo="JOR-ATUALIZAR-DIAS",
        nome="Jornada com dias substituiveis",
        tipo=esquemas.Tipo14.fixa,
        vigencia_inicio=dt.date(2026, 1, 1),
        dias=[esquemas.JornadaDia(dia_semana=1, tipo_dia=esquemas.TipoDia.util, carga_minutos=480)],
    )
    jornada = await servico.criar_jornada(sessao_f3, contexto_f3.tenant_id, dados)
    await sessao_f3.flush()
    dias_iniciais = await servico.listar_dias_da_jornada(sessao_f3, jornada.id)
    assert len(dias_iniciais) == 1

    await servico.atualizar_jornada(
        sessao_f3,
        jornada.id,
        esquemas.JornadaAtualizar(
            dias=[
                esquemas.JornadaDia(dia_semana=d, tipo_dia=esquemas.TipoDia.util, carga_minutos=480)
                for d in range(1, 6)
            ]
        ),
    )
    await sessao_f3.flush()
    dias_novos = await servico.listar_dias_da_jornada(sessao_f3, jornada.id)
    assert len(dias_novos) == 5


async def test_listar_jornadas_filtra_por_tipo_e_vigencia(
    sessao_f3: AsyncSession, contexto_f3: ContextoF3
) -> None:
    await _criar_jornada_para_listagem(
        sessao_f3, contexto_f3, "JOR-LISTA-LIVRE", esquemas.Tipo14.livre, dt.date(2026, 3, 1)
    )
    await _criar_jornada_para_listagem(
        sessao_f3, contexto_f3, "JOR-LISTA-FIXA", esquemas.Tipo14.fixa, dt.date(2026, 3, 1)
    )
    await sessao_f3.flush()

    linhas, paginacao = await servico.listar_jornadas(
        sessao_f3,
        contexto_f3.tenant_id,
        empresa_id=contexto_f3.empresa_id,
        tipo="livre",
        vigente_em=dt.date(2026, 3, 15),
        ordenar="codigo:asc",
    )
    codigos = {j.codigo for j in linhas}
    assert "JOR-LISTA-LIVRE" in codigos
    assert "JOR-LISTA-FIXA" not in codigos
    assert paginacao.limite == 50


async def _criar_jornada_para_listagem(
    sessao: AsyncSession,
    contexto: ContextoF3,
    codigo: str,
    tipo: esquemas.Tipo14,
    vigencia_inicio: dt.date,
):
    dados = esquemas.JornadaCriar(
        empresa_id=contexto.empresa_id,
        codigo=codigo,
        nome=f"Jornada {codigo}",
        tipo=tipo,
        vigencia_inicio=vigencia_inicio,
    )
    return await servico.criar_jornada(sessao, contexto.tenant_id, dados)


async def test_listar_jornadas_filtra_por_ativo_e_pagina(
    sessao_f3: AsyncSession, contexto_f3: ContextoF3
) -> None:
    for i in range(3):
        dados = esquemas.JornadaCriar(
            empresa_id=contexto_f3.empresa_id,
            codigo=f"JOR-PAG-{i}",
            nome=f"Jornada pag {i}",
            tipo=esquemas.Tipo14.livre,
            vigencia_inicio=dt.date(2026, 1, 1),
            ativo=True,
        )
        await servico.criar_jornada(sessao_f3, contexto_f3.tenant_id, dados)
    await sessao_f3.flush()

    primeira, paginacao = await servico.listar_jornadas(
        sessao_f3,
        contexto_f3.tenant_id,
        empresa_id=contexto_f3.empresa_id,
        ativo=True,
        limite=2,
        ordenar="codigo:asc",
    )
    assert len(primeira) == 2
    assert paginacao.tem_mais is True
    assert paginacao.proximo_cursor is not None

    segunda, _ = await servico.listar_jornadas(
        sessao_f3,
        contexto_f3.tenant_id,
        empresa_id=contexto_f3.empresa_id,
        cursor=paginacao.proximo_cursor,
        limite=2,
        ordenar="codigo:asc",
    )
    assert {j.id for j in primeira}.isdisjoint({j.id for j in segunda})


async def test_atualizar_jornada_troca_tipo(
    sessao_f3: AsyncSession, contexto_f3: ContextoF3
) -> None:
    dados = esquemas.JornadaCriar(
        empresa_id=contexto_f3.empresa_id,
        codigo="JOR-TROCA-TIPO",
        nome="Jornada flexivel",
        tipo=esquemas.Tipo14.livre,
        vigencia_inicio=dt.date(2026, 1, 1),
    )
    jornada = await servico.criar_jornada(sessao_f3, contexto_f3.tenant_id, dados)
    await sessao_f3.flush()

    atualizada = await servico.atualizar_jornada(
        sessao_f3, jornada.id, esquemas.JornadaAtualizar(tipo=esquemas.Tipo14.flexivel)
    )
    assert atualizada.tipo == "flexivel"


async def _criar_horario_auxiliar(
    sessao: AsyncSession, contexto: ContextoF3, codigo: str
) -> Horario:
    from app.jornada.modelagem import horarios as servico_horarios

    dados = esquemas.HorarioCriar(
        empresa_id=contexto.empresa_id,
        codigo=codigo,
        nome=f"Horario {codigo}",
        entrada="08:00",
        saida="17:00",
        carga_minutos=480,
    )
    horario = await servico_horarios.criar_horario(sessao, contexto.tenant_id, dados)
    await sessao.flush()
    return horario
