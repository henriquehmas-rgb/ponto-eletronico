"""Fecha o gap de cobertura de `app.apuracao.tratamento.paginacao` (T8, copia
propria do dominio `tratamento` -- ver docstring do modulo sob teste, e a de
`tests/f4/dominio/test_paginacao.py` para a copia irma).

A maior parte das funcoes deste modulo (`normalizar_limite`,
`interpretar_ordenar`, `codificar_cursor`/`decodificar_cursor`,
`montar_paginacao`) e pura e nao depende de banco: os testes abaixo cobrem os
ramos de erro (limite fora da faixa, campo/direcao de ordenacao invalidos,
cursor corrompido ou emitido para outra ordenacao) que os testes de
`app.apuracao.tratamento.servico` nunca exercitam (eles so chamam a primeira
pagina, sem cursor, com `ordenar=None`). So `executar_pagina` toca banco --
insere linhas reais em `tipos_tratamento` (via `INSERT` direto, mesmo padrao
de `conftest.py` deste subpacote) e pagina sobre elas com o motor de cursor
deste modulo diretamente, sem passar por `listar_tipos_tratamento`.
"""

from __future__ import annotations

import base64
import json
import uuid
from datetime import UTC, date, datetime
from typing import Any

import pytest
import sqlalchemy as sa
from ponto_contracts import TipoTratamento
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.apuracao.tratamento.paginacao import (
    CODIGO_CONSULTA_INVALIDA,
    CODIGO_CURSOR_INCOMPATIVEL,
    LIMITE_MAXIMO,
    LIMITE_PADRAO,
    CampoOrdenacao,
    Ordenacao,
    codificar_cursor,
    decodificar_cursor,
    executar_pagina,
    interpretar_ordenar,
    montar_paginacao,
    normalizar_limite,
)
from app.core.erros import ErroDeAplicacao
from tests.f4.tratamento.conftest import ContextoTratamento

_CODIGOS = ["PAG-TIPO-A", "PAG-TIPO-B", "PAG-TIPO-C"]


def _cursor_bruto(payload: Any) -> str:
    """Monta um cursor base64url a partir de um payload arbitrario, sem
    passar por `codificar_cursor` -- para simular cursores corrompidos ou
    emitidos por outra versao/formato."""
    bruto = json.dumps(payload).encode("utf-8")
    return base64.urlsafe_b64encode(bruto).decode("ascii").rstrip("=")


async def _inserir_tipo_tratamento(
    sessao: AsyncSession, *, id_: uuid.UUID, tenant_id: uuid.UUID, codigo: str
) -> None:
    await sessao.execute(
        text(
            "INSERT INTO tipos_tratamento "
            "(id, tenant_id, codigo, nome, categoria, exige_aprovacao, ativo) "
            "VALUES (:id, :tenant_id, :codigo, :nome, 'justificativa', TRUE, TRUE)"
        ),
        {"id": id_, "tenant_id": tenant_id, "codigo": codigo, "nome": f"Tipo {codigo}"},
    )


# ---------------------------------------------------------------------------
# normalizar_limite
# ---------------------------------------------------------------------------


def test_normalizar_limite_none_usa_padrao() -> None:
    assert normalizar_limite(None) == LIMITE_PADRAO


def test_normalizar_limite_aceita_os_extremos_da_faixa() -> None:
    assert normalizar_limite(1) == 1
    assert normalizar_limite(LIMITE_MAXIMO) == LIMITE_MAXIMO


@pytest.mark.parametrize("limite", [0, -1, LIMITE_MAXIMO + 1, 10_000])
def test_normalizar_limite_rejeita_fora_da_faixa(limite: int) -> None:
    with pytest.raises(ErroDeAplicacao) as exc_info:
        normalizar_limite(limite)
    assert exc_info.value.codigo == CODIGO_CONSULTA_INVALIDA


# ---------------------------------------------------------------------------
# interpretar_ordenar
# ---------------------------------------------------------------------------


def test_interpretar_ordenar_sem_parametro_usa_padrao_desc() -> None:
    ordenacao = interpretar_ordenar(None, campos_aceitos=frozenset({"codigo"}), padrao="codigo")
    assert ordenacao == Ordenacao(campo="codigo", direcao="desc")


def test_interpretar_ordenar_string_vazia_usa_padrao_desc() -> None:
    ordenacao = interpretar_ordenar("", campos_aceitos=frozenset({"codigo"}), padrao="codigo")
    assert ordenacao == Ordenacao(campo="codigo", direcao="desc")


def test_interpretar_ordenar_sem_direcao_usa_asc() -> None:
    ordenacao = interpretar_ordenar("codigo", campos_aceitos=frozenset({"codigo"}), padrao="codigo")
    assert ordenacao == Ordenacao(campo="codigo", direcao="asc")


def test_interpretar_ordenar_usa_somente_o_primeiro_criterio() -> None:
    ordenacao = interpretar_ordenar(
        "nome:asc,codigo:desc",
        campos_aceitos=frozenset({"codigo", "nome"}),
        padrao="codigo",
    )
    assert ordenacao == Ordenacao(campo="nome", direcao="asc")


