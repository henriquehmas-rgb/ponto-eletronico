"""Testes de `app.jornada.modelagem.escalas` (F3 / A1, T3).

Cobre `posicao_do_ciclo` (teste de mesa puro, sem banco) para 5x2, 6x1, 4x2,
12x36 e uma rotativa de N dias com resultado esperado explicito por posicao,
e a validacao de cobertura de `ciclos` na criacao (PCF secao 6).
"""

from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.erros import ErroDeAplicacao
from app.jornada.modelagem import escalas as servico
from app.schemas import contrato as esquemas
from tests.f3.conftest import ContextoF3


def _escala(dias_ciclo: int) -> SimpleNamespace:
    return SimpleNamespace(dias_ciclo=dias_ciclo)


def _atribuicao(vigencia_inicio: dt.date, posicao_inicial: int) -> SimpleNamespace:
    return SimpleNamespace(vigencia_inicio=vigencia_inicio, posicao_inicial=posicao_inicial)


# ---------------------------------------------------------------------------
# posicao_do_ciclo -- teste de mesa puro (sem banco)
# ---------------------------------------------------------------------------


def test_posicao_do_ciclo_5x2() -> None:
    escala = _escala(dias_ciclo=7)
    atribuicao = _atribuicao(dt.date(2026, 1, 5), posicao_inicial=1)  # segunda-feira
    esperado = [1, 2, 3, 4, 5, 6, 7, 1, 2]
    obtido = [
        servico.posicao_do_ciclo(escala, atribuicao, dt.date(2026, 1, 5) + dt.timedelta(days=i))
        for i in range(len(esperado))
    ]
    assert obtido == esperado


def test_posicao_do_ciclo_6x1() -> None:
    escala = _escala(dias_ciclo=7)
    atribuicao = _atribuicao(dt.date(2026, 1, 1), posicao_inicial=1)
    obtido = [
        servico.posicao_do_ciclo(escala, atribuicao, dt.date(2026, 1, 1) + dt.timedelta(days=i))
        for i in range(8)
    ]
    assert obtido == [1, 2, 3, 4, 5, 6, 7, 1]


def test_posicao_do_ciclo_4x2() -> None:
    escala = _escala(dias_ciclo=6)
    atribuicao = _atribuicao(dt.date(2026, 1, 1), posicao_inicial=1)
    obtido = [
        servico.posicao_do_ciclo(escala, atribuicao, dt.date(2026, 1, 1) + dt.timedelta(days=i))
        for i in range(7)
    ]
    assert obtido == [1, 2, 3, 4, 5, 6, 1]


def test_posicao_do_ciclo_12x36_atravessa_virada_de_mes() -> None:
    """12x36: dias_ciclo=2 (posicao 1 trabalho, posicao 2 folga). Atribuicao
    com vigenciaInicio em janeiro, consultada cruzando para fevereiro --
    prova que a aritmetica e sobre diferenca de dias, nunca sobre
    dia-do-mes (PCF secao 2 e criterio de aceite 3)."""
    escala = _escala(dias_ciclo=2)
    atribuicao = _atribuicao(dt.date(2026, 1, 30), posicao_inicial=1)
    # 30/01 -> posicao 1 (trabalho); 31/01 -> posicao 2 (folga);
    # 01/02 -> posicao 1 (trabalho) de novo -- a virada de mes nao muda nada.
    assert servico.posicao_do_ciclo(escala, atribuicao, dt.date(2026, 1, 30)) == 1
    assert servico.posicao_do_ciclo(escala, atribuicao, dt.date(2026, 1, 31)) == 2
    assert servico.posicao_do_ciclo(escala, atribuicao, dt.date(2026, 2, 1)) == 1
    assert servico.posicao_do_ciclo(escala, atribuicao, dt.date(2026, 2, 2)) == 2


