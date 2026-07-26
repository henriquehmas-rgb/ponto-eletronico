"""Pipeline canal-agnostico de ingestao de marcacao. Ownership exclusivo do
agente A2 da fase F5 (ver `docs/fases/F05-ingestao-marcacoes-nsr.md`, secao 5).

Modulos:

* `idempotencia` (T5): as quatro chaves de deduplicacao independentes.
* `ingestao` (T6): `registrar_marcacao`, o corpo de `criarMarcacao`.
* `offline` (T7): `sincronizar_lote`, o corpo de `sincronizarMarcacoesOffline`.
* `eventos_marcacao`: publicacao de `marcacao.criada`, `marcacao.suspeita` e
  `marcacao.sincronizada_offline` no barramento interno de
  `app.marcacao.eventos`.
"""

from __future__ import annotations