def test_interpretar_ordenar_direcao_invalida_leva_a_erro() -> None:
    with pytest.raises(ErroDeAplicacao) as exc_info:
        interpretar_ordenar("codigo:lateral", campos_aceitos=frozenset({"codigo"}), padrao="codigo")
    assert exc_info.value.codigo == CODIGO_CONSULTA_INVALIDA


def test_interpretar_ordenar_campo_nao_aceito_leva_a_erro() -> None:
    with pytest.raises(ErroDeAplicacao) as exc_info:
        interpretar_ordenar(
            "campoInexistente:asc", campos_aceitos=frozenset({"codigo"}), padrao="codigo"
        )
    assert exc_info.value.codigo == CODIGO_CONSULTA_INVALIDA


# ---------------------------------------------------------------------------
# codificar_cursor / decodificar_cursor
# ---------------------------------------------------------------------------


def test_cursor_ida_e_volta_com_data() -> None:
    ordenacao = Ordenacao(campo="dataReferencia", direcao="asc")
    id_ = uuid.uuid4()
    cursor = codificar_cursor(ordenacao, date(2026, 1, 5), id_)
    valor, id_decodificado = decodificar_cursor(cursor, ordenacao=ordenacao)
    assert valor == "2026-01-05"
    assert id_decodificado == id_


def test_cursor_serializa_datetime_para_isoformat() -> None:
    ordenacao = Ordenacao(campo="criadoEm", direcao="desc")
    id_ = uuid.uuid4()
    momento = datetime(2026, 1, 5, 12, 30, tzinfo=UTC)
    cursor = codificar_cursor(ordenacao, momento, id_)
    valor, id_decodificado = decodificar_cursor(cursor, ordenacao=ordenacao)
    assert valor == momento.isoformat()
    assert id_decodificado == id_


def test_cursor_serializa_uuid_como_string() -> None:
    ordenacao = Ordenacao(campo="colaboradorId", direcao="asc")
    id_ = uuid.uuid4()
    valor_original = uuid.uuid4()
    cursor = codificar_cursor(ordenacao, valor_original, id_)
    valor, _ = decodificar_cursor(cursor, ordenacao=ordenacao)
    assert valor == str(valor_original)


def test_cursor_mantem_valores_ja_serializaveis() -> None:
    ordenacao = Ordenacao(campo="codigo", direcao="asc")
    id_ = uuid.uuid4()
    cursor = codificar_cursor(ordenacao, "PAG-TIPO-A", id_)
    valor, _ = decodificar_cursor(cursor, ordenacao=ordenacao)
    assert valor == "PAG-TIPO-A"


def test_decodificar_cursor_base64_corrompido_leva_a_erro() -> None:
    ordenacao = Ordenacao(campo="codigo", direcao="asc")
    with pytest.raises(ErroDeAplicacao) as exc_info:
        decodificar_cursor("@@@nao-e-base64@@@", ordenacao=ordenacao)
    assert exc_info.value.codigo == CODIGO_CURSOR_INCOMPATIVEL


def test_decodificar_cursor_payload_nao_e_json_leva_a_erro() -> None:
    ordenacao = Ordenacao(campo="codigo", direcao="asc")
    bruto = base64.urlsafe_b64encode(b"isto nao e json").decode("ascii").rstrip("=")
    with pytest.raises(ErroDeAplicacao) as exc_info:
        decodificar_cursor(bruto, ordenacao=ordenacao)
    assert exc_info.value.codigo == CODIGO_CURSOR_INCOMPATIVEL


def test_decodificar_cursor_payload_nao_e_dict_leva_a_erro() -> None:
    ordenacao = Ordenacao(campo="codigo", direcao="asc")
    with pytest.raises(ErroDeAplicacao) as exc_info:
        decodificar_cursor(_cursor_bruto(["nao", "e", "um", "dict"]), ordenacao=ordenacao)
    assert exc_info.value.codigo == CODIGO_CURSOR_INCOMPATIVEL


def test_decodificar_cursor_emitido_para_outro_campo_leva_a_erro() -> None:
    cursor = codificar_cursor(Ordenacao(campo="codigo", direcao="asc"), "PAG-TIPO-A", uuid.uuid4())
    with pytest.raises(ErroDeAplicacao) as exc_info:
        decodificar_cursor(cursor, ordenacao=Ordenacao(campo="nome", direcao="asc"))
    assert exc_info.value.codigo == CODIGO_CURSOR_INCOMPATIVEL


def test_decodificar_cursor_emitido_para_outra_direcao_leva_a_erro() -> None:
    cursor = codificar_cursor(Ordenacao(campo="codigo", direcao="asc"), "PAG-TIPO-A", uuid.uuid4())
    with pytest.raises(ErroDeAplicacao) as exc_info:
        decodificar_cursor(cursor, ordenacao=Ordenacao(campo="codigo", direcao="desc"))
    assert exc_info.value.codigo == CODIGO_CURSOR_INCOMPATIVEL


