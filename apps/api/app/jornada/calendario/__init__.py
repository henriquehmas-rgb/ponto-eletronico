"""Calendario: feriados (nacional/estadual/municipal, moveis) e afastamentos.

Ownership: F3/A2 (ver `docs/fases/F03-motor-de-jornada.md`, secao 5). Este
pacote nao escreve em `app/jornada/modelagem` nem em `app/jornada/resolvedor`
(A1 e A3, respectivamente); publica apenas as funcoes puras e os servicos que
`app/routers/feriados.py` e `app/routers/afastamentos.py` chamam, e que o
resolvedor (A3, T7) reaproveita para sobrepor feriado/afastamento ao dia
resolvido pela jornada ou escala.
"""

from __future__ import annotations
