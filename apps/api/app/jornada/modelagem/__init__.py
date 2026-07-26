"""Modelagem do motor de jornada (F3 / A1): horarios, jornadas (+ dias),
turnos, escalas (+ ciclos) e as atribuicoes datadas ao vinculo
(`vinculo_jornadas`, `escala_atribuicoes`).

Publica `escalas.posicao_do_ciclo`, a formula pura de posicao do ciclo
(aritmetica modular sobre `vigencia_inicio`/`posicao_inicial`/`dias_ciclo`),
reaproveitada pelo resolvedor (F3 / A3, T7) -- ver `docs/fases/F03-motor-de-jornada.md`
secao 2 e 6 (T3/T7). Ninguem alem de A1 edita este subpacote.
"""

from __future__ import annotations
