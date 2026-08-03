"""Testes do exportador Senior (T18, agente A7, F13).

Testes puros de transformacao -- `layout.gerar()` so chama `generico_csv.
gerar` e troca o nome do arquivo; nao acessa banco nem rede, entao nao
depende de `apps/api/tests/f13/conftest.py` (fixture compartilhada da fase,
ownership de A1). A correcao do CONTEUDO do CSV em si (delimitador, BOM,
resolucao de rubrica, grao vinculo x dia x componente) e responsabilidade de
T15/A5 e e testada em `apps/api/tests/f13/folha/comum` -- este arquivo testa
so o que este modulo acrescenta: registro no motor generico e a convencao de
nome de arquivo do parceiro (ver debito tecnico completo no docstring de
`app.integracoes.folha.senior`).
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from uuid import uuid4

import app.integracoes.folha.senior as pacote_senior
from app.integracoes.folha.comum import registro
from app.integracoes.folha.comum.generico_csv import gerar as gerar_generico_csv
from app.integracoes.folha.comum.protocolo import ContextoExportacaoFolha, LinhaApuracaoFolha
from app.integracoes.folha.senior import layout


def _linha(**sobrescritas: object) -> LinhaApuracaoFolha:
    base: dict[str, object] = {
        "vinculo_id": uuid4(),
        "colaborador_id": uuid4(),
        "empresa_id": uuid4(),
        "unidade_id": None,
        "departamento_id": None,
        "departamento_codigo": None,
        "matricula": "00123",
        "cpf": "12345678909",
        "pis_nit": None,
        "nome_completo": "Jose da Silva",
        "empresa_cnpj": "12345678000190",
        "data": dt.date(2026, 7, 15),
        "componente_codigo": "he_50",
        "componente_descricao": "Hora extra 50%",
        "categoria": "extra",
        "minutos": 60,
        "fator": Decimal("1.5"),
        "minutos_equivalentes": 90,
        "origem": "marcacao",
        "rubrica": None,
    }
    base.update(sobrescritas)
    return LinhaApuracaoFolha(**base)  # type: ignore[arg-type]


def _contexto(**sobrescritas: object) -> ContextoExportacaoFolha:
    base: dict[str, object] = {
        "tenant_id": uuid4(),
        "integracao_id": uuid4(),
        "processamento_id": uuid4(),
        "empresa_id": uuid4(),
        "empresa_cnpj": "12345678000190",
        "parceiro": "senior",
        "competencia_folha": "2026-07",
        "periodo_id": None,
        "unidade_id": None,
        "somente_fechados": True,
        "periodo_inicio": dt.date(2026, 7, 1),
        "periodo_fim": dt.date(2026, 7, 31),
        "configuracao": {},
        "mapeamento_rubricas": {},
        "linhas": (_linha(),),
        "gerado_em": dt.datetime(2026, 8, 3, 12, 0, tzinfo=dt.UTC),
    }
    base.update(sobrescritas)
    return ContextoExportacaoFolha(**base)  # type: ignore[arg-type]


def test_parceiro_bate_com_enum_do_contrato() -> None:
    # `packages/contracts/schema.sql` (CHECK de `integracoes_folha.parceiro`)
    # e `packages/contracts/openapi.yaml` (`IntegracaoFolha.parceiro`) usam
    # exatamente este literal.
    assert layout.PARCEIRO == "senior"


def test_nunca_declarado_validado_contra_layout_do_parceiro() -> None:
    # Criterio de aceite 3 / proibicao 4 do PCF F13: nenhum dos cinco
    # parceiros de T18 pode ser descrito como "validado contra layout de
    # referencia do parceiro" -- so Alterdata (T16/A5) atinge esse padrao.
    assert layout.VALIDADO_CONTRA_LAYOUT_REFERENCIA is False


def test_registrado_no_motor_generico() -> None:
    # Importar `app.integracoes.folha.senior` (topo deste arquivo) ja
    # disparou `registro.registrar("senior", gerar)` no `__init__.py` do
    # pacote -- efeito colateral deliberado (PCF T15, mesmo padrao usado por
    # `app.integracoes.folha.dominio`).
    assert registro.obter_gerador("senior") is pacote_senior.gerar


def test_conteudo_identico_ao_motor_generico() -> None:
    contexto = _contexto()
    resultado = layout.gerar(contexto)
    referencia = gerar_generico_csv(contexto)
    assert resultado.conteudo == referencia.conteudo


def test_content_type_preservado_do_motor_generico() -> None:
    contexto = _contexto()
    resultado = layout.gerar(contexto)
    referencia = gerar_generico_csv(contexto)
    assert resultado.content_type == referencia.content_type


def test_nome_arquivo_identifica_o_parceiro() -> None:
    tenant_id = uuid4()
    integracao_id = uuid4()
    processamento_id = uuid4()
    contexto = _contexto(
        tenant_id=tenant_id,
        integracao_id=integracao_id,
        processamento_id=processamento_id,
        competencia_folha="2026-07",
    )
    resultado = layout.gerar(contexto)
    assert resultado.nome_arquivo == (
        f"integracoes-folha/{tenant_id}/{integracao_id}/senior-2026-07-{processamento_id}.csv"
    )


def test_nome_arquivo_muda_por_competencia() -> None:
    contexto_julho = _contexto(competencia_folha="2026-07")
    contexto_agosto = _contexto(competencia_folha="2026-08")
    assert layout.gerar(contexto_julho).nome_arquivo != layout.gerar(contexto_agosto).nome_arquivo


def test_exportar_varias_linhas_nao_quebra() -> None:
    contexto = _contexto(
        linhas=(
            _linha(componente_codigo="he_50"),
            _linha(
                componente_codigo="falta",
                categoria="falta",
                minutos=480,
                fator=Decimal("1.0"),
                minutos_equivalentes=480,
            ),
        )
    )
    resultado = layout.gerar(contexto)
    texto = resultado.conteudo.decode("utf-8-sig")
    assert len(texto.splitlines()) == 1 + 2  # cabecalho + 2 linhas


def test_exportar_sem_linhas_produz_so_cabecalho() -> None:
    contexto = _contexto(linhas=())
    resultado = layout.gerar(contexto)
    texto = resultado.conteudo.decode("utf-8-sig")
    assert len(texto.splitlines()) == 1
