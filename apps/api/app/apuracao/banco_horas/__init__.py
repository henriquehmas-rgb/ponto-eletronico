"""Banco de horas (F4, agente A2).

`PROJETO.md` §4.3 e a especificacao de negocio completa; leia-a antes de
mexer neste pacote.

Um vinculo pode ter varias contas simultaneas (`bh_contas`, por exemplo
`normal`, `sobreaviso`, `feriado`), cada uma amarrada a uma `bh_politicas`
(regime `individual` <= 6 meses, `coletivo`/`convencao` <= 12 meses -- limite
legal imposto por `CHECK` no banco, `ck_bh_politicas_periodo_legal`, este
pacote so o respeita, nunca o recalcula). Todo lancamento (`bh_lancamentos`) e
append-only e encadeado por hash (mesmo padrao de `marcacoes`, mesma funcao
`fn_registro_imutavel`, com uma unica excecao: `fn_bh_lancamento_imutavel()`
permite `UPDATE` de apenas `consumido_minutos`, exigido pela rotina de consumo
FIFO/LIFO). Corrigir um lancamento e sempre um estorno (linha nova), nunca um
`UPDATE`/`DELETE`.

Modulos:

* `hash_chain` -- cadeia de hash do extrato e a formula de arredondamento
  (fator NUMERIC aplicado sobre minutos INTEIROS, ADR-004 ponto 2).
* `erros_bd` -- traducao de `IntegrityError` para `ErroDeAplicacao`.
* `paginacao` -- cursor opaco, copia dedicada desta fase.
* `eventos` -- envelope e publicacao de `banco_horas.vencendo`/`banco_horas.quitado`.
* `politicas` -- CRUD de `bh_politicas` (T5).
* `contas` -- CRUD de `bh_contas` (T5).
* `lancamentos` -- `lancar()` e consumo FIFO/LIFO (T6).
* `consulta` -- extrato, saldo e simulador (T6).
* `quitacoes` -- quitacao/expiracao e tetos (T7).
"""

from __future__ import annotations
