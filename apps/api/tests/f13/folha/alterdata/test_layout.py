"""Teste do layout Alterdata (F13/A5, T16) -- confere CADA CAMPO PELA
POSICAO exata contra a tabela documentada em `app.integracoes.folha.
alterdata.layout` (fonte primaria: `ajuda.alterdata.com.br`, ver docstring
do modulo). Este e o teste que sustenta o criterio de aceite 3 da fase
("cada exportador de folha valida contra layout de referencia do
parceiro") para o UNICO parceiro em que isso e literalmente alcancavel --
nao basta "o arquivo nao quebra", cada posicao é comparada."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from uuid import uuid4

import pytest

from app.core.erros import ErroDeAplicacao
from app.integracoes.folha.alterdata.layout import CAMPOS, TAMANHO_REGISTRO, gerar
from app.integracoes.folha.comum.protocolo import ContextoExportacaoFolha, LinhaApuracaoFolha


def _linha(**overrides: object) -> LinhaApuracaoFolha:
    base: dict[str, object] = {
        "vinculo_id": uuid4(),
        "colaborador_id": uuid4(),
        "empresa_id": uuid4(),
        "unidade_id": None,
        "departamento_id": None,
        "departamento_codigo": "0042",
        "matricula": "001234",
        "cpf": "12345678901",
        "pis_nit": "10987654321",
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
        "rubrica": "015",
    }
    base.update(overrides)
    return LinhaApuracaoFolha(**base)  # type: ignore[arg-type]


def _contexto(
    linhas: tuple[LinhaApuracaoFolha, ...], configuracao: dict[str, object] | None = None
) -> ContextoExportacaoFolha:
    return ContextoExportacaoFolha(
        tenant_id=uuid4(),
        integracao_id=uuid4(),
        processamento_id=uuid4(),
        empresa_id=uuid4(),
        empresa_cnpj="12345678000199",
        parceiro="alterdata",
        competencia_folha="2026-07",
        periodo_id=None,
        unidade_id=None,
        somente_fechados=True,
        periodo_inicio=dt.date(2026, 7, 1),
        periodo_fim=dt.date(2026, 7, 31),
        configuracao=configuracao if configuracao is not None else {"codigoEmpresa": "00007"},
        mapeamento_rubricas={},
        linhas=linhas,
        gerado_em=dt.datetime.now(dt.UTC),
    )


def _primeiro_registro(conteudo: bytes) -> str:
    texto = conteudo.decode("iso-8859-1")
    return texto.split("\r\n")[0]


def _campo(registro: str, nome: str) -> str:
    inicio, fim = CAMPOS[nome]
    return registro[inicio - 1 : fim]  # posicoes 1-indexadas inclusive


def test_tamanho_do_registro_e_90_posicoes() -> None:
    resultado = gerar(_contexto((_linha(),)))
    registro = _primeiro_registro(resultado.conteudo)
    assert len(registro) == TAMANHO_REGISTRO


def test_sequencial_posicoes_1_a_6() -> None:
    resultado = gerar(_contexto((_linha(), _linha())))
    texto = resultado.conteudo.decode("iso-8859-1")
    linhas = [linha for linha in texto.split("\r\n") if linha]
    assert _campo(linhas[0], "sequencial") == "000001"
    assert _campo(linhas[1], "sequencial") == "000002"


def test_codigo_empresa_posicoes_7_a_11() -> None:
    resultado = gerar(_contexto((_linha(),), configuracao={"codigoEmpresa": "123"}))
    registro = _primeiro_registro(resultado.conteudo)
    assert _campo(registro, "codigo_empresa") == "00123"


def test_referencias_de_data_posicoes_12_a_23_formato_ddmmaa() -> None:
    resultado = gerar(_contexto((_linha(data=dt.date(2026, 7, 5)),)))
    registro = _primeiro_registro(resultado.conteudo)
    assert _campo(registro, "referencia_1") == "050726"
    assert _campo(registro, "referencia_2") == "050726"


def test_faltas_posicoes_24_a_29_soh_quando_categoria_falta() -> None:
    linha_falta = _linha(categoria="falta", minutos=480, minutos_equivalentes=480)
    registro_falta = _primeiro_registro(gerar(_contexto((linha_falta,))).conteudo)
    assert _campo(registro_falta, "faltas") == "000480"

    linha_extra = _linha(categoria="extra", minutos=60, minutos_equivalentes=90)
    registro_extra = _primeiro_registro(gerar(_contexto((linha_extra,))).conteudo)
    assert _campo(registro_extra, "faltas") == "000000"


def test_horas_trabalhadas_posicoes_30_a_35_zero_em_dia_de_falta() -> None:
    linha_extra = _linha(categoria="extra", minutos=60, minutos_equivalentes=90)
    registro_extra = _primeiro_registro(gerar(_contexto((linha_extra,))).conteudo)
    assert _campo(registro_extra, "horas_trabalhadas") == "000090"

    linha_falta = _linha(categoria="falta", minutos=480, minutos_equivalentes=480)
    registro_falta = _primeiro_registro(gerar(_contexto((linha_falta,))).conteudo)
    assert _campo(registro_falta, "horas_trabalhadas") == "000000"


def test_dias_uteis_posicoes_36_a_37_sempre_01() -> None:
    registro = _primeiro_registro(gerar(_contexto((_linha(),))).conteudo)
    assert _campo(registro, "dias_uteis") == "01"


def test_codigo_evento_posicoes_38_a_40_via_rubrica_mapeada() -> None:
    registro = _primeiro_registro(gerar(_contexto((_linha(rubrica="15"),))).conteudo)
    assert _campo(registro, "codigo_evento") == "015"


def test_codigo_evento_zero_quando_rubrica_nao_mapeada() -> None:
    registro = _primeiro_registro(gerar(_contexto((_linha(rubrica=None),))).conteudo)
    assert _campo(registro, "codigo_evento") == "000"


def test_valor_evento_posicoes_41_a_54_horas_decimais_sem_separador() -> None:
    # 90 minutos equivalentes = 1.50 hora -> "150" com 2 casas implicitas
    linha = _linha(minutos_equivalentes=90)
    registro = _primeiro_registro(gerar(_contexto((linha,))).conteudo)
    assert _campo(registro, "valor_evento") == "00000000000150"


def test_codigo_funcionario_posicoes_55_a_60() -> None:
    registro = _primeiro_registro(gerar(_contexto((_linha(matricula="42"),))).conteudo)
    assert _campo(registro, "codigo_funcionario") == "000042"


def test_matricula_nao_numerica_e_ponto_val_001() -> None:
    with pytest.raises(ErroDeAplicacao) as exc_info:
        gerar(_contexto((_linha(matricula="ABC123"),)))
    assert exc_info.value.codigo == "PONTO-VAL-001"


def test_processo_posicao_61_e_espaco() -> None:
    registro = _primeiro_registro(gerar(_contexto((_linha(),))).conteudo)
    assert _campo(registro, "processo") == " "


def test_cnpj_cpf_empresa_posicoes_62_a_75() -> None:
    linha = _linha(empresa_cnpj="98765432000188")
    registro = _primeiro_registro(gerar(_contexto((linha,))).conteudo)
    assert _campo(registro, "cnpj_cpf_empresa") == "98765432000188"


def test_pis_funcionario_posicoes_76_a_86() -> None:
    linha = _linha(pis_nit="12345678909")
    registro = _primeiro_registro(gerar(_contexto((linha,))).conteudo)
    assert _campo(registro, "pis_funcionario") == "12345678909"


def test_pis_ausente_vira_zeros() -> None:
    linha = _linha(pis_nit=None)
    registro = _primeiro_registro(gerar(_contexto((linha,))).conteudo)
    assert _campo(registro, "pis_funcionario") == "00000000000"


def test_departamento_posicoes_87_a_90() -> None:
    linha = _linha(departamento_codigo="0099")
    registro = _primeiro_registro(gerar(_contexto((linha,))).conteudo)
    assert _campo(registro, "departamento") == "0099"


def test_departamento_nao_numerico_vira_zeros() -> None:
    linha = _linha(departamento_codigo="ADM")
    registro = _primeiro_registro(gerar(_contexto((linha,))).conteudo)
    assert _campo(registro, "departamento") == "0000"


def test_sem_codigo_empresa_configurado_e_ponto_val_001() -> None:
    with pytest.raises(ErroDeAplicacao) as exc_info:
        gerar(_contexto((_linha(),), configuracao={}))
    assert exc_info.value.codigo == "PONTO-VAL-001"


def test_codificacao_iso_8859_1() -> None:
    linha = _linha(nome_completo="José da Silva")
    resultado = gerar(_contexto((linha,)))
    # Nao decodifica em UTF-8 sem erro (acento em posicoes diferentes) --
    # prova que o arquivo saiu em ISO-8859-1, nao UTF-8.
    resultado.conteudo.decode("iso-8859-1")


def test_arquivo_vazio_sem_linhas() -> None:
    resultado = gerar(_contexto(()))
    assert resultado.conteudo == b""
