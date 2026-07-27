"""Apuracao do dia (F4 / A1).

Publica `servico.apurar_dia(sessao, tenant_id, vinculo_id, data) ->
contrato.ApuracaoDia` -- assinatura fixada no PCF da fase
(`docs/fases/F04-calculo-banco-de-horas.md`, secao 4). E a funcao que
`apps/worker/worker/tarefas/apuracao.py::apurar_dia` chama e que
`app.apuracao.tratamento.recalculo.recalcular_periodo` (A3) chama para cada
`(vinculo, dia)` do intervalo reprocessado -- nunca duplique a logica de
pareamento/calculo daqui em outro modulo.

Sequencia interna deste subpacote: `pareamento` (pareia marcacoes do dia) ->
`tolerancia` (art. 58 par. 1 CLT) -> `noturno` (hora ficta e prorrogacao) ->
`calculo` (normais/extras por faixa, intrajornada, interjornada, DSR, falta)
-> `servico` (orquestra tudo, le/grava banco, publica `ocorrencia.aberta`).
`consulta`/`paginacao` sao o lado de leitura (`listarApuracoes`,
`obterApuracao`, `listarOcorrencias`).

Nunca escreve em `marcacoes`; nunca reescreve a logica de
`app.jornada.resolvedor.servico.resolver_jornada_do_dia` (F3), so a consome.
"""

from __future__ import annotations