def test_posicao_do_ciclo_rotativa_n_dias_com_posicao_inicial_diferente() -> None:
    """Escala rotativa de 5 dias, duas equipes desencontradas: a equipe B
    entra na posicao 3 em vez de 1 (PCF: `posicao_inicial` e o que permite
    equipes desencontradas na mesma escala)."""
    escala = _escala(dias_ciclo=5)
    equipe_a = _atribuicao(dt.date(2026, 3, 1), posicao_inicial=1)
    equipe_b = _atribuicao(dt.date(2026, 3, 1), posicao_inicial=3)

    posicoes_a = [
        servico.posicao_do_ciclo(escala, equipe_a, dt.date(2026, 3, 1) + dt.timedelta(days=i))
        for i in range(5)
    ]
    posicoes_b = [
        servico.posicao_do_ciclo(escala, equipe_b, dt.date(2026, 3, 1) + dt.timedelta(days=i))
        for i in range(5)
    ]
    assert posicoes_a == [1, 2, 3, 4, 5]
    assert posicoes_b == [3, 4, 5, 1, 2]
    # Sanidade do PCF: em data == vigencia_inicio, posicao == posicao_inicial.
    assert posicoes_a[0] == equipe_a.posicao_inicial
    assert posicoes_b[0] == equipe_b.posicao_inicial


def test_posicao_do_ciclo_em_vigencia_inicio_e_sanidade() -> None:
    escala = _escala(dias_ciclo=7)
    atribuicao = _atribuicao(dt.date(2026, 5, 10), posicao_inicial=4)
    assert servico.posicao_do_ciclo(escala, atribuicao, dt.date(2026, 5, 10)) == 4


# ---------------------------------------------------------------------------
# Validacao de cobertura de ciclos (criterio de aceite da T3, com banco real)
# ---------------------------------------------------------------------------


async def test_criar_escala_12x36_com_ciclos_completos_e_aceita(
    sessao_f3: AsyncSession, contexto_f3: ContextoF3
) -> None:
    dados = esquemas.EscalaCriar(
        empresa_id=contexto_f3.empresa_id,
        codigo="ESC-12X36",
        nome="12x36",
        tipo=esquemas.Tipo20.field_12x36,
        dias_ciclo=2,
        data_referencia=dt.date(2026, 1, 1),
        ciclos=[
            esquemas.EscalaCiclo(posicao=1, tipo_dia=esquemas.TipoDia1.trabalho, carga_minutos=720),
            esquemas.EscalaCiclo(posicao=2, tipo_dia=esquemas.TipoDia1.folga, carga_minutos=0),
        ],
    )
    escala = await servico.criar_escala(sessao_f3, contexto_f3.tenant_id, dados)
    await sessao_f3.flush()
    ciclos = await servico.listar_ciclos_da_escala(sessao_f3, escala.id)
    assert len(ciclos) == 2
    assert {c.posicao for c in ciclos} == {1, 2}


async def test_criar_escala_faltando_posicao_do_ciclo_e_recusado(
    sessao_f3: AsyncSession, contexto_f3: ContextoF3
) -> None:
    dados = esquemas.EscalaCriar(
        empresa_id=contexto_f3.empresa_id,
        codigo="ESC-5X2-INCOMPLETA",
        nome="5x2 incompleta",
        tipo=esquemas.Tipo20.field_5x2,
        dias_ciclo=7,
        data_referencia=dt.date(2026, 1, 1),
        ciclos=[
            esquemas.EscalaCiclo(posicao=i, tipo_dia=esquemas.TipoDia1.trabalho, carga_minutos=480)
            for i in range(1, 6)  # faltam as posicoes 6 e 7
        ],
    )
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.criar_escala(sessao_f3, contexto_f3.tenant_id, dados)
    assert excinfo.value.codigo == "PONTO-VAL-001"


async def test_criar_escala_com_posicao_duplicada_e_recusado(
    sessao_f3: AsyncSession, contexto_f3: ContextoF3
) -> None:
    dados = esquemas.EscalaCriar(
        empresa_id=contexto_f3.empresa_id,
        codigo="ESC-4X2-DUPLICADA",
        nome="4x2 com posicao duplicada",
        tipo=esquemas.Tipo20.field_4x2,
        dias_ciclo=6,
        data_referencia=dt.date(2026, 1, 1),
        ciclos=[
            esquemas.EscalaCiclo(posicao=1, tipo_dia=esquemas.TipoDia1.trabalho, carga_minutos=480),
            esquemas.EscalaCiclo(posicao=1, tipo_dia=esquemas.TipoDia1.trabalho, carga_minutos=480),
            esquemas.EscalaCiclo(posicao=2, tipo_dia=esquemas.TipoDia1.trabalho, carga_minutos=480),
            esquemas.EscalaCiclo(posicao=3, tipo_dia=esquemas.TipoDia1.trabalho, carga_minutos=480),
            esquemas.EscalaCiclo(posicao=4, tipo_dia=esquemas.TipoDia1.folga, carga_minutos=0),
            esquemas.EscalaCiclo(posicao=5, tipo_dia=esquemas.TipoDia1.folga, carga_minutos=0),
        ],
    )
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.criar_escala(sessao_f3, contexto_f3.tenant_id, dados)
    assert excinfo.value.codigo == "PONTO-VAL-001"


