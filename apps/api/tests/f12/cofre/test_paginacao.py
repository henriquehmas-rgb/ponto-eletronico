"""Testes de `app.fiscal.cofre.paginacao` (F12/A3) -- cópia própria do
padrão de paginação por cursor já usado por outras fases. A maior parte
destas funções são puras (sem banco); só `executar_pagina` precisa de
sessão real, e já é exercitada indiretamente por `test_consulta.py`
(paginação em `listar_afd`) -- este arquivo cobre os ramos que os testes de
`consulta.py` não alcançam: limites/ordenação inválidos, cursor corrompido/
incompatível, e a direção `desc` de `executar_pagina`.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
import sqlalchemy as sa

from app.core.erros import ErroDeAplicacao
from app.fiscal.cofre.paginacao import (
    Ordenacao,
    codificar_cursor,
    decodificar_cursor,
    executar_pagina,
    interpretar_ordenar,
    montar_paginacao,
    normalizar_limite,
)


def test_normalizar_limite_none_usa_padrao() -> None:
    assert normalizar_limite(None) == 50


def test_normalizar_limite_dentro_da_faixa() -> None:
    assert normalizar_limite(1) == 1
    assert normalizar_limite(200) == 200
    assert normalizar_limite(75) == 75


@pytest.mark.parametrize("limite_invalido", [0, -1, 201, 1000])
def test_normalizar_limite_fora_da_faixa_e_val_005(limite_invalido: int) -> None:
    with pytest.raises(ErroDeAplicacao) as excinfo:
        normalizar_limite(limite_invalido)
    assert excinfo.value.codigo == "PONTO-VAL-005"


def test_interpretar_ordenar_ausente_usa_padrao_desc() -> None:
    ordenacao = interpretar_ordenar(None, campos_aceitos=frozenset({"geradoEm"}), padrao="geradoEm")
    assert ordenacao == Ordenacao(campo="geradoEm", direcao="desc")

    ordenacao_vazio = interpretar_ordenar(
        "", campos_aceitos=frozenset({"geradoEm"}), padrao="geradoEm"
    )
    assert ordenacao_vazio == Ordenacao(campo="geradoEm", direcao="desc")


def test_interpretar_ordenar_campo_sem_direcao_usa_asc() -> None:
    ordenacao = interpretar_ordenar(
        "periodoInicio", campos_aceitos=frozenset({"periodoInicio"}), padrao="geradoEm"
    )
    assert ordenacao == Ordenacao(campo="periodoInicio", direcao="asc")


def test_interpretar_ordenar_pega_so_o_primeiro_criterio_de_uma_lista() -> None:
    ordenacao = interpretar_ordenar(
        "periodoInicio:desc,geradoEm:asc",
        campos_aceitos=frozenset({"periodoInicio", "geradoEm"}),
        padrao="geradoEm",
    )
    assert ordenacao == Ordenacao(campo="periodoInicio", direcao="desc")


def test_interpretar_ordenar_direcao_invalida_e_val_005() -> None:
    with pytest.raises(ErroDeAplicacao) as excinfo:
        interpretar_ordenar(
            "geradoEm:lateral", campos_aceitos=frozenset({"geradoEm"}), padrao="geradoEm"
        )
    assert excinfo.value.codigo == "PONTO-VAL-005"


def test_interpretar_ordenar_campo_desconhecido_e_val_005() -> None:
    with pytest.raises(ErroDeAplicacao) as excinfo:
        interpretar_ordenar(
            "campoQueNaoExiste:asc", campos_aceitos=frozenset({"geradoEm"}), padrao="geradoEm"
        )
    assert excinfo.value.codigo == "PONTO-VAL-005"


def test_codificar_e_decodificar_cursor_roundtrip() -> None:
    ordenacao = Ordenacao(campo="geradoEm", direcao="desc")
    id_ = uuid.uuid4()
    valor = dt.datetime(2026, 7, 1, 12, 0, tzinfo=dt.UTC)

    cursor = codificar_cursor(ordenacao, valor, id_)
    valor_bruto, id_decodificado = decodificar_cursor(cursor, ordenacao=ordenacao)

    assert id_decodificado == id_
    assert valor_bruto == valor.isoformat()


def test_decodificar_cursor_ilegivel_e_val_006() -> None:
    with pytest.raises(ErroDeAplicacao) as excinfo:
        decodificar_cursor("!!!nao-e-base64!!!", ordenacao=Ordenacao(campo="a", direcao="asc"))
    assert excinfo.value.codigo == "PONTO-VAL-006"


def test_decodificar_cursor_ordenacao_incompativel_e_val_006() -> None:
    cursor = codificar_cursor(Ordenacao(campo="geradoEm", direcao="desc"), "x", uuid.uuid4())
    with pytest.raises(ErroDeAplicacao) as excinfo:
        decodificar_cursor(cursor, ordenacao=Ordenacao(campo="periodoInicio", direcao="desc"))
    assert excinfo.value.codigo == "PONTO-VAL-006"

    with pytest.raises(ErroDeAplicacao) as excinfo2:
        decodificar_cursor(cursor, ordenacao=Ordenacao(campo="geradoEm", direcao="asc"))
    assert excinfo2.value.codigo == "PONTO-VAL-006"


def test_decodificar_cursor_sem_id_e_val_006() -> None:
    import base64
    import json

    payload = {"o": "geradoEm", "d": "desc", "v": "x"}  # sem "id"
    bruto = json.dumps(payload).encode("utf-8")
    cursor = base64.urlsafe_b64encode(bruto).decode("ascii").rstrip("=")

    with pytest.raises(ErroDeAplicacao) as excinfo:
        decodificar_cursor(cursor, ordenacao=Ordenacao(campo="geradoEm", direcao="desc"))
    assert excinfo.value.codigo == "PONTO-VAL-006"


def test_montar_paginacao_campos_basicos() -> None:
    paginacao = montar_paginacao(proximo_cursor="abc", tem_mais=True, limite=10)
    assert paginacao.proximo_cursor == "abc"
    assert paginacao.tem_mais is True
    assert paginacao.limite == 10
    assert paginacao.cursor_anterior is None


@pytest.mark.asyncio
async def test_executar_pagina_direcao_desc_com_cursor(sessao_f12_a3, contexto_cofre) -> None:
    """Cobre o ramo `desc` de `executar_pagina` (o teste de `consulta.py`
    já cobre `asc` via `listar_afd`) -- cria um terceiro AFD, ordena por
    `geradoEm:desc` e confere que a segunda página (via cursor) devolve o
    item mais antigo."""
    from ponto_contracts import AfdArquivo

    from app.fiscal.cofre.consulta import _CAMPOS_ORDENACAO_AFD

    terceiro = AfdArquivo(
        tenant_id=contexto_cofre.contexto.tenant_id,
        empresa_id=contexto_cofre.contexto.empresa_id,
        rep_p_id=contexto_cofre.contexto.rep_p_id,
        periodo_inicio=dt.date(2026, 9, 1),
        periodo_fim=dt.date(2026, 9, 30),
        nsr_inicial=3,
        nsr_final=3,
        total_registros=1,
        nome_arquivo="AFD_TERCEIRO_DESC.txt",
        conteudo_ref="fiscal/teste/nao-importa-desc.txt",
        status="gerado",
        gerado_em=dt.datetime.now(dt.UTC) + dt.timedelta(seconds=1),
    )
    sessao_f12_a3.add(terceiro)
    await sessao_f12_a3.flush()

    ordenacao = Ordenacao(campo="geradoEm", direcao="desc")
    campo = _CAMPOS_ORDENACAO_AFD["geradoEm"]
    consulta_base = sa.select(AfdArquivo).where(
        AfdArquivo.tenant_id == contexto_cofre.contexto.tenant_id,
        AfdArquivo.rep_p_id == contexto_cofre.contexto.rep_p_id,
    )

    pagina1, tem_mais1 = await executar_pagina(
        sessao_f12_a3,
        consulta_base,
        ordenacao=ordenacao,
        campo=campo,
        coluna_id=AfdArquivo.id,
        cursor=None,
        limite=1,
    )
    assert len(pagina1) == 1
    assert tem_mais1 is True
    assert pagina1[0].id == terceiro.id  # o mais recente vem primeiro em desc

    cursor = codificar_cursor(ordenacao, pagina1[0].gerado_em, pagina1[0].id)
    pagina2, _tem_mais2 = await executar_pagina(
        sessao_f12_a3,
        consulta_base,
        ordenacao=ordenacao,
        campo=campo,
        coluna_id=AfdArquivo.id,
        cursor=cursor,
        limite=1,
    )
    assert len(pagina2) == 1
    assert pagina2[0].id != terceiro.id
