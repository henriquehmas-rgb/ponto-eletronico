"""Testes de `app.workflow.fechamento.paginacao` (F10/A2), diretos sobre as
funções do módulo -- antes deste arquivo, todo teste da fase só exercitava
`listar_fechamentos`/`listar_espelhos` com a página inteira cabendo em uma
tacada só (`ordenar`/`limite`/`cursor` sempre `None`), então
`interpretar_ordenar`/`normalizar_limite` só viam o caminho "nada informado"
e `codificar_cursor`/`decodificar_cursor`/o ramo de cursor de
`executar_pagina` nunca eram exercitados.
"""

from __future__ import annotations

import base64
import datetime as dt
import json
import uuid

import pytest
import sqlalchemy as sa
from ponto_contracts import Fechamento

from app.core.erros import ErroDeAplicacao
from app.workflow.fechamento import paginacao
from tests.f10.conftest import ContextoF10

# ---------------------------------------------------------------------------
# normalizar_limite
# ---------------------------------------------------------------------------


def test_normalizar_limite_none_usa_padrao() -> None:
    assert paginacao.normalizar_limite(None) == paginacao.LIMITE_PADRAO


def test_normalizar_limite_aceita_valor_na_faixa() -> None:
    assert paginacao.normalizar_limite(10) == 10
    assert paginacao.normalizar_limite(paginacao.LIMITE_MAXIMO) == paginacao.LIMITE_MAXIMO
    assert paginacao.normalizar_limite(1) == 1


def test_normalizar_limite_abaixo_da_faixa_e_val_005() -> None:
    with pytest.raises(ErroDeAplicacao) as excinfo:
        paginacao.normalizar_limite(0)
    assert excinfo.value.codigo == "PONTO-VAL-005"


def test_normalizar_limite_acima_da_faixa_e_val_005() -> None:
    with pytest.raises(ErroDeAplicacao) as excinfo:
        paginacao.normalizar_limite(paginacao.LIMITE_MAXIMO + 1)
    assert excinfo.value.codigo == "PONTO-VAL-005"


# ---------------------------------------------------------------------------
# interpretar_ordenar
# ---------------------------------------------------------------------------

_CAMPOS = frozenset({"criadoEm", "fechadoEm"})


def test_interpretar_ordenar_vazio_usa_padrao_desc() -> None:
    ordenacao = paginacao.interpretar_ordenar(None, campos_aceitos=_CAMPOS, padrao="criadoEm")
    assert ordenacao == paginacao.Ordenacao(campo="criadoEm", direcao="desc")


def test_interpretar_ordenar_campo_e_direcao_explicitos() -> None:
    ordenacao = paginacao.interpretar_ordenar(
        "fechadoEm:asc", campos_aceitos=_CAMPOS, padrao="criadoEm"
    )
    assert ordenacao == paginacao.Ordenacao(campo="fechadoEm", direcao="asc")


def test_interpretar_ordenar_sem_direcao_assume_asc() -> None:
    ordenacao = paginacao.interpretar_ordenar(
        "fechadoEm", campos_aceitos=_CAMPOS, padrao="criadoEm"
    )
    assert ordenacao == paginacao.Ordenacao(campo="fechadoEm", direcao="asc")


def test_interpretar_ordenar_direcao_invalida_e_val_005() -> None:
    with pytest.raises(ErroDeAplicacao) as excinfo:
        paginacao.interpretar_ordenar("criadoEm:lateral", campos_aceitos=_CAMPOS, padrao="criadoEm")
    assert excinfo.value.codigo == "PONTO-VAL-005"


def test_interpretar_ordenar_campo_invalido_e_val_005() -> None:
    with pytest.raises(ErroDeAplicacao) as excinfo:
        paginacao.interpretar_ordenar("inexistente:asc", campos_aceitos=_CAMPOS, padrao="criadoEm")
    assert excinfo.value.codigo == "PONTO-VAL-005"


# ---------------------------------------------------------------------------
# codificar_cursor / decodificar_cursor
# ---------------------------------------------------------------------------


def test_codificar_e_decodificar_cursor_round_trip_data() -> None:
    ordenacao = paginacao.Ordenacao(campo="criadoEm", direcao="desc")
    id_ = uuid.uuid4()
    valor = dt.datetime(2026, 1, 15, 12, 30, tzinfo=dt.UTC)
    cursor = paginacao.codificar_cursor(ordenacao, valor, id_)

    valor_bruto, id_decodificado = paginacao.decodificar_cursor(cursor, ordenacao=ordenacao)
    assert valor_bruto == valor.isoformat()
    assert id_decodificado == id_


def test_codificar_cursor_serializa_uuid() -> None:
    ordenacao = paginacao.Ordenacao(campo="codigo", direcao="asc")
    id_ = uuid.uuid4()
    valor_uuid = uuid.uuid4()
    cursor = paginacao.codificar_cursor(ordenacao, valor_uuid, id_)
    valor_bruto, _ = paginacao.decodificar_cursor(cursor, ordenacao=ordenacao)
    assert valor_bruto == str(valor_uuid)


