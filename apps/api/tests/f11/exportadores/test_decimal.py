"""`app.relatorios.exportadores.decimal` (F11, T5/A3)."""

from __future__ import annotations

from app.relatorios.exportadores.decimal import (
    CASAS_DECIMAIS_PADRAO,
    minutos_para_horas_decimais,
)


def test_150_minutos_vira_2_50_horas() -> None:
    assert minutos_para_horas_decimais(150) == 2.5


def test_casas_decimais_padrao_e_2() -> None:
    assert CASAS_DECIMAIS_PADRAO == 2


def test_arredonda_meio_para_cima() -> None:
    # 5 minutos = 0.08333... horas -> arredonda para 0.08.
    assert minutos_para_horas_decimais(5) == 0.08
    # 100 minutos = 1.6666... horas -> arredonda para 1.67.
    assert minutos_para_horas_decimais(100) == 1.67


def test_preserva_sinal_negativo() -> None:
    assert minutos_para_horas_decimais(-90) == -1.5


def test_zero_minutos_e_zero_horas() -> None:
    assert minutos_para_horas_decimais(0) == 0.0


def test_casas_decimais_customizadas() -> None:
    assert minutos_para_horas_decimais(150, casas_decimais=0) == 3.0
    assert minutos_para_horas_decimais(150, casas_decimais=4) == 2.5
