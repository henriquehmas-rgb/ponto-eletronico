"""T1 -- casos de borda de `app.fiscal.comum.formatos` (módulo comum entre
AFD e AEJ, ownership de A1). Os casos "felizes" já são exercitados
indiretamente por todos os outros testes de A1 que montam registros; este
arquivo cobre os desvios (datetime ingênuo, caractere fora de Latin-1, lista
vazia).
"""

from __future__ import annotations

import datetime as dt

import pytest

from app.fiscal.comum.formatos import (
    TERMINADOR_LINHA,
    formatar_data,
    formatar_data_hora,
    montar_arquivo_texto,
)


def test_formatar_data() -> None:
    assert formatar_data(dt.date(2026, 7, 1)) == "2026-07-01"


def test_formatar_data_hora_exemplo_da_norma() -> None:
    """Exemplo dado pela própria fonte oficial (`docs/leiaute-afd-aej.md`
    §6 regra 6): "2021-04-27T16:44:00-0300"."""
    momento = dt.datetime(2021, 4, 27, 16, 44, 17, tzinfo=dt.timezone(dt.timedelta(hours=-3)))
    resultado = formatar_data_hora(momento)
    assert resultado == "2021-04-27T16:44:00-0300"
    assert len(resultado) == 24


def test_formatar_data_hora_trunca_segundos_para_00() -> None:
    momento = dt.datetime(2026, 1, 1, 0, 0, 59, tzinfo=dt.UTC)
    assert formatar_data_hora(momento).endswith(":00+0000")


def test_formatar_data_hora_fuso_positivo() -> None:
    momento = dt.datetime(2026, 1, 1, 12, 0, 0, tzinfo=dt.timezone(dt.timedelta(hours=9)))
    assert formatar_data_hora(momento).endswith("+0900")


def test_formatar_data_hora_datetime_ingenuo_levanta_erro() -> None:
    with pytest.raises(ValueError, match="fuso horario"):
        formatar_data_hora(dt.datetime(2026, 1, 1, 0, 0, 0))


def test_montar_arquivo_texto_lista_vazia() -> None:
    assert montar_arquivo_texto([]) == b""


def test_montar_arquivo_texto_termina_toda_linha_em_crlf() -> None:
    resultado = montar_arquivo_texto(["AAA", "BBB"])
    assert resultado == b"AAA" + TERMINADOR_LINHA + b"BBB" + TERMINADOR_LINHA


def test_montar_arquivo_texto_caractere_fora_de_latin1_levanta_erro() -> None:
    """Nomes em português usam só Latin-1 na prática, mas não é presumido:
    um emoji (fora do Latin-1) levanta erro explícito, não *mangling*."""
    with pytest.raises(ValueError, match="linha 2"):
        montar_arquivo_texto(["linha valida", "nome com emoji 🎉"])
