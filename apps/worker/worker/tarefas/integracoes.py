"""Entrega de webhooks e sincronizacao de terminais. Implementacao na F13 e F6.

**`enviar_webhook`** entrega um evento de `packages/contracts/events.yaml` ao
endpoint assinado pelo cliente. Assinatura HMAC, retentativa exponencial e
*dead letter* sao contrato desde ja (secao `entrega` do catalogo de eventos): o
consumidor deduplica pelo `id` do envelope e tolera reordenacao, porque a
entrega e *at-least-once*.

**`sincronizar_terminal`** empurra cadastro (usuarios, templates, grupos, regras
de acesso) para um coletor Control iD. Vive na mesma fila de integracoes porque
as duas tarefas sao curtas e falam com rede de terceiro -- e ficam longe da
fila de apuracao, que e longa e nao pode ser atrasada por um endpoint remoto
lento.

Nada disso existe na Fase 0: as duas tarefas devolvem `PONTO-INT-005`.
"""

from __future__ import annotations

from typing import Any

from worker.filas import resultado_nao_implementado
from worker.log import obter_logger

logger = obter_logger("tarefas.integracoes")


async def enviar_webhook(
    ctx: dict[str, Any],
    *,
    tenant_id: str,
    entrega_id: str,
    webhook_id: str,
    evento: str,
    tentativa: int = 1,
) -> dict[str, Any]:
    """Entrega uma vez o evento ao endpoint do cliente, assinado com HMAC.

    Args:
        ctx: contexto do ARQ.
        tenant_id: tenant dono do dado.
        entrega_id: registro em `webhook_entregas`, que acumula o historico.
        webhook_id: assinatura do cliente (endpoint, segredo e eventos).
        evento: nome do evento no catalogo, por exemplo `marcacao.criada`.
        tentativa: numero da tentativa, base do recuo exponencial.
    """
    logger.info(
        "enviar_webhook recebida",
        extra={
            "jobId": ctx.get("job_id"),
            "tenantId": tenant_id,
            "entregaId": entrega_id,
            "webhookId": webhook_id,
            "evento": evento,
            "tentativa": tentativa,
        },
    )
    return resultado_nao_implementado(
        "enviar_webhook",
        tenant_id=tenant_id,
        entrega_id=entrega_id,
        webhook_id=webhook_id,
        evento=evento,
        tentativa=tentativa,
    )


async def sincronizar_terminal(
    ctx: dict[str, Any],
    *,
    tenant_id: str,
    terminal_id: str,
    escopo: str = "completo",
    solicitante_id: str | None = None,
) -> dict[str, Any]:
    """Sincroniza cadastro e biometria com um coletor Control iD.

    Args:
        ctx: contexto do ARQ.
        tenant_id: tenant dono do dado.
        terminal_id: terminal de destino.
        escopo: `completo` ou o subconjunto a propagar (`usuarios`, `templates`,
            `grupos`, `regras`, `horarios`).
        solicitante_id: quem pediu, para a trilha de auditoria.
    """
    logger.info(
        "sincronizar_terminal recebida",
        extra={
            "jobId": ctx.get("job_id"),
            "tenantId": tenant_id,
            "terminalId": terminal_id,
            "escopo": escopo,
        },
    )
    return resultado_nao_implementado(
        "sincronizar_terminal",
        tenant_id=tenant_id,
        terminal_id=terminal_id,
        escopo=escopo,
    )
