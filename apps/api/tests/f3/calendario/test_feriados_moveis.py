"""Testes da funcao pura de feriados moveis (T5 do PCF da F3).

Cobre o criterio de aceite 6: as cinco ancoras moveis (pascoa, carnaval,
sexta_santa, corpus_christi, quarta_cinzas) para pelo menos dois anos
diferentes, com data esperada conferida a mao contra calendario oficial.
Nenhum destes testes toca banco -- `resolver_ancora_movel` e pura.
"""

from __future__ import annotations

import datetime as dt

import pytest

from app.jornada.calendario.feriados_moveis import data_pascoa, resolver_ancora_movel


# Datas oficiais conferidas a mao (calendario nacional brasileiro):
#   2024: Pascoa 31/03, Carnaval (terca) 13/02, Quarta de Cinzas 14/02,
#         Sexta-Feira Santa 29/03, Corpus Christi 30/05.
#   2025: Pascoa 20/04, Carnaval (terca) 04/03, Quarta de Cinzas 05/03,
#         Sexta-Feira Santa 18/04, Corpus Christi 19/06.
@pytest.mark.parametrize(
    ("ano", "esperado"),
    [
        (2024, dt.date(2024, 3, 31)),
        (2025, dt.date(2025, 4, 20)),
    ],
)
def test_data_pascoa_meeus_jones_butcher(ano: int, esperado: dt.date) -> None:
    assert data_pascoa(ano) == esperado


@pytest.mark.parametrize(
    ("ano", "esperado"),
    [
        (2024, dt.date(2024, 3, 31)),
        (2025, dt.date(2025, 4, 20)),
    ],
)
def test_resolver_ancora_pascoa(ano: int, esperado: dt.date) -> None:
    assert resolver_ancora_movel("pascoa", ano) == esperado


@pytest.mark.parametrize(
    ("ano", "esperado"),
    [
        (2024, dt.date(2024, 2, 13)),
        (2025, dt.date(2025, 3, 4)),
    ],
)
def test_resolver_ancora_carnaval(ano: int, esperado: dt.date) -> None:
    assert resolver_ancora_movel("carnaval", ano) == esperado


@pytest.mark.parametrize(
    ("ano", "esperado"),
    [
        (2024, dt.date(2024, 2, 14)),
        (2025, dt.date(2025, 3, 5)),
    ],
)
def test_resolver_ancora_quarta_cinzas(ano: int, esperado: dt.date) -> None:
    assert resolver_ancora_movel("quarta_cinzas", ano) == esperado


@pytest.mark.parametrize(
    ("ano", "esperado"),
    [
        (2024, dt.date(2024, 3, 29)),
        (2025, dt.date(2025, 4, 18)),
    ],
)
def test_resolver_ancora_sexta_santa(ano: int, esperado: dt.date) -> None:
    assert resolver_ancora_movel("sexta_santa", ano) == esperado


@pytest.mark.parametrize(
    ("ano", "esperado"),
    [
        (2024, dt.date(2024, 5, 30)),
        (2025, dt.date(2025, 6, 19)),
    ],
)
def test_resolver_ancora_corpus_christi(ano: int, esperado: dt.date) -> None:
    assert resolver_ancora_movel("corpus_christi", ano) == esperado


def test_resolver_ancora_custom_usa_pascoa_mais_offset() -> None:
    assert resolver_ancora_movel("custom", 2024, offset_dias=10) == dt.date(2024, 4, 10)


def test_resolver_ancora_offset_soma_a_qualquer_ancora() -> None:
    """`offset_dias` se soma a qualquer ancora, inclusive `pascoa` (PCF, secao 2)."""
    assert resolver_ancora_movel("pascoa", 2024, offset_dias=1) == dt.date(2024, 4, 1)
    assert resolver_ancora_movel("corpus_christi", 2024, offset_dias=-1) == dt.date(2024, 5, 29)


def test_virada_de_ano_nao_quebra_a_aritmetica() -> None:
    """Sanidade: a formula e aritmetica de data, nao string -- cruzar
    dezembro/janeiro (ex. corpus_christi com offset negativo grande) nao tem
    tratamento especial, exatamente como a virada de mes do 12x36 (PCF)."""
    resultado = resolver_ancora_movel("pascoa", 2024, offset_dias=-100)
    assert resultado < dt.date(2024, 3, 31)
    assert resultado.year in (2023, 2024)
