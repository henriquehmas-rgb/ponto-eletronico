"""Fecha o gap de cobertura de `app.apuracao.tratamento.erros_bd` (T8):
`_nome_constraint`/`traduzir_integridade` so tem sentido contra uma violacao
REAL do Postgres -- e o que os 3 primeiros testes fazem, forcando cada uma
das 3 categorias do mapa `CODIGOS_POR_CONSTRAINT` (unicidade, `CHECK` e
chave estrangeira) contra o banco de teste e conferindo que o `ErroDeAplicacao`
resultante tem o codigo certo do catalogo.

`asyncpg` sempre preenche `constraint_name` no erro nativo para estas 3
categorias (`asyncpg.exceptions._base.py`, campo de diagnostico `'n'`), entao
a violacao real nunca exercita o ramo de busca textual (linhas 30-34 de
`_nome_constraint`, usado quando o driver NAO preenche o atributo) nem o
`return None` de constraint desconhecida -- os 3 ultimos testes cobrem esses
dois ramos com um `IntegrityError` fabricado em memoria, sem tocar banco.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.apuracao.tratamento.erros_bd import _nome_constraint, traduzir_integridade
from tests.f4.tratamento.conftest import ContextoTratamento

_DATA_REFERENCIA = date(2026, 3, 10)


# ---------------------------------------------------------------------------
# Violacoes reais contra o banco de teste
# ---------------------------------------------------------------------------


async def test_traduz_violacao_de_unicidade_de_codigo_de_tipo_tratamento(
    sessao_tratamento: AsyncSession, contexto_tratamento: ContextoTratamento
) -> None:
    codigo_duplicado = f"DUP-{uuid.uuid4().hex[:8]}"
    insercao = text(
        "INSERT INTO tipos_tratamento "
        "(id, tenant_id, codigo, nome, categoria, exige_aprovacao, ativo) "
        "VALUES (:id, :tenant_id, :codigo, 'Tipo duplicado', 'justificativa', TRUE, TRUE)"
    )
    await sessao_tratamento.execute(
        insercao,
        {
            "id": uuid.uuid4(),
            "tenant_id": contexto_tratamento.tenant_id,
            "codigo": codigo_duplicado,
        },
    )

    with pytest.raises(IntegrityError) as exc_info:
        await sessao_tratamento.execute(
            insercao,
            {
                "id": uuid.uuid4(),
                "tenant_id": contexto_tratamento.tenant_id,
                "codigo": codigo_duplicado,
            },
        )
    await sessao_tratamento.rollback()

    erro = traduzir_integridade(exc_info.value)
    assert erro.codigo == "PONTO-CONF-001"
    assert erro.contexto_log["constraint"] == "uq_tipos_tratamento_codigo"


async def test_traduz_violacao_de_check_de_sentido_do_tratamento(
    sessao_tratamento: AsyncSession, contexto_tratamento: ContextoTratamento
) -> None:
    with pytest.raises(IntegrityError) as exc_info:
        await sessao_tratamento.execute(
            text(
                "INSERT INTO tratamentos "
                "(id, tenant_id, colaborador_id, vinculo_id, tipo_tratamento_id, "
                " data_referencia, motivo, sentido) "
                "VALUES (:id, :tenant_id, :colaborador_id, :vinculo_id, :tipo_tratamento_id, "
                "        :data_referencia, :motivo, :sentido)"
            ),
            {
                "id": uuid.uuid4(),
                "tenant_id": contexto_tratamento.tenant_id,
                "colaborador_id": contexto_tratamento.colaborador_id,
                "vinculo_id": contexto_tratamento.vinculo_id,
                "tipo_tratamento_id": contexto_tratamento.tipo_tratamento_id,
                "data_referencia": _DATA_REFERENCIA,
                "motivo": "Teste de violacao de CHECK",
                "sentido": "situacao_nao_existe",
            },
        )
    await sessao_tratamento.rollback()

    erro = traduzir_integridade(exc_info.value)
    assert erro.codigo == "PONTO-VAL-001"
    assert erro.contexto_log["constraint"] == "tratamentos_sentido_check"


async def test_traduz_violacao_de_fk_de_marcacao_do_tratamento(
    sessao_tratamento: AsyncSession, contexto_tratamento: ContextoTratamento
) -> None:
    marcacao_id_inexistente = uuid.uuid4()
    with pytest.raises(IntegrityError) as exc_info:
        await sessao_tratamento.execute(
            text(
                "INSERT INTO tratamentos "
                "(id, tenant_id, colaborador_id, vinculo_id, tipo_tratamento_id, "
                " data_referencia, motivo, marcacao_id, marcacao_datahora) "
                "VALUES (:id, :tenant_id, :colaborador_id, :vinculo_id, :tipo_tratamento_id, "
                "        :data_referencia, :motivo, :marcacao_id, :marcacao_datahora)"
            ),
            {
                "id": uuid.uuid4(),
                "tenant_id": contexto_tratamento.tenant_id,
                "colaborador_id": contexto_tratamento.colaborador_id,
                "vinculo_id": contexto_tratamento.vinculo_id,
                "tipo_tratamento_id": contexto_tratamento.tipo_tratamento_id,
                "data_referencia": _DATA_REFERENCIA,
                "motivo": "Teste de violacao de FK",
                # `ck_tratamentos_marcacao` exige o par completo -- os dois
                # nao-nulos aqui satisfazem o CHECK e deixam a FK (que
                # referencia uma marcacao que nao existe) ser o unico erro.
                "marcacao_id": marcacao_id_inexistente,
                "marcacao_datahora": datetime.now(UTC),
            },
        )
    await sessao_tratamento.rollback()

    erro = traduzir_integridade(exc_info.value)
    assert erro.codigo == "PONTO-REC-001"
    assert erro.contexto_log["constraint"] == "fk_tratamentos_marcacao"


# ---------------------------------------------------------------------------
# `_nome_constraint`: ramo de busca textual e desconhecido (sem banco)
# ---------------------------------------------------------------------------


def test_nome_constraint_usa_atributo_quando_o_driver_o_preenche() -> None:
    class _OrigemComAtributo(Exception):
        constraint_name = "uq_tipos_tratamento_codigo"

    assert _nome_constraint(_OrigemComAtributo("mensagem qualquer")) == "uq_tipos_tratamento_codigo"


def test_nome_constraint_cai_para_busca_textual_sem_o_atributo() -> None:
    origem = Exception(
        'duplicate key value violates unique constraint "uq_tipos_tratamento_codigo"'
    )
    assert getattr(origem, "constraint_name", None) is None
    assert _nome_constraint(origem) == "uq_tipos_tratamento_codigo"


def test_nome_constraint_devolve_none_quando_nao_reconhece_nenhuma() -> None:
    origem = Exception("erro generico, nenhuma constraint conhecida na mensagem")
    assert _nome_constraint(origem) is None


def test_traduzir_integridade_usa_o_codigo_padrao_quando_constraint_nao_mapeada() -> None:
    exc = IntegrityError("INSERT INTO x", {}, Exception("erro sem constraint reconhecida"))
    erro = traduzir_integridade(exc)
    assert erro.codigo == "PONTO-CONF-001"
    assert erro.contexto_log == {"constraint": None}
