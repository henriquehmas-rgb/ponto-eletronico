"""Fase F4 -- Calculo e Banco de Horas.

Sequencia canonica do motor (packages/contracts/glossario.md, secao 5):

    marcacoes imutaveis -> regras da jornada do dia -> tratamentos aplicaveis
    -> apuracao do dia -> lancamentos de banco de horas -> fechamento

Subpacotes (um por agente, ver docs/fases/F04-calculo-banco-de-horas.md,
secao 5 -- ownership):

* `app.apuracao.dominio` -- A1: pareamento de marcacoes, tolerancia, horas
  normais/extras, adicional noturno, intrajornada/interjornada/DSR,
  `apurar_dia`.
* `app.apuracao.tratamento` -- A3: CRUD de tratamentos, decisao, recalculo
  deterministico e idempotente, trava de periodo fechado.
* `app.apuracao.banco_horas` -- A2: politicas/contas de banco de horas,
  extrato/saldo/lancamentos com consumo FIFO/LIFO, quitacao/expiracao/tetos.
"""

from __future__ import annotations
