"""Testes puros (sem banco) de `app.integracoes.sandbox.dados_sinteticos`
(F13/A2, T8)."""

from __future__ import annotations

import datetime as dt

from app.integracoes.sandbox.dados_sinteticos import (
    COLABORADORES_SINTETICOS,
    cpf_sintetico,
    gerar_dias_uteis,
    gerar_plano_de_marcacoes,
    matricula_sintetica,
)


def test_colaboradores_sinteticos_tem_matricula_e_cpf_unicos() -> None:
    matriculas = {matricula_sintetica(c) for c in COLABORADORES_SINTETICOS}
    cpfs = {cpf_sintetico(c) for c in COLABORADORES_SINTETICOS}
    assert len(matriculas) == len(COLABORADORES_SINTETICOS)
    assert len(cpfs) == len(COLABORADORES_SINTETICOS)
    for cpf in cpfs:
        assert len(cpf) == 11
        assert cpf.isdigit()


def test_gerar_dias_uteis_pula_fim_de_semana() -> None:
    # 2026-08-03 e uma segunda-feira (confirmado pelo `currentDate` da sessao).
    segunda = dt.date(2026, 8, 3)
    dias = gerar_dias_uteis(terminando_em=segunda, quantidade=6)
    assert len(dias) == 6
    for dia in dias:
        assert dia.weekday() < 5
    # Deve andar para tras o suficiente para atravessar o fim de semana anterior.
    assert dias[0] < dias[-1]
    assert dias == sorted(dias)


def test_gerar_dias_uteis_e_deterministico() -> None:
    fim = dt.date(2026, 8, 3)
    primeira = gerar_dias_uteis(terminando_em=fim, quantidade=10)
    segunda = gerar_dias_uteis(terminando_em=fim, quantidade=10)
    assert primeira == segunda


def test_gerar_plano_de_marcacoes_quatro_batimentos_por_dia() -> None:
    dias = gerar_dias_uteis(terminando_em=dt.date(2026, 8, 3), quantidade=3)
    plano = gerar_plano_de_marcacoes(dias)
    assert len(plano) == 3 * 4
    horas = {b.hora for b in plano if b.data == dias[0]}
    assert horas == {dt.time(8, 0), dt.time(12, 0), dt.time(13, 0), dt.time(18, 0)}
