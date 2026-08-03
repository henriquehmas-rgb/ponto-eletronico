"""Testes do layout `generico_csv` (F13/A5, T15). Puro Python, sem banco:
o motor generico recebe `ContextoExportacaoFolha` ja materializado (ver
`app.integracoes.folha.comum.protocolo`), entao o teste confere campo a
campo contra a documentacao do proprio modulo sem precisar de fixture de
banco."""

from __future__ import annotations

import csv
import datetime as dt
import io
from decimal import Decimal
from uuid import uuid4

from app.integracoes.folha.comum.generico_csv import CABECALHO, DELIMITADOR, gerar
from app.integracoes.folha.comum.protocolo import ContextoExportacaoFolha, LinhaApuracaoFolha


def _linha(**overrides: object) -> LinhaApuracaoFolha:
    base: dict[str, object] = {
        "vinculo_id": uuid4(),
        "colaborador_id": uuid4(),
        "empresa_id": uuid4(),
        "unidade_id": None,
        "departamento_id": None,
        "departamento_codigo": None,
        "matricula": "000123",
        "cpf": "12345678901",
        "pis_nit": "12345678901",
        "nome_completo": "Colaborador Teste",
        "empresa_cnpj": "12345678000199",
        "data": dt.date(2026, 7, 15),
        "componente_codigo": "he_50",
        "componente_descricao": "Hora extra 50%",
        "categoria": "extra",
        "minutos": 60,
        "fator": Decimal("1.5000"),
        "minutos_equivalentes": 90,
        "origem": "marcacao",
        "rubrica": None,
    }
    base.update(overrides)
    return LinhaApuracaoFolha(**base)  # type: ignore[arg-type]


def _contexto(
    linhas: tuple[LinhaApuracaoFolha, ...], mapeamento: dict[str, object] | None = None
) -> ContextoExportacaoFolha:
    return ContextoExportacaoFolha(
        tenant_id=uuid4(),
        integracao_id=uuid4(),
        processamento_id=uuid4(),
        empresa_id=uuid4(),
        empresa_cnpj="12345678000199",
        parceiro="generico_csv",
        competencia_folha="2026-07",
        periodo_id=None,
        unidade_id=None,
        somente_fechados=True,
        periodo_inicio=dt.date(2026, 7, 1),
        periodo_fim=dt.date(2026, 7, 31),
        configuracao={},
        mapeamento_rubricas=mapeamento or {},
        linhas=linhas,
        gerado_em=dt.datetime.now(dt.UTC),
    )


def test_gera_cabecalho_com_nome_de_coluna() -> None:
    resultado = gerar(_contexto(()))
    texto = resultado.conteudo.decode("utf-8-sig")
    primeira_linha = texto.splitlines()[0]
    assert primeira_linha.split(DELIMITADOR) == list(CABECALHO)


def test_uma_linha_por_combinacao_vinculo_dia_componente() -> None:
    linhas = (
        _linha(componente_codigo="he_50", categoria="extra", minutos=60, minutos_equivalentes=90),
        _linha(
            componente_codigo="adicional_noturno",
            categoria="noturno",
            minutos=30,
            minutos_equivalentes=36,
        ),
    )
    resultado = gerar(_contexto(linhas))
    texto = resultado.conteudo.decode("utf-8-sig")
    linhas_csv = list(csv.reader(io.StringIO(texto), delimiter=DELIMITADOR))
    # cabecalho + 2 registros, um por componente -- nunca consolidado
    assert len(linhas_csv) == 3
    codigos = {linha[6] for linha in linhas_csv[1:]}
    assert codigos == {"he_50", "adicional_noturno"}


def test_campo_a_campo_contra_a_documentacao_do_modulo() -> None:
    linha = _linha(
        matricula="000456",
        cpf="98765432100",
        pis_nit="10987654321",
        nome_completo="Fulano de Tal",
        empresa_cnpj="11222333000144",
        data=dt.date(2026, 7, 20),
        componente_codigo="falta",
        componente_descricao="Falta injustificada",
        categoria="falta",
        minutos=480,
        fator=Decimal("1.0000"),
        minutos_equivalentes=480,
        origem="regra",
    )
    resultado = gerar(_contexto((linha,), mapeamento={"falta": "999"}))
    texto = resultado.conteudo.decode("utf-8-sig")
    linhas_csv = list(csv.reader(io.StringIO(texto), delimiter=DELIMITADOR))
    registro = dict(zip(CABECALHO, linhas_csv[1], strict=True))
    assert registro["matricula"] == "000456"
    assert registro["cpf"] == "98765432100"
    assert registro["pis"] == "10987654321"
    assert registro["nomeCompleto"] == "Fulano de Tal"
    assert registro["cnpjEmpresa"] == "11222333000144"
    assert registro["data"] == "2026-07-20"
    assert registro["componenteCodigo"] == "falta"
    assert registro["componenteDescricao"] == "Falta injustificada"
    assert registro["categoria"] == "falta"
    assert registro["minutos"] == "480"
    assert registro["fator"] == "1.0000"
    assert registro["minutosEquivalentes"] == "480"
    assert registro["origem"] == "regra"
    assert registro["rubrica"] == "999"


def test_rubrica_vazia_quando_sem_mapeamento() -> None:
    linha = _linha(componente_codigo="codigo_sem_mapeamento")
    resultado = gerar(_contexto((linha,), mapeamento={"outro_codigo": "111"}))
    texto = resultado.conteudo.decode("utf-8-sig")
    linhas_csv = list(csv.reader(io.StringIO(texto), delimiter=DELIMITADOR))
    registro = dict(zip(CABECALHO, linhas_csv[1], strict=True))
    assert registro["rubrica"] == ""


def test_delimitador_e_ponto_e_virgula_convencao_brasileira() -> None:
    resultado = gerar(_contexto((_linha(),)))
    texto = resultado.conteudo.decode("utf-8-sig")
    assert ";" in texto.splitlines()[0]
    assert "," not in texto.splitlines()[0]


def test_nome_arquivo_e_content_type() -> None:
    resultado = gerar(_contexto(()))
    assert resultado.nome_arquivo.startswith("integracoes-folha/")
    assert resultado.nome_arquivo.endswith(".csv")
    assert resultado.content_type == "text/csv; charset=utf-8"
