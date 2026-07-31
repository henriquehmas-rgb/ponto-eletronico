"""Testes do motor genérico (T2, critério de aceite oficial):

* o motor aplica filtro de período + escopo corretamente contra um dataset
  de exemplo;
* pedir colunas fora de `colunas_disponiveis` responde `PONTO-VAL-005`;
* agrupar por `departamento` soma corretamente contra dado sintético
  conhecido (soma calculada à mão, ver `tests/f11/conftest.py::
  ColaboradorF11`).

O dataset usado aqui é sintético, registrado só para este módulo
(`teste_motor_apuracao`) -- não colide com os 24 nomes reais do catálogo
(`_CATALOGO_RELATORIOS`, `conftest.py`), então não interfere com os testes
de dataset de A2/A3/A4 quando a suíte inteira roda junta.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
import sqlalchemy as sa
from ponto_contracts import ApuracaoDia, RelatorioDefinicao
from sqlalchemy import Select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.erros import ErroDeAplicacao
from app.relatorios import motor
from app.relatorios.catalogo import (
    AgrupamentoCatalogo,
    ColunaCatalogo,
    montar_agrupamentos,
    montar_colunas_disponiveis,
    montar_filtros_disponiveis,
    registrar_dataset,
)
from tests.f11.conftest import ContextoF11

_NOME_DATASET = "teste_motor_apuracao"


def _construtor_sintetico(
    sessao: AsyncSession, tenant_id: uuid.UUID, contexto: motor.ContextoConsulta
) -> Select[Any]:
    consulta = sa.select(
        ApuracaoDia.colaborador_id.label("colaboradorId"),
        ApuracaoDia.departamento_id.label("departamento"),
        ApuracaoDia.data.label("data"),
        ApuracaoDia.extras_minutos.label("extrasMinutos"),
        ApuracaoDia.trabalhado_minutos.label("trabalhadoMinutos"),
    ).where(ApuracaoDia.tenant_id == tenant_id)
    if contexto.de is not None:
        consulta = consulta.where(ApuracaoDia.data >= contexto.de)
    if contexto.ate is not None:
        consulta = consulta.where(ApuracaoDia.data <= contexto.ate)
    if contexto.colaborador_id is not None:
        consulta = consulta.where(ApuracaoDia.colaborador_id == contexto.colaborador_id)
    if contexto.departamento_id is not None:
        consulta = consulta.where(ApuracaoDia.departamento_id == contexto.departamento_id)
    return consulta


registrar_dataset(_NOME_DATASET, _construtor_sintetico)

_COLUNAS = [
    ColunaCatalogo("colaboradorId", "Colaborador", "uuid"),
    ColunaCatalogo("departamento", "Departamento", "uuid"),
    ColunaCatalogo("data", "Data", "data"),
    ColunaCatalogo("extrasMinutos", "Extras", "numero", True),
    ColunaCatalogo("trabalhadoMinutos", "Trabalhado", "numero", True),
]
_AGRUPAMENTOS = [AgrupamentoCatalogo("departamento", "Departamento")]


@pytest.fixture
async def definicao_sintetica(
    contexto_f11: ContextoF11, sessao_f11: AsyncSession
) -> RelatorioDefinicao:
    definicao = RelatorioDefinicao(
        id=uuid.uuid4(),
        tenant_id=contexto_f11.tenant_id,
        codigo="teste-motor",
        nome="Dataset sintetico de teste do motor",
        categoria="operacional",
        sistema=False,
        dataset=_NOME_DATASET,
        colunas_disponiveis=montar_colunas_disponiveis(_COLUNAS),
        filtros_disponiveis=montar_filtros_disponiveis([]),
        agrupamentos=montar_agrupamentos(_AGRUPAMENTOS),
        formatos=["csv", "xlsx", "pdf"],
        permissao_codigo="relatorios.executar",
        assincrono=False,
        ativo=True,
    )
    sessao_f11.add(definicao)
    await sessao_f11.flush()
    return definicao


async def test_motor_aplica_filtro_de_periodo_e_escopo(
    contexto_f11: ContextoF11, sessao_f11: AsyncSession, definicao_sintetica: RelatorioDefinicao
) -> None:
    colaborador_a = contexto_f11.colaboradores[0]
    contexto = motor.montar_contexto_consulta(
        contexto_f11.tenant_id,
        de=contexto_f11.dias_uteis[0],
        ate=contexto_f11.dias_uteis[-1],
        colaborador_id=colaborador_a.colaborador_id,
    )
    resultado = await motor.executar_dataset(
        sessao_f11, contexto_f11.tenant_id, definicao_sintetica, filtros=contexto
    )
    assert len(resultado.linhas) == 3
    assert all(linha["colaboradorId"] == colaborador_a.colaborador_id for linha in resultado.linhas)
    assert all(linha["extrasMinutos"] == 30 for linha in resultado.linhas)
    assert {linha["data"] for linha in resultado.linhas} == set(contexto_f11.dias_uteis)


async def test_motor_recusa_coluna_fora_do_catalogo(
    contexto_f11: ContextoF11, sessao_f11: AsyncSession, definicao_sintetica: RelatorioDefinicao
) -> None:
    contexto = motor.montar_contexto_consulta(contexto_f11.tenant_id)
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await motor.executar_dataset(
            sessao_f11,
            contexto_f11.tenant_id,
            definicao_sintetica,
            filtros=contexto,
            colunas=["campoInexistente"],
        )
    assert excinfo.value.codigo == "PONTO-VAL-005"


async def test_motor_recusa_agrupamento_nao_declarado(
    contexto_f11: ContextoF11, sessao_f11: AsyncSession, definicao_sintetica: RelatorioDefinicao
) -> None:
    contexto = motor.montar_contexto_consulta(contexto_f11.tenant_id)
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await motor.executar_dataset(
            sessao_f11,
            contexto_f11.tenant_id,
            definicao_sintetica,
            filtros=contexto,
            agrupamento="colaborador",
        )
    assert excinfo.value.codigo == "PONTO-VAL-005"


async def test_motor_agrupa_e_soma_corretamente_contra_soma_a_mao(
    contexto_f11: ContextoF11, sessao_f11: AsyncSession, definicao_sintetica: RelatorioDefinicao
) -> None:
    colaborador_a, colaborador_b, colaborador_c = contexto_f11.colaboradores
    dias = len(contexto_f11.dias_uteis)
    soma_operacoes_esperada = (
        colaborador_a.extras_minutos_por_dia + colaborador_b.extras_minutos_por_dia
    ) * dias
    soma_financeiro_esperada = colaborador_c.extras_minutos_por_dia * dias

    contexto = motor.montar_contexto_consulta(
        contexto_f11.tenant_id, de=contexto_f11.dias_uteis[0], ate=contexto_f11.dias_uteis[-1]
    )
    resultado = await motor.executar_dataset(
        sessao_f11,
        contexto_f11.tenant_id,
        definicao_sintetica,
        filtros=contexto,
        agrupamento="departamento",
    )

    por_departamento = {linha["departamento"]: linha for linha in resultado.linhas}
    assert len(por_departamento) == 2

    linha_operacoes = por_departamento[contexto_f11.departamento_operacoes_id]
    assert linha_operacoes["extrasMinutos"] == soma_operacoes_esperada
    assert linha_operacoes["quantidadeRegistros"] == 2 * dias  # 2 colaboradores x 3 dias

    linha_financeiro = por_departamento[contexto_f11.departamento_financeiro_id]
    assert linha_financeiro["extrasMinutos"] == soma_financeiro_esperada
    assert linha_financeiro["quantidadeRegistros"] == 1 * dias

    # trabalhadoMinutos tambem e coluna duracao=True: soma automaticamente.
    assert "trabalhadoMinutos" in linha_operacoes
    # colunas nao-duracao (colaboradorId/data) somem no modo agrupado --
    # comportamento documentado, nao bug (motor.py, docstring do modulo).
    assert "colaboradorId" not in linha_operacoes
    assert "data" not in linha_operacoes


async def test_motor_pagina_por_deslocamento(
    contexto_f11: ContextoF11, sessao_f11: AsyncSession, definicao_sintetica: RelatorioDefinicao
) -> None:
    contexto = motor.montar_contexto_consulta(
        contexto_f11.tenant_id, de=contexto_f11.dias_uteis[0], ate=contexto_f11.dias_uteis[-1]
    )
    primeira_pagina = await motor.executar_dataset(
        sessao_f11, contexto_f11.tenant_id, definicao_sintetica, filtros=contexto, limite=4
    )
    assert len(primeira_pagina.linhas) == 4
    assert primeira_pagina.tem_mais is True
    assert primeira_pagina.proximo_cursor is not None

    segunda_pagina = await motor.executar_dataset(
        sessao_f11,
        contexto_f11.tenant_id,
        definicao_sintetica,
        filtros=contexto,
        limite=4,
        cursor=primeira_pagina.proximo_cursor,
    )
    assert len(segunda_pagina.linhas) == 4
    assert segunda_pagina.tem_mais is True

    terceira_pagina = await motor.executar_dataset(
        sessao_f11,
        contexto_f11.tenant_id,
        definicao_sintetica,
        filtros=contexto,
        limite=4,
        cursor=segunda_pagina.proximo_cursor,
    )
    assert len(terceira_pagina.linhas) == 1  # 9 linhas no total (3 colaboradores x 3 dias)
    assert terceira_pagina.tem_mais is False
    assert terceira_pagina.total_linhas == 9

    # Nenhuma linha repetida entre paginas.
    todas = [
        (linha["colaboradorId"], linha["data"])
        for pagina in (primeira_pagina, segunda_pagina, terceira_pagina)
        for linha in pagina.linhas
    ]
    assert len(todas) == len(set(todas)) == 9
