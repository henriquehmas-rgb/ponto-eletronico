"""T13 -- reenvio manual de uma entrega (`POST /v1/webhooks/{webhookId}/
entregas/{entregaId}/reenviar`, `app.integracoes.webhooks.servico.
reenviar_entrega`). Reseta `tentativa=1`, `status='pendente'`, enfileira
IMEDIATAMENTE -- mesmo de uma entrega em `dlq`.
"""

from __future__ import annotations

import uuid

import pytest
from arq.connections import RedisSettings, create_pool
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.filas import FILA_PADRAO
from app.integracoes.webhooks.despacho import NOME_TAREFA_ENVIAR_WEBHOOK

pytestmark = pytest.mark.asyncio


async def _criar_webhook(sessao: AsyncSession, *, tenant_id, api_client_id) -> uuid.UUID:
    webhook_id = uuid.uuid4()
    await sessao.execute(
        text(
            "INSERT INTO webhooks "
            "(id, tenant_id, api_client_id, nome, url, eventos, segredo_hmac_cifrado, "
            " chave_id, max_tentativas, timeout_segundos, status) "
            "VALUES (:id, :tenant_id, :api_client_id, :nome, :url, "
            "        ARRAY['colaborador.admitido']::text[], :segredo, 'webh-v1', 8, 10, 'ativo')"
        ),
        {
            "id": webhook_id,
            "tenant_id": tenant_id,
            "api_client_id": api_client_id,
            "nome": f"webhook-t13-{webhook_id.hex[:8]}",
            "url": "https://example.invalid/receber",
            "segredo": b"\x00" * 28,
        },
    )
    return webhook_id


async def _criar_entrega_em_dlq(sessao: AsyncSession, *, tenant_id, webhook_id) -> uuid.UUID:
    entrega_id = uuid.uuid4()
    await sessao.execute(
        text(
            "INSERT INTO webhook_entregas "
            "(id, tenant_id, webhook_id, evento, evento_id, payload, tentativa, status, "
            " proxima_tentativa_em, http_status, erro) "
            "VALUES (:id, :tenant_id, :webhook_id, 'colaborador.admitido', :evento_id, "
            "        '{}'::jsonb, 8, 'dlq', NULL, 503, 'endpoint fora do ar')"
        ),
        {
            "id": entrega_id,
            "tenant_id": tenant_id,
            "webhook_id": webhook_id,
            "evento_id": uuid.uuid4(),
        },
    )
    return entrega_id


async def test_reenviar_entrega_em_dlq_reseta_e_enfileira_imediatamente(
    sessao_f13a3, contexto_webhooks_f13a3, redis_teste_url
):
    from app.integracoes.webhooks import servico

    ctx = contexto_webhooks_f13a3
    webhook_id = await _criar_webhook(
        sessao_f13a3, tenant_id=ctx.tenant_id, api_client_id=ctx.api_client_id
    )
    entrega_id = await _criar_entrega_em_dlq(
        sessao_f13a3, tenant_id=ctx.tenant_id, webhook_id=webhook_id
    )
    await sessao_f13a3.commit()
    await sessao_f13a3.execute(
        text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(ctx.tenant_id)}
    )

    entrega = await servico.reenviar_entrega(
        sessao_f13a3, ctx.tenant_id, webhook_id, entrega_id, redis_url=redis_teste_url
    )

    assert entrega.tentativa == 1
    assert entrega.status == "pendente"
    assert entrega.http_status is None
    assert entrega.erro is None

    pool = await create_pool(
        RedisSettings.from_dsn(redis_teste_url), default_queue_name=FILA_PADRAO
    )
    try:
        enfileirados = await pool.queued_jobs()
        correspondentes = [
            job
            for job in enfileirados
            if job.function == NOME_TAREFA_ENVIAR_WEBHOOK
            and job.kwargs.get("entrega_id") == str(entrega_id)
        ]
        assert correspondentes, (
            f"enviar_webhook nao foi enfileirado para a entrega {entrega_id}; "
            f"jobs vistos: {[(j.function, j.kwargs) for j in enfileirados]}"
        )
        assert correspondentes[0].kwargs["tentativa"] == 1
    finally:
        await pool.aclose()
