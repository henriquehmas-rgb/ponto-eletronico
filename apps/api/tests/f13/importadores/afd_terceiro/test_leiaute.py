"""T19 (A8) -- `app.integracoes.importadores.afd_terceiro.leiaute`: CRC-16/
KERMIT (algoritmo oficial do leiaute) e parsing dos campos `DH`/`D`."""

from __future__ import annotations

import datetime as dt

import pytest

from app.integracoes.importadores.afd_terceiro.leiaute import (
    CampoDhInvalido,
    crc16_kermit,
    crc16_kermit_hex,
    parsear_data,
    parsear_dh,
)


def test_crc16_kermit_vetor_oficial() -> None:
    """docs/leiaute-afd-aej.md §8.1, citação literal da fonte oficial:
    CRC-16("123456789") = 0x2189 com CRC-16/KERMIT."""
    assert crc16_kermit(b"123456789") == 0x2189


def test_crc16_kermit_hex_quatro_digitos_maiusculo() -> None:
    assert crc16_kermit_hex(b"123456789") == "2189"


def test_crc16_kermit_determinístico() -> None:
    dados = "linha de teste qualquer".encode("iso-8859-1")
    assert crc16_kermit(dados) == crc16_kermit(dados)


def test_crc16_kermit_sensivel_a_um_byte() -> None:
    a = crc16_kermit(b"AAAA")
    b = crc16_kermit(b"AAAB")
    assert a != b


def test_parsear_dh_exemplo_oficial() -> None:
    """Exemplo dado pela própria fonte oficial (docs/leiaute-afd-aej.md
    §6 regra 6): "2021-04-27T16:44:00-0300"."""
    resultado = parsear_dh("2021-04-27T16:44:00-0300")
    assert resultado.year == 2021
    assert resultado.month == 4
    assert resultado.day == 27
    assert resultado.hour == 16
    assert resultado.minute == 44
    assert resultado.second == 0
    assert resultado.utcoffset() == dt.timedelta(hours=-3)


def test_parsear_dh_formato_invalido_levanta() -> None:
    with pytest.raises(CampoDhInvalido):
        parsear_dh("nao e uma data valida       ")


def test_parsear_dh_tamanho_errado_levanta() -> None:
    with pytest.raises(CampoDhInvalido):
        parsear_dh("2021-04-27T16:44:00")  # sem fuso, 19 chars != 24


def test_parsear_data_valida() -> None:
    assert parsear_data("2026-01-01") == dt.date(2026, 1, 1)


def test_parsear_data_invalida_levanta() -> None:
    with pytest.raises(CampoDhInvalido):
        parsear_data("31-13-2026")