async def test_excluir_escala_inexistente_e_rec_001(
    sessao_f3: AsyncSession, contexto_f3: ContextoF3
) -> None:
    import uuid

    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.excluir_escala(sessao_f3, contexto_f3.tenant_id, uuid.uuid4())
    assert excinfo.value.codigo == "PONTO-REC-001"


async def test_atualizar_escala_substitui_ciclos(
    sessao_f3: AsyncSession, contexto_f3: ContextoF3
) -> None:
    dados = esquemas.EscalaCriar(
        empresa_id=contexto_f3.empresa_id,
        codigo="ESC-ATUALIZAVEL",
        nome="Escala atualizavel",
        tipo=esquemas.Tipo20.field_5x2,
        dias_ciclo=7,
        data_referencia=dt.date(2026, 1, 1),
        ciclos=[
            esquemas.EscalaCiclo(posicao=i, tipo_dia=esquemas.TipoDia1.trabalho, carga_minutos=480)
            for i in range(1, 6)
        ]
        + [
            esquemas.EscalaCiclo(posicao=6, tipo_dia=esquemas.TipoDia1.folga, carga_minutos=0),
            esquemas.EscalaCiclo(posicao=7, tipo_dia=esquemas.TipoDia1.dsr, carga_minutos=0),
        ],
    )
    escala = await servico.criar_escala(sessao_f3, contexto_f3.tenant_id, dados)
    await sessao_f3.flush()

    atualizada = await servico.atualizar_escala(
        sessao_f3,
        escala.id,
        esquemas.EscalaAtualizar(
            nome="Renomeada",
            ciclos=[
                esquemas.EscalaCiclo(
                    posicao=i, tipo_dia=esquemas.TipoDia1.trabalho, carga_minutos=440
                )
                for i in range(1, 8)
            ],
        ),
    )
    assert atualizada.nome == "Renomeada"
    await sessao_f3.flush()
    ciclos = await servico.listar_ciclos_da_escala(sessao_f3, escala.id)
    assert {c.carga_minutos for c in ciclos} == {440}


async def test_excluir_escala_com_atribuicao_vigente_e_conf_004(
    sessao_f3: AsyncSession, contexto_f3: ContextoF3
) -> None:
    from app.jornada.modelagem import escala_atribuicoes

    dados = esquemas.EscalaCriar(
        empresa_id=contexto_f3.empresa_id,
        codigo="ESC-EM-USO",
        nome="Escala em uso",
        tipo=esquemas.Tipo20.field_12x36,
        dias_ciclo=2,
        data_referencia=dt.date(2026, 1, 1),
        ciclos=[
            esquemas.EscalaCiclo(posicao=1, tipo_dia=esquemas.TipoDia1.trabalho, carga_minutos=720),
            esquemas.EscalaCiclo(posicao=2, tipo_dia=esquemas.TipoDia1.folga, carga_minutos=0),
        ],
    )
    escala = await servico.criar_escala(sessao_f3, contexto_f3.tenant_id, dados)
    await sessao_f3.flush()

    atribuicao = esquemas.EscalaAtribuicaoCriar(
        vinculo_id=contexto_f3.vinculo_sp_id, vigencia_inicio=dt.date(2026, 1, 1)
    )
    await escala_atribuicoes.atribuir_escala_vinculo(
        sessao_f3, contexto_f3.tenant_id, escala.id, atribuicao
    )
    await sessao_f3.flush()

    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.excluir_escala(sessao_f3, contexto_f3.tenant_id, escala.id)
    assert excinfo.value.codigo == "PONTO-CONF-004"


