"""Posições de campo do AFD (Anexo V da Portaria MTP 671/2021) e CRC-16/KERMIT.

Fonte: `docs/leiaute-afd-aej.md` seções 6-8 (leitura direta do PDF técnico
oficial do MTE, ver aquele documento para a citação literal de cada regra).
Todas as posições abaixo são 1-indexadas na documentação oficial ("Posição"
001-009 etc.); os `slice()` deste módulo já convertem para o índice 0 do
Python, então quem usa `POS_*` fatia a string diretamente
(`linha[POS_NSR]`), sem aritmética extra no ponto de uso.

**Este módulo só sabe LER.** Nenhuma função aqui monta ou grava uma linha de
AFD -- isso é `app.fiscal.afd.**` (F12), fora do ownership desta fase. Ler o
leiaute oficial para reconhecer um arquivo de terceiro não duplica o
gerador: são operações inversas, mas o conhecimento (posição, tipo, largura
de cada campo) é da norma, não do código de F12 -- por isso é lido de novo
aqui, deliberadamente, em vez de importado de lá.
"""

from __future__ import annotations

import datetime as dt

# =============================================================================
# Tipo "1" -- Cabeçalho (302 caracteres). docs/leiaute-afd-aej.md §7.
# =============================================================================
TAMANHO_TIPO1 = 302
POS_TIPO1_CONSTANTE = slice(0, 9)
POS_TIPO1_TIPO_REGISTRO = slice(9, 10)
POS_TIPO1_TIPO_IDENTIFICADOR_EMPREGADOR = slice(10, 11)
POS_TIPO1_CNPJ_CPF_EMPREGADOR = slice(11, 25)
POS_TIPO1_CNO_CAEPF = slice(25, 39)
POS_TIPO1_RAZAO_SOCIAL = slice(39, 189)
POS_TIPO1_NUMERO_REP = slice(189, 206)
POS_TIPO1_DATA_INICIAL = slice(206, 216)
POS_TIPO1_DATA_FINAL = slice(216, 226)
POS_TIPO1_GERACAO = slice(226, 250)
POS_TIPO1_VERSAO_LEIAUTE = slice(250, 253)
POS_TIPO1_TIPO_IDENTIFICADOR_FABRICANTE = slice(253, 254)
POS_TIPO1_CNPJ_CPF_FABRICANTE = slice(254, 268)
POS_TIPO1_MODELO = slice(268, 298)
POS_TIPO1_CRC16 = slice(298, 302)
#: Bytes cobertos pelo CRC-16 do tipo 1: posição 1 até a posição imediatamente
#: anterior ao próprio campo de CRC (docs/leiaute-afd-aej.md §8.1 -- "aplica-se
#: apenas aos registros dos tipos 1 a 5 ... cobre os bytes do registro na sua
#: representação de largura fixa, da posição 1 até a posição imediatamente
#: anterior ao campo de CRC").
POS_TIPO1_COBERTO_PELO_CRC = slice(0, 298)

# =============================================================================
# Tipo "3" -- Marcação REP-C/REP-A (50 caracteres). NÃO se aplica ao REP-P
# (docs/leiaute-afd-aej.md §7, "não se aplica ao REP-P") -- um arquivo com
# registros deste tipo não é um AFD de REP-P e é rejeitado por inteiro.
# =============================================================================
TAMANHO_TIPO3 = 50

# =============================================================================
# Outros tipos que podem aparecer num AFD real mas não viram marcação
# importada por este módulo (sem CPF de vínculo/pareamento útil aqui):
# tipo "2" (331), "4" (73), "5" (118), "6" (36, sem CRC).
# =============================================================================
TAMANHO_TIPO2 = 331
TAMANHO_TIPO4 = 73
TAMANHO_TIPO5 = 118
TAMANHO_TIPO6 = 36

# =============================================================================
# Tipo "7" -- Marcação de ponto do REP-P (137 caracteres, sem CRC-16, com
# hash SHA-256). docs/leiaute-afd-aej.md §7 -- o registro central desta fase.
# =============================================================================
TAMANHO_TIPO7 = 137
POS_TIPO7_NSR = slice(0, 9)
POS_TIPO7_TIPO_REGISTRO = slice(9, 10)
POS_TIPO7_DATAHORA_MARCACAO = slice(10, 34)
POS_TIPO7_CPF = slice(34, 46)
POS_TIPO7_DATAHORA_GRAVACAO = slice(46, 70)
POS_TIPO7_IDENTIFICADOR_COLETOR = slice(70, 72)
POS_TIPO7_ONLINE_OFFLINE = slice(72, 73)
POS_TIPO7_HASH = slice(73, 137)