def test_decodificar_cursor_ilegivel_e_val_006() -> None:
    ordenacao = paginacao.Ordenacao(campo="criadoEm", direcao="desc")
    with pytest.raises(ErroDeAplicacao) as excinfo:
        paginacao.decodificar_cursor("!!!nao-e-base64!!!", ordenacao=ordenacao)
    assert excinfo.value.codigo == "PONTO-VAL-006"


def _cursor_bruto(payload: dict) -> str:
    bruto = json.dumps(payload).encode("utf-8")
    return base64.urlsafe_b64encode(bruto).decode("ascii").rstrip("=")


def test_decodificar_cursor_ordenacao_incompativel_e_val_006() -> None:
    ordenacao = paginacao.Ordenacao(campo="criadoEm", direcao="desc")
    cursor_de_outro_campo = _cursor_bruto(
        {"o": "fechadoEm", "d": "desc", "v": "2026-01-01", "id": str(uuid.uuid4())}
    )
    with pytest.raises(ErroDeAplicacao) as excinfo:
        paginacao.decodificar_cursor(cursor_de_outro_campo, ordenacao=ordenacao)
    assert excinfo.value.codigo == "PONTO-VAL-006"


def test_decodificar_cursor_sem_id_valido_e_val_006() -> None:
    ordenacao = paginacao.Ordenacao(campo="criadoEm", direcao="desc")
    cursor_sem_id = _cursor_bruto({"o": "criadoEm", "d": "desc", "v": "2026-01-01"})
    with pytest.raises(ErroDeAplicacao) as excinfo:
        paginacao.decodificar_cursor(cursor_sem_id, ordenacao=ordenacao)
    assert excinfo.value.codigo == "PONTO-VAL-006"


# ---------------------------------------------------------------------------
# executar_pagina -- ramo do cursor (keyset real contra o banco)
# ---------------------------------------------------------------------------


async def _criar_fechamento_bruto(
    sessao, contexto: ContextoF10, *, criado_em: dt.datetime
) -> Fechamento:
    fechamento = Fechamento(
        tenant_id=contexto.tenant_id,
        periodo_id=contexto.periodo_id,
        empresa_id=contexto.empresa_id,
        escopo="empresa",
        status="em_andamento",
        criado_em=criado_em,
    )
    sessao.add(fechamento)
    await sessao.flush()
    return fechamento


@pytest.mark.asyncio
async def test_executar_pagina_usa_o_cursor_para_a_segunda_pagina(
    sessao_f10, contexto_f10: ContextoF10
) -> None:
    agora = dt.datetime.now(tz=dt.UTC)
    mais_antigo = await _criar_fechamento_bruto(
        sessao_f10, contexto_f10, criado_em=agora - dt.timedelta(minutes=2)
    )
    mais_novo = await _criar_fechamento_bruto(
        sessao_f10, contexto_f10, criado_em=agora - dt.timedelta(minutes=1)
    )

    ordenacao = paginacao.Ordenacao(campo="criadoEm", direcao="desc")
    campo = paginacao.CampoOrdenacao(Fechamento.criado_em, dt.datetime.fromisoformat)
    consulta = sa.select(Fechamento).where(
        Fechamento.tenant_id == contexto_f10.tenant_id,
        Fechamento.periodo_id == contexto_f10.periodo_id,
    )

    primeira_pagina, tem_mais = await paginacao.executar_pagina(
        sessao_f10,
        consulta,
        ordenacao=ordenacao,
        campo=campo,
        coluna_id=Fechamento.id,
        cursor=None,
        limite=1,
    )
    assert tem_mais is True
    assert [f.id for f in primeira_pagina] == [mais_novo.id]

    ultimo_da_primeira_pagina = primeira_pagina[-1]
    cursor = paginacao.codificar_cursor(
        ordenacao, ultimo_da_primeira_pagina.criado_em, ultimo_da_primeira_pagina.id
    )

    segunda_pagina, tem_mais_2 = await paginacao.executar_pagina(
        sessao_f10,
        consulta,
        ordenacao=ordenacao,
        campo=campo,
        coluna_id=Fechamento.id,
        cursor=cursor,
        limite=1,
    )
    assert tem_mais_2 is False
    assert [f.id for f in segunda_pagina] == [mais_antigo.id]


def test_montar_paginacao() -> None:
    resposta = paginacao.montar_paginacao(proximo_cursor="abc", tem_mais=True, limite=50)
    assert resposta.proximo_cursor == "abc"
    assert resposta.tem_mais is True
    assert resposta.limite == 50
    assert resposta.cursor_anterior is None
    assert resposta.total_estimado is None
