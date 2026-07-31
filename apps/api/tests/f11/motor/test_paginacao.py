"""Testes de `app.relatorios.paginacao` (T1/T2 -- cobertura do módulo
compartilhado de listagem) e da paginação real de `listarRelatorios`
(24 linhas semeadas, páginas pequenas cruzando o limite)."""

from __future__ import annotations

import uuid

import pytest

from app.core.erros import ErroDeAplicacao
from app.relatorios import execucao as execucao_servico
from app.relatorios import paginacao
from tests.f11.conftest import ContextoF11


def test_normalizar_limite_aplica_padrao_e_valida_faixa() -> None:
    assert paginacao.normalizar_limite(None) == paginacao.LIMITE_PADRAO
    assert paginacao.normalizar_limite(10) == 10
    with pytest.raises(ErroDeAplicacao) as excinfo:
        paginacao.normalizar_limite(0)
    assert excinfo.value.codigo == "PONTO-VAL-005"
    with pytest.raises(ErroDeAplicacao):
        paginacao.normalizar_limite(paginacao.LIMITE_MAXIMO + 1)


def test_interpretar_ordenar_valida_campo_e_direcao() -> None:
    ordenacao = paginacao.interpretar_ordenar(
        "nome:asc", campos_aceitos=frozenset({"nome", "codigo"}), padrao="codigo"
    )
    assert ordenacao.campo == "nome"
    assert ordenacao.direcao == "asc"

    padrao = paginacao.interpretar_ordenar(
        None, campos_aceitos=frozenset({"nome", "codigo"}), padrao="codigo"
    )
    assert padrao.campo == "codigo"
    assert padrao.direcao == "desc"

    with pytest.raises(ErroDeAplicacao) as excinfo:
        paginacao.interpretar_ordenar(
            "campoInvalido:asc", campos_aceitos=frozenset({"nome"}), padrao="nome"
        )
    assert excinfo.value.codigo == "PONTO-VAL-005"

    with pytest.raises(ErroDeAplicacao):
        paginacao.interpretar_ordenar(
            "nome:lateral", campos_aceitos=frozenset({"nome"}), padrao="nome"
        )


def test_cursor_roundtrip_e_erros() -> None:
    ordenacao = paginacao.Ordenacao(campo="codigo", direcao="asc")
    id_original = uuid.uuid4()
    cursor = paginacao.codificar_cursor(ordenacao, "espelho-jornada", id_original)
    valor, id_ = paginacao.decodificar_cursor(cursor, ordenacao=ordenacao)
    assert valor == "espelho-jornada"
    assert id_ == id_original

    with pytest.raises(ErroDeAplicacao) as excinfo:
        paginacao.decodificar_cursor("!!!nao-e-base64!!!", ordenacao=ordenacao)
    assert excinfo.value.codigo == "PONTO-VAL-006"

    outra_ordenacao = paginacao.Ordenacao(campo="nome", direcao="asc")
    with pytest.raises(ErroDeAplicacao) as excinfo:
        paginacao.decodificar_cursor(cursor, ordenacao=outra_ordenacao)
    assert excinfo.value.codigo == "PONTO-VAL-006"


async def test_listar_relatorios_pagina_pelas_24_linhas_semeadas(
    contexto_f11: ContextoF11, sessao_f11
) -> None:
    vistos: list[str] = []
    cursor = None
    paginas = 0
    while True:
        linhas, pag = await execucao_servico.listar_definicoes(
            sessao_f11, contexto_f11.tenant_id, cursor=cursor, limite=10
        )
        vistos.extend(linha.codigo for linha in linhas)
        paginas += 1
        if not pag.tem_mais:
            break
        cursor = pag.proximo_cursor
        assert cursor is not None
    assert paginas == 3  # 24 linhas, 10 por pagina -> 3 paginas (10+10+4)
    assert len(vistos) == 24
    assert len(set(vistos)) == 24  # nenhuma repetida entre paginas
