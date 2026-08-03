"""Testes puros (sem banco) de `app.integracoes.folha.comum.paginacao`
(F13/A5, T15) -- cursor opaco, normalizacao de limite e interpretacao de
`ordenar`."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.core.erros import ErroDeAplicacao
from app.integracoes.folha.comum import paginacao as pag


def test_normalizar_limite_padrao() -> None:
    assert pag.normalizar_limite(None) == pag.LIMITE_PADRAO


def test_normalizar_limite_fora_da_faixa_e_ponto_val_005() -> None:
    with pytest.raises(ErroDeAplicacao) as exc_info:
        pag.normalizar_limite(0)
    assert exc_info.value.codigo == "PONTO-VAL-005"
    with pytest.raises(ErroDeAplicacao):
        pag.normalizar_limite(pag.LIMITE_MAXIMO + 1)


def test_interpretar_ordenar_padrao_quando_ausente() -> None:
    ordenacao = pag.interpretar_ordenar(None, campos_aceitos=frozenset({"nome"}), padrao="nome")
    assert ordenacao.campo == "nome"
    assert ordenacao.direcao == "desc"


def test_interpretar_ordenar_campo_e_direcao_explicitos() -> None:
    ordenacao = pag.interpretar_ordenar(
        "ultimaExportacaoEm:asc",
        campos_aceitos=frozenset({"nome", "ultimaExportacaoEm"}),
        padrao="nome",
    )
    assert ordenacao.campo == "ultimaExportacaoEm"
    assert ordenacao.direcao == "asc"


def test_interpretar_ordenar_campo_invalido_e_ponto_val_005() -> None:
    with pytest.raises(ErroDeAplicacao) as exc_info:
        pag.interpretar_ordenar(
            "campoInexistente:asc", campos_aceitos=frozenset({"nome"}), padrao="nome"
        )
    assert exc_info.value.codigo == "PONTO-VAL-005"


def test_interpretar_ordenar_direcao_invalida_e_ponto_val_005() -> None:
    with pytest.raises(ErroDeAplicacao) as exc_info:
        pag.interpretar_ordenar("nome:lateral", campos_aceitos=frozenset({"nome"}), padrao="nome")
    assert exc_info.value.codigo == "PONTO-VAL-005"


def test_cursor_roundtrip() -> None:
    ordenacao = pag.Ordenacao(campo="nome", direcao="asc")
    id_ = uuid4()
    cursor = pag.codificar_cursor(ordenacao, "Alguma Integracao", id_)
    valor, id_decodificado = pag.decodificar_cursor(cursor, ordenacao=ordenacao)
    assert valor == "Alguma Integracao"
    assert id_decodificado == id_


def test_cursor_com_ordenacao_diferente_e_incompativel() -> None:
    ordenacao = pag.Ordenacao(campo="nome", direcao="asc")
    cursor = pag.codificar_cursor(ordenacao, "X", uuid4())
    outra_ordenacao = pag.Ordenacao(campo="ultimaExportacaoEm", direcao="asc")
    with pytest.raises(ErroDeAplicacao) as exc_info:
        pag.decodificar_cursor(cursor, ordenacao=outra_ordenacao)
    assert exc_info.value.codigo == "PONTO-VAL-006"


def test_cursor_ilegivel_e_incompativel() -> None:
    ordenacao = pag.Ordenacao(campo="nome", direcao="asc")
    with pytest.raises(ErroDeAplicacao) as exc_info:
        pag.decodificar_cursor("!!!nao-e-base64!!!", ordenacao=ordenacao)
    assert exc_info.value.codigo == "PONTO-VAL-006"


def test_montar_paginacao() -> None:
    resposta = pag.montar_paginacao(proximo_cursor="abc", tem_mais=True, limite=50)
    assert resposta.proximo_cursor == "abc"
    assert resposta.tem_mais is True
    assert resposta.limite == 50
    assert resposta.cursor_anterior is None
