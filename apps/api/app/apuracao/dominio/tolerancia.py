"""Tolerancia de marcacao e tolerancia diaria (T2, art. 58 par. 1 CLT).

`jornadas.tolerancia_marcacao_minutos` (padrao 5) e `tolerancia_diaria_minutos`
(padrao 10) sao dado de configuracao, lidos pelo chamador -- este modulo nunca
grava jornada, so aplica os dois numeros a uma lista de desvios em minutos.

**Interpretacao fixada aqui** (o PCF descreve o principio em prosa -- "ate 5
minutos por marcacao e 10 minutos no total do dia", glossario, verbete
Tolerancia -- a formalizacao abaixo e a escolha deste modulo, documentada para
que A4/orquestrador possam conferir ou abrir RFC se discordarem):

1. Cada desvio da lista e comparado, ISOLADAMENTE, a
   `tolerancia_marcacao_minutos`. Um desvio que sozinho ja excede esse limite
   e SEMPRE computado por inteiro -- nunca entra no "cofre" da tolerancia
   diaria (art. 58 par. 1 fala em variacoes de ate 5 minutos; uma variacao
   maior que isso nunca foi, em si, tolerada).
2. Os desvios elegiveis (cada um <= tolerancia por marcacao) sao somados. Se a
   soma nao ultrapassa `tolerancia_diaria_minutos`, nenhum deles e computado
   (a tolerancia absorve o dia inteiro).
3. Se a soma ultrapassa o teto diario:
   - `descontar_tudo_se_exceder=True`: a tolerancia diaria e descartada por
     inteiro -- TODOS os desvios elegiveis passam a ser computados (nao so o
     excedente). `jornadas.descontar_tudo_se_exceder`, comentario da coluna:
     "quando verdadeiro e a tolerancia diaria estoura, todo o excedente e
     computado, nao apenas a diferenca".
   - `False` (padrao): so o EXCEDENTE acima do teto diario e computado. O
     excedente e distribuido entre os desvios elegiveis NA ORDEM EM QUE
     APARECEM na lista de entrada (primeiro desvio absorve o excedente
     primeiro) -- escolha de desempate documentada aqui, sem orientacao mais
     fina no PCF, analoga a `_PRIORIDADE_TIPO_FERIADO` da F3.

Nao ha ponto flutuante em nenhum passo (ADR-004): toda entrada e saida e
`int` de minutos.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ResultadoTolerancia:
    """`desvios_computados_minutos` tem o MESMO tamanho e a MESMA ordem de
    `desvios_minutos` recebidos por `aplicar_tolerancia` -- cada posicao e o
    valor final (pos-tolerancia) daquele desvio especifico."""

    desvios_computados_minutos: tuple[int, ...]
    tolerancia_aplicada_minutos: int


def aplicar_tolerancia(
    desvios_minutos: Sequence[int],
    *,
    tolerancia_marcacao_minutos: int,
    tolerancia_diaria_minutos: int,
    descontar_tudo_se_exceder: bool,
) -> ResultadoTolerancia:
    """Aplica a tolerancia por marcacao e a tolerancia diaria a uma lista de
    desvios (cada um em minutos, sempre >= 0 -- o chamador ja decide o sinal:
    so desvios desfavoraveis ao empregador, isto e, atraso na entrada e saida
    antecipada, entram aqui; entrada adiantada ou saida tardia sao hora extra,
    tratadas em `calculo.py`, nunca tolerancia)."""
    computados = list(desvios_minutos)
    elegiveis: list[tuple[int, int]] = []  # (indice, valor)
    for indice, desvio in enumerate(desvios_minutos):
        if desvio < 0:
            raise ValueError("desvio de tolerancia nao pode ser negativo")
        if desvio <= tolerancia_marcacao_minutos:
            elegiveis.append((indice, desvio))
            computados[indice] = 0
        # desvio > tolerancia_marcacao_minutos: ja fica com o valor cheio
        # (computados[indice] permanece o valor original), nunca elegivel a
        # tolerancia diaria.

    soma_elegivel = sum(valor for _, valor in elegiveis)

    if soma_elegivel <= tolerancia_diaria_minutos:
        return ResultadoTolerancia(
            desvios_computados_minutos=tuple(computados),
            tolerancia_aplicada_minutos=soma_elegivel,
        )

    if descontar_tudo_se_exceder:
        for indice, valor in elegiveis:
            computados[indice] = valor
        return ResultadoTolerancia(
            desvios_computados_minutos=tuple(computados),
            tolerancia_aplicada_minutos=0,
        )

    excedente_restante = soma_elegivel - tolerancia_diaria_minutos
    for indice, valor in elegiveis:
        se = min(valor, excedente_restante)
        computados[indice] = se
        excedente_restante -= se
        if excedente_restante <= 0:
            break
    return ResultadoTolerancia(
        desvios_computados_minutos=tuple(computados),
        tolerancia_aplicada_minutos=tolerancia_diaria_minutos,
    )