async def test_listar_escalas_filtra_por_tipo(
    sessao_f3: AsyncSession, contexto_f3: ContextoF3
) -> None:
    dados = esquemas.EscalaCriar(
        empresa_id=contexto_f3.empresa_id,
        codigo="ESC-ESPANHOLA",
        nome="Escala espanhola",
        tipo=esquemas.Tipo20.espanhola,
        dias_ciclo=7,
        data_referencia=dt.date(2026, 1, 1),
    )
    await servico.criar_escala(sessao_f3, contexto_f3.tenant_id, dados)
    await sessao_f3.flush()

    linhas, _ = await servico.listar_escalas(
        sessao_f3, contexto_f3.tenant_id, empresa_id=contexto_f3.empresa_id, tipo="espanhola"
    )
    assert any(e.codigo == "ESC-ESPANHOLA" for e in linhas)


async def test_listar_escalas_filtra_por_ativo_e_pagina(
    sessao_f3: AsyncSession, contexto_f3: ContextoF3
) -> None:
    for i in range(3):
        dados = esquemas.EscalaCriar(
            empresa_id=contexto_f3.empresa_id,
            codigo=f"ESC-PAG-{i}",
            nome=f"Escala {i}",
            tipo=esquemas.Tipo20.rotativa,
            dias_ciclo=5,
            data_referencia=dt.date(2026, 1, 1),
            ativo=True,
        )
        await servico.criar_escala(sessao_f3, contexto_f3.tenant_id, dados)
    await sessao_f3.flush()

    primeira, paginacao = await servico.listar_escalas(
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

    segunda, _ = await servico.listar_escalas(
        sessao_f3,
        contexto_f3.tenant_id,
        empresa_id=contexto_f3.empresa_id,
        cursor=paginacao.proximo_cursor,
        limite=2,
        ordenar="codigo:asc",
    )
    assert {e.id for e in primeira}.isdisjoint({e.id for e in segunda})


async def test_dois_escalas_com_mesmo_codigo_colidem(
    sessao_f3: AsyncSession, contexto_f3: ContextoF3
) -> None:
    primeira = esquemas.EscalaCriar(
        empresa_id=contexto_f3.empresa_id,
        codigo="ESC-DUP",
        nome="Primeira",
        tipo=esquemas.Tipo20.field_6x1,
        dias_ciclo=7,
        data_referencia=dt.date(2026, 1, 1),
    )
    await servico.criar_escala(sessao_f3, contexto_f3.tenant_id, primeira)
    await sessao_f3.flush()

    segunda = esquemas.EscalaCriar(
        empresa_id=contexto_f3.empresa_id,
        codigo="ESC-DUP",
        nome="Segunda",
        tipo=esquemas.Tipo20.field_6x1,
        dias_ciclo=7,
        data_referencia=dt.date(2026, 1, 1),
    )
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.criar_escala(sessao_f3, contexto_f3.tenant_id, segunda)
    assert excinfo.value.codigo == "PONTO-CONF-001"


async def test_atualizar_escala_para_codigo_ja_usado_colide(
    sessao_f3: AsyncSession, contexto_f3: ContextoF3
) -> None:
    primeira = esquemas.EscalaCriar(
        empresa_id=contexto_f3.empresa_id,
        codigo="ESC-ORIGINAL",
        nome="Original",
        tipo=esquemas.Tipo20.field_4x2,
        dias_ciclo=6,
        data_referencia=dt.date(2026, 1, 1),
    )
    segunda = esquemas.EscalaCriar(
        empresa_id=contexto_f3.empresa_id,
        codigo="ESC-ALVO",
        nome="Alvo",
        tipo=esquemas.Tipo20.field_4x2,
        dias_ciclo=6,
        data_referencia=dt.date(2026, 1, 1),
    )
    await servico.criar_escala(sessao_f3, contexto_f3.tenant_id, primeira)
    escala_2 = await servico.criar_escala(sessao_f3, contexto_f3.tenant_id, segunda)
    await sessao_f3.flush()

    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.atualizar_escala(
            sessao_f3, escala_2.id, esquemas.EscalaAtualizar(codigo="ESC-ORIGINAL")
        )
    assert excinfo.value.codigo == "PONTO-CONF-001"
