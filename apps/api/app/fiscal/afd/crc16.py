"""CRC-16 do AFD (Portaria MTP 671/2021, Anexo V, regra 8 + observação;
`docs/leiaute-afd-aej.md` §8.1) — obrigatório apenas para os registros dos
tipos "1" a "5" do AFD (`docs/fases/F12-conformidade-rep-p.md` §2.2/§2.9).

**NÃO é o mesmo algoritmo que `app.marcacao.dominio.nsr.crc16`** (F5): aquele
implementa CRC-16/ARC (polinômio reverso `0xA001`), documentado na própria
docstring de F5 como "não certificado" contra o leiaute oficial — é uma
função DIFERENTE, de outra fase, com outro propósito (cadeia de detecção de
adulteração interna de `marcacoes`, não o campo de CRC do AFD).

O leiaute exige especificamente **CRC-16 CCITT-TRUE**, também conhecido como
**CRC-16/KERMIT** — citação literal da fonte oficial:

    "Para o AFD gerado pelo REP-A ou pelo REP-P, deve ser utilizado o
    padrão CRC-16 CCITT-TRUE (CRC-16/KERMIT). Por exemplo, os 9 caracteres
    "123456789" geram o CRC-16 de valor 0x2189 em hexadecimal com esse
    algoritmo."

Parâmetros da variante (catálogo público de CRCs — a norma não os declara
explicitamente, só nomeia o padrão e dá o vetor de teste, que bate
exatamente com estes parâmetros, `docs/leiaute-afd-aej.md` §8.1):

- Largura: 16 bits.
- Polinômio (forma normal): `0x1021`.
- Valor inicial: `0x0000`.
- RefIn: verdadeiro (byte de entrada refletido bit a bit).
- RefOut: verdadeiro (registrador final refletido bit a bit).
- XorOut: `0x0000`.
- Vetor de teste (`"123456789"`): `0x2189`.

A implementação abaixo usa o truque padrão para CRCs com RefIn=RefOut=
verdadeiro: processar os bytes com um registrador deslocado à DIREITA
(LSB-first) usando o polinômio JÁ REFLETIDO bit a bit (`0x8408`, o reflexo
de 16 bits de `0x1021`) — matematicamente equivalente a refletir cada byte
de entrada, aplicar o polinômio normal MSB-first, e refletir o resultado
final, mas sem o custo de três passos de reflexão separados. É a mesma
estrutura de `app.marcacao.dominio.nsr.crc16` (CRC-16/ARC, polinômio
refletido `0xA001`) — só o polinômio muda, porque o algoritmo family é o
mesmo (CRC-16 com RefIn/RefOut verdadeiros); NÃO foi copiado daquele módulo
(instrução explícita do PCF), foi escrito e verificado aqui contra o vetor
oficial do leiaute do AFD, independente de F5.
"""

from __future__ import annotations

from typing import Final

#: Reflexo de 16 bits do polinômio normal `0x1021` (CRC-16/CCITT-TRUE).
_POLINOMIO_REFLETIDO: Final[int] = 0x8408
_VALOR_INICIAL: Final[int] = 0x0000


def crc16_ccitt(dados: bytes) -> int:
    """CRC-16 CCITT-TRUE (CRC-16/KERMIT) de `dados`. Devolve um inteiro no
    intervalo `[0, 0xFFFF]`; quem monta o campo do registro formata o
    resultado em hexadecimal (`docs/leiaute-afd-aej.md` §7: "hex, sem 0x").
    """
    registrador = _VALOR_INICIAL
    for byte in dados:
        registrador ^= byte
        for _ in range(8):
            if registrador & 0x0001:
                registrador = (registrador >> 1) ^ _POLINOMIO_REFLETIDO
            else:
                registrador >>= 1
    return registrador & 0xFFFF
