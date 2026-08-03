"""Teste do exportador Domínio (F13/A5, T16) -- melhor esforco, debito
tecnico documentado (ver docstring de `app.integracoes.folha.dominio`).
Confere que gera arquivo plausivel (mesmo conteudo/colunas do
`generico_csv`, so nome de arquivo proprio) -- NUNCA afirma fidelidade de
posicao de campo, porque nenhuma foi confirmada por fonte oficial."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from uuid import uuid4

from app.integracoes.folha.comum.generico_csv import CABECALHO
from app.integracoes.folha.comum.generico_csv import gerar as gerar_generico_csv
from app.integracoes.folha.comum.protocolo import ContextoExportacaoFolha, LinhaApuracaoFolha
from app.integracoes.folha.dominio.layout import gerar


def _linha() -> LinhaApuracaoFolha:
    return LinhaApuracaoFolha(
        vinculo_id=uuid4(),
        colaborador_id=uuid4(),
        empresa_id=uuid4(),
        unidade_id=None,
        departamento_id=None,
        departamento_codigo=None,
        matricula="000123",
        cpf="12345678901",
        pis_nit="12345678901",
        nome_completo="Colaborador Teste",
        empresa_cnpj="12345678000199",
        data=dt.date(2026, 7, 15),
        componente_codigo="he_50",
        componente_descricao="Hora extra 50%",
        categoria="extra",
        minutos=60,
        fator=Decimal("1.5000"),
        minutos_equivalentes=90,
        origem="marcacao",
        rubrica=None,
    )


def _contexto() -> ContextoExportacaoFolha:
    return ContextoExportacaoFolha(
        tenant_id=uuid4(),
        integracao_id=uuid4(),
        processamento_id=uuid4(),
        empresa_id=uuid4(),
        empresa_cnpj="12345678000199",
        parceiro="dominio",
        competencia_folha="2026-07",
        periodo_id=None,
        unidade_id=None,
        somente_fechados=True,
        periodo_inicio=dt.date(2026, 7, 1),
        periodo_fim=dt.date(2026, 7, 31),
        configuracao={},
        mapeamento_rubricas={},
        linhas=(_linha(),),
        gerado_em=dt.datetime.now(dt.UTC),
    )


def test_gera_arquivo_plausivel_com_mesmo_cabecalho_do_generico() -> None:
    contexto = _contexto()
    resultado = gerar(contexto)
    texto = resultado.conteudo.decode("utf-8-sig")
    primeira_linha = texto.splitlines()[0]
    assert primeira_linha.split(";") == list(CABECALHO)


def test_conteudo_identico_ao_generico_csv_so_muda_o_nome() -> None:
    contexto = _contexto()
    resultado_dominio = gerar(contexto)
    resultado_generico = gerar_generico_csv(contexto)
    assert resultado_dominio.conteudo == resultado_generico.conteudo
    assert resultado_dominio.nome_arquivo != resultado_generico.nome_arquivo
    assert "dominio-" in resultado_dominio.nome_arquivo


def test_debito_tecnico_documentado_no_modulo() -> None:
    """Nao e um teste de comportamento -- confere que a docstring do pacote
    registra explicitamente a ausencia de fonte oficial, mesmo padrao de
    honestidade exigido pelo PCF (secao 7, criterio 3 / secao 9, proibicao
    4). Falhar aqui e sinal de que alguem removeu a ressalva por engano."""
    import app.integracoes.folha.dominio as pacote_dominio

    docstring = pacote_dominio.__doc__ or ""
    assert "não pode ser descrito como" in docstring or "nao pode ser descrito como" in docstring
    assert "validado contra layout" in docstring
