"""T2 -- vetor de teste oficial do CRC-16 CCITT-TRUE (KERMIT).

Este teste é OBRIGATÓRIO e não pode ser aproximado: é o único jeito de
provar que `crc16_ccitt` bate com a norma sem precisar de um AFD de
referência externo -- é exatamente o vetor de teste que a própria norma
cita (`docs/leiaute-afd-aej.md` §8.1, citação literal do Anexo V da
Portaria MTP 671/2021).
"""

from __future__ import annotations

from app.fiscal.afd.crc16 import crc16_ccitt


def test_vetor_oficial() -> None:
    """ "Os 9 caracteres '123456789' geram o CRC-16 de valor 0x2189 em
    hexadecimal" -- citação literal da fonte oficial."""
    assert crc16_ccitt(b"123456789") == 0x2189


def test_vetor_oficial_hex_string() -> None:
    """Mesma prova, com o valor esperado escrito por extenso em vez de
    literal hexadecimal -- reforça que 0x2189 == 8585 (decimal), sem
    depender de leitura correta da notação hex por quem revisar o teste."""
    valor = crc16_ccitt(b"123456789")
    assert valor == 8585
    assert format(valor, "04X") == "2189"


def test_determinismo() -> None:
    """Mesma entrada, sempre o mesmo CRC."""
    dados = "AFD_60258502000149_REP_P".encode("iso-8859-1")
    assert crc16_ccitt(dados) == crc16_ccitt(dados)


def test_entradas_diferentes_produzem_crc_diferente() -> None:
    """Não é uma prova formal de ausência de colisão (CRC-16 tem colisões
    por definição), só uma checagem de sanidade de que a função reage ao
    conteúdo."""
    assert crc16_ccitt(b"123456789") != crc16_ccitt(b"123456780")


def test_string_vazia() -> None:
    """CRC-16 do registrador inicial sem nenhum byte processado é o próprio
    valor inicial (0x0000) -- checagem de caso-limite do laço."""
    assert crc16_ccitt(b"") == 0x0000


def test_nao_e_o_algoritmo_de_f5() -> None:
    """Prova negativa direta do achado do PCF F12 §2.5:
    `app.marcacao.dominio.nsr.crc16` (CRC-16/ARC) produz um valor DIFERENTE
    de `crc16_ccitt` (CRC-16/KERMIT) para a mesma entrada -- são algoritmos
    diferentes, e este teste garante que ninguém reintroduza a confusão
    trocando um import por engano."""
    from app.marcacao.dominio.nsr import crc16 as crc16_arc_de_f5

    dados = b"123456789"
    assert crc16_arc_de_f5(dados) != crc16_ccitt(dados)
    # CRC-16/ARC do vetor oficial e conhecido publicamente como 0xBB3D --
    # confirma que a funcao de F5 e mesmo a variante ARC, nao uma segunda
    # implementacao de KERMIT por acidente.
    assert crc16_arc_de_f5(dados) == 0xBB3D
