"""Regra de dominio do `device-gw` (F6, agente A1).

Submodulos:

* `bd` -- engine/sessao assincrona do gateway e o `SET LOCAL app.tenant_id`
  exigido pelo Row Level Security (ADR-001).
* `resolucao` -- `fn_resolve_terminal` (RFC-010): identifica o terminal e o
  tenant a partir do `numero_serie`, antes de existir qualquer outro contexto.
* `cifra` -- decifragem de `terminais.senha_api_cifrada` (mesmo algoritmo e
  mesma variavel de ambiente do envelope cifrado por `apps/api/app/terminais/
  cifra.py`; os dois modulos sao copias deliberadas, nao um pacote
  compartilhado -- mesma razao de `gateway/log.py` duplicar `app/core/log.py`).
* `conversao` -- `access_log` do fabricante -> `MarcacaoCriar` do contrato.
* `fila` -- fila de comandos do modo Push, no Redis.
* `cliente_api` -- chamada a `POST /v1/marcacoes` da API interna.
* `eventos` -- envelope de `packages/contracts/events.yaml` publicado por este
  servico (`terminal.online`).
"""

from __future__ import annotations
