"""Adicional noturno, hora ficta de 52'30" e prorrogacao noturna (T3).

Formula fixada pelo PCF da fase (secao 2), para que A1 e A4 (golden dataset)
concordem: `jornadas.noturno_inicio`/`noturno_fim` (padrao 22:00-05:00)
delimitam o periodo noturno urbano. Quando `hora_ficta_noturna=True` (padrao),
cada 52 minutos e 30 segundos de relogio trabalhados DENTRO do periodo noturno
equivalem a 60 minutos de jornada.

**Aritmetica exata, sem ponto flutuante (ADR-004).** 52 minutos e 30 segundos
sao 52,5 minutos; a razao 60/52,5 e EXATAMENTE 8/7 (60/52,5 = 6000/5250 =
8/7, dividindo numerador e denominador por 750) -- uma fracao racional exata,
sem dizima. Os minutos equivalentes de um bloco noturno de `n` minutos de
relogio sao `round(n * 8 / 7)`, calculado em aritmetica inteira como
`(n * 16 + 7) // 14` (a formula de arredondamento-para-o-mais-proximo de
`p/q` e `(2p + q) // (2q)`; aqui `p = n*8`, `q = 7`, entao `2p+q = n*16+7` e
`2q = 14`). Como `q=7` e impar, `2*(n*8) mod 14 = (16n) mod 14 = (2n) mod 14`
e sempre par, e portanto NUNCA cai exatamente em ".5" -- nao ha empate para
desempatar, o arredondamento e sempre inambiguo.
`noturno_ficta_minutos` (o acrescimo gravado em `apuracoes_dia`) e a diferenca
entre o equivalente e o `n` original.

**Prorrogacao noturna (Sumula 60, II do TST).** Quando
`jornadas.prorrogacao_noturna=True` (padrao) e um periodo trabalhado COMECOU
dentro do periodo noturno mas continuou depois do fim dele (`noturno_fim`),
o tratamento noturno (hora ficta inclusive) continua ate o FIM do periodo
trabalhado, nao para no relogio as 05:00 -- e por isso que a janela noturna
efetiva de UMA instancia especifica (a que contem o inicio do periodo) e
esticada ate o fim do periodo trabalhado, em vez de truncada em
`noturno_fim`.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass


def _proxima_janela(
    dia: dt.date, *, noturno_inicio: dt.time, noturno_fim: dt.time, fuso: dt.tzinfo
) -> tuple[dt.datetime, dt.datetime]:
    """Uma instancia da janela noturna que comeca no `dia` civil informado.

    Padrao urbano (22:00-05:00) cruza a meia-noite: a janela vai de
    `noturno_inicio` do `dia` ate `noturno_fim` do dia SEGUINTE. O schema
    permite, em tese, `noturno_inicio <= noturno_fim` (janela que NAO cruza
    meia-noite, configuracao incomum mas nao proibida pelo `CHECK`); tratada
    aqui como janela contida no mesmo dia civil.
    """
    inicio = dt.datetime.combine(dia, noturno_inicio, tzinfo=fuso)
    if noturno_inicio > noturno_fim:
        fim = dt.datetime.combine(dia + dt.timedelta(days=1), noturno_fim, tzinfo=fuso)
    else:
        fim = dt.datetime.combine(dia, noturno_fim, tzinfo=fuso)
    return inicio, fim


def minutos_no_periodo_noturno(
    entrada: dt.datetime,
    saida: dt.datetime,
    *,
    noturno_inicio: dt.time,
    noturno_fim: dt.time,
    prorrogacao_noturna: bool,
) -> int:
    """Minutos de RELOGIO (antes da hora ficta) de `[entrada, saida)` que
    caem dentro do periodo noturno, considerando a prorrogacao quando
    aplicavel. `entrada`/`saida` devem estar no mesmo fuso (o da unidade do
    vinculo, ADR-004) -- este modulo nao converte fuso, so compara instantes.
    """
    if saida <= entrada:
        return 0

    fuso = entrada.tzinfo
    if fuso is None:
        raise ValueError("entrada/saida precisam ser datetimes com fuso (aware)")

    total_minutos = 0
    dia = entrada.date() - dt.timedelta(days=1)
    ultimo_dia = saida.date() + dt.timedelta(days=1)
    while dia <= ultimo_dia:
        inicio_janela, fim_janela = _proxima_janela(
            dia, noturno_inicio=noturno_inicio, noturno_fim=noturno_fim, fuso=fuso
        )
        fim_efetivo = fim_janela
        if prorrogacao_noturna and inicio_janela <= entrada < fim_janela and saida > fim_janela:
            # Sumula 60, II TST: a jornada comecou de noite e continua alem do
            # fim da janela -- o tratamento noturno persiste ate o fim real do
            # periodo trabalhado, so para ESTA instancia da janela.
            fim_efetivo = saida
        sobreposicao_inicio = max(entrada, inicio_janela)
        sobreposicao_fim = min(saida, fim_efetivo)
        if sobreposicao_fim > sobreposicao_inicio:
            total_minutos += int((sobreposicao_fim - sobreposicao_inicio).total_seconds() // 60)
        dia += dt.timedelta(days=1)
    return total_minutos


@dataclass(frozen=True, slots=True)
class ResultadoHoraFicta:
    noturno_minutos: int
    """Minutos de relogio efetivamente noturnos (sem a hora ficta)."""
    noturno_ficta_minutos: int
    """Acrescimo decorrente da hora ficta -- SOMA-SE a `noturno_minutos` para
    obter os minutos equivalentes de jornada."""


def aplicar_hora_ficta(
    minutos_relogio_noturno: int, *, hora_ficta_noturna: bool
) -> ResultadoHoraFicta:
    """Ver formula no docstring do modulo. Sem hora ficta habilitada (ou sem
    minuto noturno algum), o acrescimo e zero."""
    if minutos_relogio_noturno <= 0 or not hora_ficta_noturna:
        return ResultadoHoraFicta(
            noturno_minutos=max(0, minutos_relogio_noturno), noturno_ficta_minutos=0
        )
    equivalente = (minutos_relogio_noturno * 16 + 7) // 14
    ficta = equivalente - minutos_relogio_noturno
    return ResultadoHoraFicta(noturno_minutos=minutos_relogio_noturno, noturno_ficta_minutos=ficta)
