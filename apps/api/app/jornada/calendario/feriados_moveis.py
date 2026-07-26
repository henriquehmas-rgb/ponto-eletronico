"""Calculo de feriados moveis a partir da Pascoa. Funcao pura, sem I/O.

Formula fixada no PCF da F3 (`docs/fases/F03-motor-de-jornada.md`, secao 2,
"Feriados moveis"). A ancora de todas as regras e a data da Pascoa do ano
consultado, calculada pelo algoritmo gregoriano anonimo de Meeus/Jones/Butcher
-- aritmetica inteira, sem ponto flutuante, sem biblioteca de calendario
liturgico de terceiros (a formula tem poucas linhas e e testavel por si).

As ancoras (relativas a Pascoa do `ano`):

* ``pascoa``: a propria data da Pascoa.
* ``carnaval`` (terca-feira de carnaval): Pascoa - 47 dias.
* ``quarta_cinzas``: Pascoa - 46 dias.
* ``sexta_santa``: Pascoa - 2 dias.
* ``corpus_christi``: Pascoa + 60 dias.
* ``custom``: a propria Pascoa (o ``offset_dias`` e obrigatorio na pratica
  para este caso -- validado em `feriados.py`, nao aqui, porque esta funcao e
  pura e nao conhece o catalogo de erros).

``offset_dias`` se soma a qualquer uma das ancoras acima, inclusive `pascoa`.
"""

from __future__ import annotations

import datetime as dt
from typing import Final, Literal

RegraMovel = Literal[
    "pascoa", "carnaval", "sexta_santa", "corpus_christi", "quarta_cinzas", "custom"
]

REGRAS_MOVEIS: Final[frozenset[str]] = frozenset(
    {"pascoa", "carnaval", "sexta_santa", "corpus_christi", "quarta_cinzas", "custom"}
)

#: Deslocamento em dias de cada ancora em relacao a data da Pascoa do ano.
_OFFSET_ANCORA: Final[dict[str, int]] = {
    "pascoa": 0,
    "carnaval": -47,
    "quarta_cinzas": -46,
    "sexta_santa": -2,
    "corpus_christi": 60,
    "custom": 0,
}


def data_pascoa(ano: int) -> dt.date:
    """Domingo de Pascoa do `ano`, pelo algoritmo gregoriano anonimo de
    Meeus/Jones/Butcher. Aritmetica inteira; valido para o calendario
    gregoriano (anos >= 1583).
    """
    a = ano % 19
    b = ano // 100
    c = ano % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    ell = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * ell) // 451
    mes = (h + ell - 7 * m + 114) // 31
    dia = ((h + ell - 7 * m + 114) % 31) + 1
    return dt.date(ano, mes, dia)


def resolver_ancora_movel(regra_movel: str, ano: int, offset_dias: int | None = None) -> dt.date:
    """Data efetiva de um feriado movel no `ano` consultado.

    `regra_movel` deve ser um dos valores de `REGRAS_MOVEIS` (o CHECK do banco
    -- `feriados_regra_movel_check` -- ja garante isso para dados persistidos;
    esta funcao nao valida o dominio de novo, e pura aritmetica de data).
    """
    base = data_pascoa(ano)
    ancora = base + dt.timedelta(days=_OFFSET_ANCORA[regra_movel])
    if offset_dias:
        ancora = ancora + dt.timedelta(days=offset_dias)
    return ancora
