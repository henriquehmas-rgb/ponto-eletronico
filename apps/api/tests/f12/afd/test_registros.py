"""T4 -- registros AFD de largura fixa: tipos 1, 2, 4, 5, 6, 9 e a linha de
assinatura. Tamanhos exatos conferidos contra `docs/leiaute-afd-aej.md` §7.
"""

from __future__ import annotations

import datetime as dt

import pytest

from app.fiscal.afd.crc16 import crc16_ccitt
from app.fiscal.afd.registros import (
    montar_linha_assinatura,
    montar_registro_tipo1,
    montar_registro_tipo2,
    montar_registro_tipo4,
    montar_registro_tipo5,
    montar_registro_tipo6,
    montar_trailer_tipo9,
    preencher_alfanumerico,
    preencher_numerico,
)
from app.fiscal.comum.formatos import CODIFICACAO_LEIAUTE

_FUSO = dt.timezone(dt.timedelta(hours=-3))


def test_preencher_numerico_zero_a_esquerda() -> None:
    assert preencher_numerico("7", 9) == "000000007"


def test_preencher_numerico_levanta_erro_se_maior_que_o_campo() -> None:
    with pytest.raises(ValueError, match="excede"):
        preencher_numerico("12345678901234567890", 9)


def test_preencher_alfanumerico_espaco_a_direita() -> None:
    resultado = preencher_alfanumerico("SEEG", 10)
    assert resultado == "SEEG      "
    assert len(resultado) == 10


def test_preencher_alfanumerico_levanta_erro_se_maior_que_o_campo() -> None:
    with pytest.raises(ValueError, match="excede"):
        preencher_alfanumerico("nome muito comprido demais para o campo", 5)


def test_ordenacao_lexicografica_do_nsr_zero_padded_bate_com_numerica() -> None:
    """Motivo real de `MODO_PREENCHIMENTO_NUMERICO='zero_esquerda'` ser o
    padrão (§2.9 do PCF): "2" + espacos ordenaria DEPOIS de "10" + espacos
    numa comparacao de string, o que seria numericamente errado -- com
    zero a esquerda a ordenacao lexicografica bate com a numerica."""
    dois = preencher_numerico("2", 9)
    dez = preencher_numerico("10", 9)
    assert dois < dez  # comparacao de string
    assert 2 < 10  # comparacao numerica -- as duas concordam


class TestRegistroTipo1:
    def _montar(self, **kwargs: object) -> str:
        base: dict[str, object] = {
            "tipo_identificador_empregador": "1",
            "cnpj_ou_cpf_empregador": "60258502000230",
            "cno_ou_caepf": None,
            "razao_social_empregador": "Empresa de Teste F12 Ltda",
            "numero_inpi": "512026000123456",
            "periodo_inicio": dt.date(2026, 7, 1),
            "periodo_fim": dt.date(2026, 7, 31),
            "gerado_em": dt.datetime(2026, 8, 1, 8, 0, 0, tzinfo=_FUSO),
            "tipo_identificador_fabricante": "1",
            "cnpj_ou_cpf_fabricante": "60258502000149",
        }
        base.update(kwargs)
        return montar_registro_tipo1(**base)  # type: ignore[arg-type]

    def test_tamanho_302(self) -> None:
        assert len(self._montar()) == 302

    def test_comeca_com_constante_e_tipo(self) -> None:
        linha = self._montar()
        assert linha[0:9] == "000000000"
        assert linha[9:10] == "1"

    def test_crc16_bate_com_o_corpo_sem_crc(self) -> None:
        linha = self._montar()
        corpo, crc_gravado = linha[:-4], linha[-4:]
        esperado = format(crc16_ccitt(corpo.encode(CODIFICACAO_LEIAUTE)), "04X")
        assert crc_gravado == esperado

    def test_campo_7_e_o_numero_do_inpi_para_rep_p(self) -> None:
        linha = self._montar()
        # Campo 7: posicoes 190-206 (17 caracteres), 1-indexado.
        campo7 = linha[189:206]
        assert campo7 == preencher_numerico("512026000123456", 17)


def test_registro_tipo2_tamanho_331_e_crc_valido() -> None:
    linha = montar_registro_tipo2(
        nsr=42,
        gravado_em=dt.datetime(2026, 7, 1, 8, 0, 0, tzinfo=_FUSO),
        cpf_responsavel="12345678901",
        tipo_identificador_empregador="1",
        cnpj_ou_cpf_empregador="60258502000230",
        cno_ou_caepf=None,
        razao_social_empregador="Empresa de Teste F12 Ltda",
        local_prestacao_servicos="Sede administrativa",
    )
    assert len(linha) == 331
    corpo, crc_gravado = linha[:-4], linha[-4:]
    assert crc_gravado == format(crc16_ccitt(corpo.encode(CODIFICACAO_LEIAUTE)), "04X")
    assert linha[9:10] == "2"