def test_decodificar_cursor_sem_id_leva_a_erro() -> None:
    ordenacao = Ordenacao(campo="codigo", direcao="asc")
    payload = {"o": "codigo", "d": "asc", "v": "PAG-TIPO-A"}
    with pytest.raises(ErroDeAplicacao) as exc_info:
        decodificar_cursor(_cursor_bruto(payload), ordenacao=ordenacao)
    assert exc_info.value.codigo == CODIGO_CURSOR_INCOMPATIVEL


def test_decodificar_cursor_com_id_invalido_leva_a_erro() -> None:
    ordenacao = Ordenacao(campo="codigo", direcao="asc")
    payload = {"o": "codigo", "d": "asc", "v": "PAG-TIPO-A", "id": "nao-e-um-uuid"}
    with pytest.raises(ErroDeAplicacao) as exc_info:
        decodificar_cursor(_cursor_bruto(payload), ordenacao=ordenacao)
    assert exc_info.value.codigo == CODIGO_CURSOR_INCOMPATIVEL


# ---------------------------------------------------------------------------
# montar_paginacao
# ---------------------------------------------------------------------------


def test_montar_paginacao_com_proxima_pagina() -> None:
    resultado = montar_paginacao(proximo_cursor="abc123", tem_mais=True, limite=50)
    assert resultado.proximo_cursor == "abc123"
    assert resultado.tem_mais is True
    assert resultado.limite == 50
    assert resultado.cursor_anterior is None
    assert resultado.total_estimado is None


def test_montar_paginacao_ultima_pagina() -> None:
    resultado = montar_paginacao(proximo_cursor=None, tem_mais=False, limite=50)
    assert resultado.proximo_cursor is None
    assert resultado.tem_mais is False


# ---------------------------------------------------------------------------
# executar_pagina (unica funcao do modulo que toca banco)
# ---------------------------------------------------------------------------


async def test_executar_pagina_sem_resultados(
    sessao_tratamento: AsyncSession, contexto_tratamento: ContextoTratamento
) -> None:
    ordenacao = Ordenacao(campo="codigo", direcao="asc")
    campo = CampoOrdenacao(TipoTratamento.codigo, str)
    consulta = sa.select(TipoTratamento).where(TipoTratamento.id == uuid.uuid4())

    linhas, tem_mais = await executar_pagina(
        sessao_tratamento,
        consulta,
        ordenacao=ordenacao,
        campo=campo,
        coluna_id=TipoTratamento.id,
        cursor=None,
        limite=50,
    )
    assert linhas == []
    assert tem_mais is False


async def test_executar_pagina_percorre_todas_as_paginas_por_cursor(
    sessao_tratamento: AsyncSession, contexto_tratamento: ContextoTratamento
) -> None:
    ids = [uuid.uuid4() for _ in _CODIGOS]
    for id_, codigo in zip(ids, _CODIGOS, strict=True):
        await _inserir_tipo_tratamento(
            sessao_tratamento, id_=id_, tenant_id=contexto_tratamento.tenant_id, codigo=codigo
        )
    # Sem commit: `set_config('app.tenant_id', ..., true)` (RLS, ver
    # `aplicar_tenant_teste`) e escopo de TRANSACAO -- commitar aqui reseta o
    # GUC e as linhas somem da proxima consulta sob RLS (mesmo motivo pelo
    # qual `contexto_tratamento` reaplica o tenant logo apos o seu commit).

    ordenacao = Ordenacao(campo="codigo", direcao="asc")
    campo = CampoOrdenacao(TipoTratamento.codigo, str)
    # Isola as 3 linhas criadas por este teste do `tipo_tratamento` ja
    # semeado por `contexto_tratamento` (mesmo tenant, codigo aleatorio).
    consulta = sa.select(TipoTratamento).where(TipoTratamento.id.in_(ids))

    pagina1, tem_mais1 = await executar_pagina(
        sessao_tratamento,
        consulta,
        ordenacao=ordenacao,
        campo=campo,
        coluna_id=TipoTratamento.id,
        cursor=None,
        limite=1,
    )
    assert [linha.codigo for linha in pagina1] == [_CODIGOS[0]]
    assert tem_mais1 is True

    cursor1 = codificar_cursor(ordenacao, pagina1[-1].codigo, pagina1[-1].id)
    pagina2, tem_mais2 = await executar_pagina(
        sessao_tratamento,
        consulta,
        ordenacao=ordenacao,
        campo=campo,
        coluna_id=TipoTratamento.id,
        cursor=cursor1,
        limite=1,
    )
    assert [linha.codigo for linha in pagina2] == [_CODIGOS[1]]
    assert tem_mais2 is True

    cursor2 = codificar_cursor(ordenacao, pagina2[-1].codigo, pagina2[-1].id)
    pagina3, tem_mais3 = await executar_pagina(
        sessao_tratamento,
        consulta,
        ordenacao=ordenacao,
        campo=campo,
        coluna_id=TipoTratamento.id,
        cursor=cursor2,
        limite=1,
    )
    assert [linha.codigo for linha in pagina3] == [_CODIGOS[2]]
    assert tem_mais3 is False