# =============================================================================
# Tipo "9" -- Trailer (64 caracteres, sem CRC-16). docs/leiaute-afd-aej.md §7.
# =============================================================================
TAMANHO_TIPO9 = 64
POS_TIPO9_CONSTANTE = slice(0, 9)
POS_TIPO9_QTD_TIPO2 = slice(9, 18)
POS_TIPO9_QTD_TIPO3 = slice(18, 27)
POS_TIPO9_QTD_TIPO4 = slice(27, 36)
POS_TIPO9_QTD_TIPO5 = slice(36, 45)
POS_TIPO9_QTD_TIPO6 = slice(45, 54)
POS_TIPO9_QTD_TIPO7 = slice(54, 63)
POS_TIPO9_TIPO_REGISTRO = slice(63, 64)

#: Linha de assinatura digital: última linha do arquivo, 100 caracteres,
#: sem número de tipo. docs/leiaute-afd-aej.md §7.
TAMANHO_LINHA_ASSINATURA = 100
LITERAL_ASSINATURA_EM_ARQUIVO_SEPARADO = "ASSINATURA_DIGITAL_EM_ARQUIVO_P7S"

#: Constantes fixas dos campos 1 dos tipos "1" e "9" (docs/leiaute-afd-aej.md
#: §7, "constante").
CONSTANTE_TIPO1 = "000000000"
CONSTANTE_TIPO9 = "999999999"


# =============================================================================
# CRC-16/KERMIT (docs/leiaute-afd-aej.md §8.1): polinômio 0x1021, valor
# inicial 0x0000, RefIn/RefOut verdadeiros, XorOut 0x0000. Vetor de teste
# oficial: CRC-16("123456789") = 0x2189, citado literalmente pela fonte
# primária (leiaute oficial do AFD, regra 8 + observação).
#
# Deliberadamente DIFERENTE do `crc16()` de `app.marcacao.dominio.nsr`
# (CRC-16/ARC, polinômio reverso 0xA001) -- aquele é a convenção INTERNA que
# F5 usa para as NOSSAS marcações (documentada como "não certificada" na
# própria docstring daquele módulo); este é o algoritmo OFICIAL do leiaute,
# usado aqui para validar a integridade estrutural de um AFD de TERCEIRO que
# alega seguir a norma. Nunca confundir os dois nem reaproveitar um pelo
# outro -- é exatamente a distinção que o critério de aceite 8 do PCF F13
# exige entre o que F5 calcularia e o que este importador calcula.
# =============================================================================
_POLINOMIO_REFLETIDO_KERMIT = 0x8408


def crc16_kermit(dados: bytes) -> int:
    """CRC-16/KERMIT sobre `dados`. Implementação bit-a-bit refletida
    (RefIn/RefOut já embutidos no algoritmo, sem pós-processamento extra)."""
    crc = 0x0000
    for byte in dados:
        crc ^= byte
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ _POLINOMIO_REFLETIDO_KERMIT
            else:
                crc >>= 1
    return crc & 0xFFFF


def crc16_kermit_hex(dados: bytes) -> str:
    """`crc16_kermit` formatado como 4 dígitos hexadecimais maiúsculos, sem
    `0x` -- exatamente o formato do campo de CRC no AFD (docs/leiaute-afd-aej
    .md §6 regra 8: "os 4 caracteres hexadecimais do CRC-16")."""
    return f"{crc16_kermit(dados):04X}"


# =============================================================================
# Campo `DH`: `AAAA-MM-ddThh:mm:00ZZZZZ`, 24 caracteres, ex.
# "2021-04-27T16:44:00-0300" (docs/leiaute-afd-aej.md §6 regra 6).
# =============================================================================
_FORMATO_DH = "%Y-%m-%dT%H:%M:%S%z"


class CampoDhInvalido(ValueError):
    """Campo `DH` não corresponde ao formato `AAAA-MM-ddThh:mm:00ZZZZZ`."""


def parsear_dh(bruto: str) -> dt.datetime:
    """Interpreta um campo `DH` de 24 caracteres em `datetime` com fuso.

    Não valida que os segundos sejam literalmente `"00"` (a norma fixa isso,
    mas um arquivo de terceiro que traga segundo diferente de zero ainda
    carrega uma data/hora válida e recuperável -- rejeitar por isso seria
    mais estrito que o próprio objetivo de migração de dados)."""
    texto = bruto.strip()
    if len(texto) != 24 or texto[10] != "T":
        raise CampoDhInvalido(f"Campo DH fora do formato esperado: {bruto!r}.")
    try:
        return dt.datetime.strptime(texto, _FORMATO_DH)
    except ValueError as exc:
        raise CampoDhInvalido(f"Campo DH ilegível: {bruto!r} ({exc}).") from exc


def parsear_data(bruta: str) -> dt.date:
    """Campo `D`: `AAAA-MM-dd` (docs/leiaute-afd-aej.md §6 regra 6)."""
    try:
        return dt.date.fromisoformat(bruta.strip())
    except ValueError as exc:
        raise CampoDhInvalido(f"Campo D ilegível: {bruta!r} ({exc}).") from exc
