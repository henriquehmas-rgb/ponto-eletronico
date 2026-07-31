"""Testes diretos de `app.fiscal.rep_p.paginacao` (cópia self-contained do
mesmo módulo usado em outros domínios do projeto -- aqui testado no
contexto de `fiscal.rep_p`, ownership de A1)."""

from __future__ import annotations

import datetime as dt
import uuid

import pytest

from app.core.erros import ErroDeAplicacao
from app.fiscal.rep_p.paginacao import (
    LIMITE_MAXIMO,
    LIMITE_PADRAO,
    Ordenacao,
    codificar_cursor,
    decodificar_cursor,
    interpretar_ordenar,
    montar_paginacao,
    normalizar_limite,
)


def test_normalizar_limite_none_usa_padrao() -> None:
    assert normalizar_limite(None) == LIMITE_PADRAO


def test_normalizar_limite_dentro_da_faixa() -> None:
    assert normalizar_limite(10) == 10


@pytest.mark.parametrize("limite", [0, -1, LIMITE_MAXIMO + 1])
def test_normalizar_limite_fora_da_faixa_levanta_erro(limite: int) -> None:
    with pytest.raises(ErroDeAplicacao) as excinfo:
        normalizar_limite(limite)
    assert excinfo.value.codigo == "PONTO-VAL-005"


def test_interpretar_ordenar_ausente_usa_padrao_desc() -> None:
    resultado = interpretar_ordenar(
        None, campos_aceitos=frozenset({"identificador"}), padrao="identificador"
    )
    assert resultado == Ordenacao(campo="identificador", direcao="desc")


def test_interpretar_ordenar_campo_explicito() -> None:
    resultado = interpretar_ordenar(
        "identificador:asc",
        campos_aceitos=frozenset({"identificador", "dataInicioOperacao"}),
        padrao="dataInicioOperacao",
    )
    assert resultado == Ordenacao(campo="identificador", direcao="asc")


def test_interpretar_ordenar_direcao_invalida() -> None:
    with pytest.raises(ErroDeAplicacao) as excinfo:
        interpretar_ordenar(
            "identificador:lateral",
            campos_aceitos=frozenset({"identificador"}),
            padrao="identificador",
        )
    assert excinfo.value.codigo == "PONTO-VAL-005"


def test_interpretar_ordenar_campo_nao_aceito() -> None:
    with pytest.raises(ErroDeAplicacao) as excinfo:
        interpretar_ordenar(
            "campoInexistente", campos_aceitos=frozenset({"identificador"}), padrao="identificador"
        )
    assert excinfo.value.codigo == "PONTO-VAL-005"


def test_cursor_round_trip_com_data() -> None:
    ordenacao = Ordenacao(campo="dataInicioOperacao", direcao="desc")
    id_ = uuid.uuid4()
    cursor = codificar_cursor(ordenacao, dt.date(2026, 7, 1), id_)
    valor, id_decodificado = decodificar_cursor(cursor, ordenacao=ordenacao)
    assert valor == "2026-07-01"
    assert id_decodificado == id_


def test_cursor_round_trip_com_uuid_como_valor() -> None:
    ordenacao = Ordenacao(campo="identificador", direcao="asc")
    id_ = uuid.uuid4()
    outro_uuid = uuid.uuid4()
    cursor = codificar_cursor(ordenacao, outro_uuid, id_)
    valor, id_decodificado = decodificar_cursor(cursor, ordenacao=ordenacao)
    assert valor == str(outro_uuid)
    assert id_decodificado == id_


def test_cursor_ilegivel_levanta_erro() -> None:
    ordenacao = Ordenacao(campo="identificador", direcao="asc")
    with pytest.raises(ErroDeAplicacao) as excinfo:
        decodificar_cursor("!!!nao-e-base64!!!", ordenacao=ordenacao)
    assert excinfo.value.codigo == "PONTO-VAL-006"


def test_cursor_de_outra_ordenacao_e_recusado() -> None:
    ordenacao_original = Ordenacao(campo="identificador", direcao="asc")
    cursor = codificar_cursor(ordenacao_original, "REPP-01", uuid.uuid4())

    ordenacao_diferente = Ordenacao(campo="dataInicioOperacao", direcao="asc")
    with pytest.raises(ErroDeAplicacao) as excinfo:
        decodificar_cursor(cursor, ordenacao=ordenacao_diferente)
    assert excinfo.value.codigo == "PONTO-VAL-006"


def test_montar_paginacao() -> None:
    paginacao = montar_paginacao(proximo_cursor="abc", tem_mais=True, limite=50)
    assert paginacao.proximo_cursor == "abc"
    assert paginacao.tem_mais is True
    assert paginacao.limite == 50