def test_registro_tipo4_tamanho_73_e_crc_valido() -> None:
    linha = montar_registro_tipo4(
        nsr=7,
        antes_do_ajuste=dt.datetime(2026, 7, 1, 8, 0, 0, tzinfo=_FUSO),
        apos_o_ajuste=dt.datetime(2026, 7, 1, 8, 5, 0, tzinfo=_FUSO),
        cpf_responsavel="12345678901",
    )
    assert len(linha) == 73
    corpo, crc_gravado = linha[:-4], linha[-4:]
    assert crc_gravado == format(crc16_ccitt(corpo.encode(CODIFICACAO_LEIAUTE)), "04X")
    assert linha[9:10] == "4"


def test_registro_tipo5_tamanho_118_e_crc_valido() -> None:
    linha = montar_registro_tipo5(
        nsr=9,
        gravado_em=dt.datetime(2026, 7, 1, 8, 0, 0, tzinfo=_FUSO),
        tipo_operacao="I",
        cpf_empregado="12345678901",
        nome_empregado="Colaborador de Teste F12",
        cpf_responsavel="98765432100",
    )
    assert len(linha) == 118
    corpo, crc_gravado = linha[:-4], linha[-4:]
    assert crc_gravado == format(crc16_ccitt(corpo.encode(CODIFICACAO_LEIAUTE)), "04X")
    assert linha[9:10] == "5"
    assert linha[34:35] == "I"


def test_registro_tipo6_tamanho_36_sem_crc() -> None:
    linha = montar_registro_tipo6(
        nsr=3, gravado_em=dt.datetime(2026, 7, 1, 8, 0, 0, tzinfo=_FUSO), tipo_evento="07"
    )
    assert len(linha) == 36
    assert linha[9:10] == "6"
    assert linha[34:36] == "07"


def test_registro_tipo6_evento_desconhecido_levanta_erro() -> None:
    with pytest.raises(ValueError, match="desconhecido"):
        montar_registro_tipo6(
            nsr=3, gravado_em=dt.datetime(2026, 7, 1, 8, 0, 0, tzinfo=_FUSO), tipo_evento="99"
        )


class TestTrailerTipo9:
    def test_tamanho_64(self) -> None:
        assert len(montar_trailer_tipo9()) == 64

    def test_comeca_com_constante_999999999_e_termina_em_9(self) -> None:
        linha = montar_trailer_tipo9(qtd_tipo7=1234)
        assert linha[0:9] == "999999999"
        assert linha[-1] == "9"

    def test_nao_conta_tipo1_nem_tipo9_de_si_mesmo(self) -> None:
        """A nota da tabela do leiaute diz que o trailer nao conta o
        cabecalho (tipo 1, sempre 1) nem a si mesmo (tipo 9, sempre 1) --
        nao ha parametro `qtd_tipo1`/`qtd_tipo9` na assinatura da funcao,
        o que e a prova de que esses dois nunca entram na soma."""
        import inspect

        parametros = set(inspect.signature(montar_trailer_tipo9).parameters)
        assert "qtd_tipo1" not in parametros
        assert "qtd_tipo9" not in parametros

    def test_contagens_batem_nas_posicoes_certas(self) -> None:
        linha = montar_trailer_tipo9(
            qtd_tipo2=1, qtd_tipo3=2, qtd_tipo4=3, qtd_tipo5=4, qtd_tipo6=5, qtd_tipo7=8421
        )
        assert linha[9:18] == preencher_numerico("1", 9)
        assert linha[18:27] == preencher_numerico("2", 9)
        assert linha[27:36] == preencher_numerico("3", 9)
        assert linha[36:45] == preencher_numerico("4", 9)
        assert linha[45:54] == preencher_numerico("5", 9)
        assert linha[54:63] == preencher_numerico("8421", 9)


def test_linha_de_assinatura_tem_100_caracteres_e_texto_literal() -> None:
    linha = montar_linha_assinatura()
    assert len(linha) == 100
    assert linha.startswith("ASSINATURA_DIGITAL_EM_ARQUIVO_P7S")
    assert linha.strip() == "ASSINATURA_DIGITAL_EM_ARQUIVO_P7S"
