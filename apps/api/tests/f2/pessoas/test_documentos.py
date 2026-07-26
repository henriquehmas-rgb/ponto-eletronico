"""Testes de `app.comum.documentos` (T1): digito verificador de CPF, CNPJ e
PIS/PASEP/NIT, e a recusa de sequencias de digito repetido.

Nao depende de banco: e validacao pura de string. Cobre o criterio de aceite
2 da fase ("Validacao de CPF, CNPJ e PIS por digito verificador... rejeitando
tambem as sequencias de digito repetido").
"""

from __future__ import annotations

import pytest

from app.comum.documentos import cnpj_valido, cpf_valido, pis_valido, somente_digitos


class TestSomenteDigitos:
    def test_remove_mascara(self) -> None:
        assert somente_digitos("111.444.777-35") == "11144477735"

    def test_remove_espacos_e_letras(self) -> None:
        assert somente_digitos(" 12.345/6789-01 abc") == "12345678901"

    def test_string_vazia(self) -> None:
        assert somente_digitos("") == ""


class TestCpfValido:
    @pytest.mark.parametrize(
        "cpf",
        [
            "111.444.777-35",  # exemplo classico de CPF valido, usado em QA
            "11144477735",
            "52998224725",
        ],
    )
    def test_cpf_valido_aceito(self, cpf: str) -> None:
        assert cpf_valido(cpf) is True

    def test_cpf_com_mascara_e_aceito_e_normalizado_para_so_digitos(self) -> None:
        mascarado = "111.444.777-35"
        assert cpf_valido(mascarado) is True
        assert somente_digitos(mascarado) == "11144477735"

    @pytest.mark.parametrize(
        "cpf",
        [
            "111.444.777-34",  # digito verificador errado
            "123.456.789-00",
            "1234567890",  # 10 digitos
            "123456789012",  # 12 digitos
            "",
            "abc.def.ghi-jk",
        ],
    )
    def test_cpf_invalido_recusado(self, cpf: str) -> None:
        assert cpf_valido(cpf) is False

    @pytest.mark.parametrize("digito", ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9"])
    def test_sequencia_de_digito_repetido_e_sempre_recusada(self, digito: str) -> None:
        """`00000000000`, `11111111111`, ... batem no digito verificador por
        construcao matematica do modulo 11, mas nao sao CPF valido."""
        assert cpf_valido(digito * 11) is False


class TestCnpjValido:
    @pytest.mark.parametrize(
        "cnpj",
        [
            "11.222.333/0001-81",  # exemplo classico de CNPJ valido, usado em QA
            "11222333000181",
        ],
    )
    def test_cnpj_valido_aceito(self, cnpj: str) -> None:
        assert cnpj_valido(cnpj) is True

    @pytest.mark.parametrize(
        "cnpj",
        [
            "11.222.333/0001-82",
            "1234567890123",  # 13 digitos
            "123456789012345",  # 15 digitos
            "",
        ],
    )
    def test_cnpj_invalido_recusado(self, cnpj: str) -> None:
        assert cnpj_valido(cnpj) is False

    @pytest.mark.parametrize("digito", ["0", "1", "5", "9"])
    def test_sequencia_de_digito_repetido_e_sempre_recusada(self, digito: str) -> None:
        assert cnpj_valido(digito * 14) is False


def _pis_valido_de_referencia(base_10_digitos: str) -> str:
    """Calcula o digito verificador esperado para os 10 primeiros digitos,
    para gerar casos de teste sem depender de um numero memorizado."""
    pesos = [3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    soma = sum(int(d) * p for d, p in zip(base_10_digitos, pesos, strict=True))
    resto = soma % 11
    dv = 11 - resto
    if dv >= 10:
        dv = 0
    return base_10_digitos + str(dv)


class TestPisValido:
    @pytest.mark.parametrize("base", ["1205640754", "0000000019", "1234567890"])
    def test_pis_valido_aceito(self, base: str) -> None:
        pis = _pis_valido_de_referencia(base)
        assert pis_valido(pis) is True

    def test_pis_com_mascara_e_aceito(self) -> None:
        pis = _pis_valido_de_referencia("1205640754")
        mascarado = f"{pis[:3]}.{pis[3:8]}.{pis[8:10]}-{pis[10]}"
        assert pis_valido(mascarado) is True

    def test_pis_com_digito_verificador_errado_e_recusado(self) -> None:
        pis = _pis_valido_de_referencia("1205640754")
        errado = pis[:-1] + str((int(pis[-1]) + 1) % 10)
        assert pis_valido(errado) is False

    @pytest.mark.parametrize("tamanho_invalido", ["1234567890", "123456789012"])
    def test_pis_com_tamanho_errado_e_recusado(self, tamanho_invalido: str) -> None:
        assert pis_valido(tamanho_invalido) is False

    @pytest.mark.parametrize("digito", ["0", "3", "7"])
    def test_sequencia_de_digito_repetido_e_sempre_recusada(self, digito: str) -> None:
        assert pis_valido(digito * 11) is False
