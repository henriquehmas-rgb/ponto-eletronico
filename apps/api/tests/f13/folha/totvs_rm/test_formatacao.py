"""Testes da formatacao de baixo nivel compartilhada pelos tres exportadores
TOTVS (`app.integracoes.folha.totvs_rm._formatacao`, T17, agente A6)."""

from __future__ import annotations

from app.integracoes.folha.totvs_rm._formatacao import (
    DELIMITADOR_PADRAO,
    formatar_horas_decimais,
    montar_csv,
)


def test_delimitador_padrao_e_ponto_e_virgula() -> None:
    assert DELIMITADOR_PADRAO == ";"


def test_formatar_horas_zero() -> None:
    assert formatar_horas_decimais(0) == "0,00"


def test_formatar_horas_exato() -> None:
    assert formatar_horas_decimais(60) == "1,00"
    assert formatar_horas_decimais(90) == "1,50"
    assert formatar_horas_decimais(45) == "0,75"


def test_formatar_horas_negativas() -> None:
    assert formatar_horas_decimais(-30) == "-0,50"


def test_formatar_horas_arredondamento_comercial() -> None:
    # 1 minuto = 0.01666...h -> arredonda para 0,02 (ROUND_HALF_UP)
    assert formatar_horas_decimais(1) == "0,02"


def test_montar_csv_cabecalho_e_linhas() -> None:
    saida = montar_csv(("A", "B"), [("1", "2"), ("3", "4")])
    texto = saida.decode("utf-8-sig")
    assert texto.splitlines() == ["A;B", "1;2", "3;4"]


def test_montar_csv_delimitador_customizado() -> None:
    saida = montar_csv(("A", "B"), [("1", "2")], delimitador=",")
    texto = saida.decode("utf-8-sig")
    assert texto.splitlines() == ["A,B", "1,2"]


def test_montar_csv_tem_bom_utf8() -> None:
    saida = montar_csv(("A",), [])
    assert saida.startswith(b"\xef\xbb\xbf")


def test_montar_csv_preserva_acentuacao() -> None:
    saida = montar_csv(("Nome",), [("José",)])
    texto = saida.decode("utf-8-sig")
    assert "José" in texto


def test_montar_csv_terminador_crlf() -> None:
    saida = montar_csv(("A",), [("1",)])
    assert b"\r\n" in saida
