"""T11/T12 -- `worker.despacho_webhooks.despachar_webhooks_pendentes_cross_tenant`
(rotina de cron `worker.scheduler.despachar_webhooks_pendentes`): varre
`webhook_entregas` pendentes/em retentativa de TODO tenant ativo e enfileira
`enviar_webhook`.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.asyncio


class _RedisFalso:
    """Registra chamadas a `enqueue_job` sem precisar de um pool ARQ real --
    o formato exato do enfileiramento (fila, kwargs) ja e provado contra
    Redis de verdade por `tests/f13/webhooks/test_reenvio_manual.py`
    (lado apps/api, T13); aqui o interesse e so a VARREDURA/reivindicacao."""

    def __init__(self) -> None:
        self.chamadas: list[dict] = []

    async def enqueue_job(self, nome_tarefa: str, **kwargs: object) -> None:
        self.chamadas.append({"tarefa": nome_tarefa, **kwargs})


async def test_despachar_reivindica_entrega_pendente_e_enfileira(
    sessao_worker_f13, contexto_webhooks_worker_f13
):
    from worker.despacho_webhooks import despachar_webhooks_pendentes_cross_tenant

    ctx = contexto_webhooks_worker_f13
    entrega_id = uuid.uuid4()
    evento_id = uuid.uuid4()
    await sessao_worker_f13.execute(
        text(
            "INSERT INTO webhook_entregas "
            "(id, tenant_id, webhook_id, evento, evento_id, payload, tentativa, status, "
            " proxima_tentativa_em) "
            "VALUES (:id, :t, :w, 'colaborador.admitido', :eid, '{}'::jsonb, 1, 'pendente', "
            "        now() - interval '1 second')"
        ),
        {"id": entrega_id, "t": ctx.tenant_id, "w": ctx.webhook_id, "eid": evento_id},
    )
    await sessao_worker_f13.commit()

    redis_falso = _RedisFalso()
    resultado = await despachar_webhooks_pendentes_cross_tenant(redis=redis_falso)

    assert resultado["entregasEnfileiradas"] >= 1
    correspondentes = [c for c in redis_falso.chamadas if c.get("entrega_id") == str(entrega_id)]
    assert correspondentes, f"entrega {entrega_id} nao foi enfileirada: {redis_falso.chamadas}"
    assert correspondentes[0]["tarefa"] == "enviar_webhook"
    assert correspondentes[0]["webhook_id"] == str(ctx.webhook_id)
    assert correspondentes[0]["tentativa"] == 1

    # Reivindicada: status virou 'enviando', nao mais candidata a uma
    # segunda varredura (defesa contra despacho duplicado).
    await sessao_worker_f13.execute(
        text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(ctx.tenant_id)}
    )
    linha = (
        await sessao_worker_f13.execute(
            text("SELECT status FROM webhook_entregas WHERE id = :id"), {"id": entrega_id}
        )
    ).one()
    assert linha.status == "enviando"


async def test_despachar_ignora_entrega_com_proxima_tentativa_no_futuro(
    sessao_worker_f13, contexto_webhooks_worker_f13
):
    from worker.despacho_webhooks import despachar_webhooks_pendentes_cross_tenant

    ctx = contexto_webhooks_worker_f13
    entrega_id = uuid.uuid4()
    await sessao_worker_f13.execute(
        text(
            "INSERT INTO webhook_entregas "
            "(id, tenant_id, webhook_id, evento, evento_id, payload, tentativa, status, "
            " proxima_tentativa_em) "
            "VALUES (:id, :t, :w, 'colaborador.admitido', :eid, '{}'::jsonb, 2, 'falha', "
            "        now() + interval '1 hour')"
        ),
        {"id": entrega_id, "t": ctx.tenant_id, "w": ctx.webhook_id, "eid": uuid.uuid4()},
    )
    await sessao_worker_f13.commit()

    redis_falso = _RedisFalso()
    await despachar_webhooks_pendentes_cross_tenant(redis=redis_falso)

    correspondentes = [c for c in redis_falso.chamadas if c.get("entrega_id") == str(entrega_id)]
    assert not correspondentes
