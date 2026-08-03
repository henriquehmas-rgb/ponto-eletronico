"""Enfileiramento de uma tentativa de entrega (`enviar_webhook`, T12) na fila
`ponto:integracoes`/`FILA_PADRAO` do ARQ.

Mesmo padrao ja em uso por `app.terminais.servico.sincronizar_terminal` e
`app.workflow.fechamento.servico._enfileirar_processar_fechamento`:
`create_pool(RedisSettings.from_dsn(redis_url), default_queue_name=
FILA_PADRAO)` -- **explicito**, nunca implicito, por causa do achado real de
F9b/A3 documentado em `app/core/filas.py` (job orfao quando
`default_queue_name` e esquecido: cai na fila embutida do ARQ, que nenhum
worker real consome).

Usado em dois pontos:

* `reenviarEntregaWebhook` (T13, `app.integracoes.webhooks.servico`) --
  enfileira IMEDIATAMENTE, mesmo de uma entrega em `dlq`.
* `worker.despacho_webhooks` (T11/T12, processo `scheduler`) -- varre
  `webhook_entregas` pendentes e enfileira cada uma, cross-tenant.

Este modulo cobre so o lado `apps/api` (T13); o lado `scheduler`
(`apps/worker`) tem a propria copia -- os dois processos nao compartilham
pacote Python (mesma razao de `app/core/filas.py` duplicar
`worker/filas.py::FILA_PADRAO`).
"""

from __future__ import annotations

from uuid import UUID

NOME_TAREFA_ENVIAR_WEBHOOK = "enviar_webhook"


async def enfileirar_tentativa(
    *,
    tenant_id: UUID,
    entrega_id: UUID,
    webhook_id: UUID,
    evento: str,
    tentativa: int,
    redis_url: str,
) -> None:
    from arq import create_pool
    from arq.connections import RedisSettings

    from app.core.filas import FILA_PADRAO

    pool = await create_pool(RedisSettings.from_dsn(redis_url), default_queue_name=FILA_PADRAO)
    try:
        await pool.enqueue_job(
            NOME_TAREFA_ENVIAR_WEBHOOK,
            tenant_id=str(tenant_id),
            entrega_id=str(entrega_id),
            webhook_id=str(webhook_id),
            evento=evento,
            tentativa=tentativa,
        )
    finally:
        await pool.aclose()
