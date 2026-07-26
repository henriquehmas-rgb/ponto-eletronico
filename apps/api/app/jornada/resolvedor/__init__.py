"""Resolvedor de jornada do dia (F3 / A3, T7).

Publica `servico.resolver_jornada_do_dia(sessao, tenant_id, vinculo_id, data)
-> ResolucaoJornada` -- assinatura fixada no PCF da fase
(`docs/fases/F03-motor-de-jornada.md`, secao 4). E a funcao que
`GET /v1/jornadas/resolver` chama (via `app/routers/jornadas.py`) e que o
*golden dataset* de A4 (`apps/api/tests/f3/golden/`) chama diretamente, sem
passar pela camada HTTP.

Este subpacote nunca escreve em `marcacoes`, nunca calcula hora extra,
adicional noturno, intrajornada/interjornada, DSR ou banco de horas -- isso e
a F4 (Onda 3), que consome esta funcao como insumo. Reaproveita, sem
duplicar, as formulas puras publicadas por A1
(`app.jornada.modelagem.escalas.posicao_do_ciclo`) e por A2
(`app.jornada.calendario.feriados.resolver_data_feriado`, que por sua vez usa
`app.jornada.calendario.feriados_moveis.resolver_ancora_movel`).
"""

from __future__ import annotations
