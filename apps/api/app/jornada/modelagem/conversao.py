"""Conversoes de tipo compartilhadas entre os servicos de `modelagem`.

O contrato representa hora do dia como `string` (`^([01][0-9]|2[0-3]):[0-5][0-9]$`,
por exemplo `"08:00"`), mas as colunas de `horarios`/`jornadas` sao `TIME`
nativo do Postgres. O driver assincrono (`asyncpg`) nao faz cast implicito de
texto para `time` -- ao contrario de `psycopg2`, que delega o cast ao
Postgres -- entao a conversao para `datetime.time` precisa acontecer em
Python antes do `INSERT`/`UPDATE`.
"""

from __future__ import annotations

import datetime as dt


def hora_ou_none(valor: str | dt.time | None) -> dt.time | None:
    """`"08:00"` -> `time(8, 0)`. Aceita `None` e `time` (idempotente)."""
    if valor is None or isinstance(valor, dt.time):
        return valor
    return dt.time.fromisoformat(valor)
