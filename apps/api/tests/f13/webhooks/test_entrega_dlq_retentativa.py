"""T12 -- `enviar_webhook` real, com retentativa exponencial e DLQ.

Critério de aceite oficial (PCF secao 7, item 2): "endpoint fora do ar
acumula em DLQ e reenvia". Critério adicional do PCF (T12, "pronto quando"):
"reativar o webhook zera falhas_consecutivas".

`apps/worker` esta instalado em modo editavel no venv de `apps/api` (ADR-009
-- confirmado por leitura, `import worker` funciona daqui), entao chamamos
`worker.tarefas.integracoes.enviar_webhook` diretamente, contra o MESMO
banco de teste desta suite (`ponto_f13_a3`), sem precisar de um Redis/ARQ
real rodando -- `enviar_webhook` so enfileira a via de commit da propria
linha de `webhook_entregas`; quem ENFILEIRARIA a proxima tentativa (T11/T12,
`worker.scheduler.despachar_webhooks_pendentes`) e testado separadamente
via `httpx.MockTransport`, nunca sobe um servidor HTTP real.

Rodar so este arquivo: `pytest tests/f13/webhooks -q -k "dlq or retentativa or reenvio" -s`.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


async def _reaplicar_tenant(sessao: AsyncSession, tenant_id: uuid.UUID) -> None:
    await sessao.execute(
        text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant_id)}
    )


async def _criar_webhook(
    sessao: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    api_client_id: uuid.UUID,
    max_tentativas: int = 3,
) -> tuple[uuid.UUID, bytes]:
    from app.integracoes.webhooks.cifra import cifrar_segredo

    blob, chave_id = cifrar_segredo("segredo-de-teste-t12")
    webhook_id = uuid.uuid4()
    await sessao.execute(
        text(
            "INSERT INTO webhooks "
            "(id, tenant_id, api_client_id, nome, url, eventos, segredo_hmac_cifrado, "
            " chave_id, max_tentativas, timeout_segundos, status, falhas_consecutivas) "
            "VALUES (:id, :tenant_id, :api_client_id, :nome, :url, "
            "        ARRAY['colaborador.admitido']::text[], :segredo, :chave_id, "
            "        :max_tentativas, 5, 'ativo', 0)"
        ),
        {
            "id": webhook_id,
            "tenant_id": tenant_id,
            "api_client_id": api_client_id,
            "nome": f"webhook-t12-{webhook_id.hex[:8]}",
            "url": "https://example.invalid/receber",
            "segredo": blob,
            "chave_id": chave_id,
            "max_tentativas": max_tentativas,
        },
    )
    return webhook_id, blob


async def _criar_entrega(
    sessao: AsyncSession, *, tenant_id: uuid.UUID, webhook_id: uuid.UUID, tentativa: int = 1
) -> uuid.UUID:
    entrega_id = uuid.uuid4()
    evento_id = uuid.uuid4()
    await sessao.execute(
        text(
            "INSERT INTO webhook_entregas "
            "(id, tenant_id, webhook_id, evento, evento_id, payload, tentativa, status, "
            " proxima_tentativa_em) "
            "VALUES (:id, :tenant_id, :webhook_id, 'colaborador.admitido', :evento_id, "
            "        :payload, :tentativa, 'pendente', now())"
        ),
        {
            "id": entrega_id,
            "tenant_id": tenant_id,
            "webhook_id": webhook_id,
            "evento_id": evento_id,
            "payload": (f'{{"id": "{evento_id}", "tipo": "colaborador.admitido", "dados": {{}}}}'),
            "tentativa": tentativa,
        },
    )
    return entrega_id


async def _linha_entrega(sessao: AsyncSession, entrega_id: uuid.UUID):
    return (
        (
            await sessao.execute(
                text("SELECT * FROM webhook_entregas WHERE id = :id"), {"id": entrega_id}
            )
        )
        .mappings()
        .one()
    )


async def _linha_webhook(sessao: AsyncSession, webhook_id: uuid.UUID):
    return (
        (await sessao.execute(text("SELECT * FROM webhooks WHERE id = :id"), {"id": webhook_id}))
        .mappings()
        .one()
    )


@pytest_asyncio.fixture(autouse=True)
async def _apontar_worker_para_banco_de_teste(contexto_webhooks_f13a3):
    """`worker.config.obter_configuracao` tambem e `lru_cache` -- limpa e
    reaponta para o MESMO `DATABASE_URL` que `contexto_webhooks_f13a3` (A1)
    ja publicou em `os.environ`, e descarta a engine cacheada de
    `worker.tarefas.integracoes` entre testes. Fixture ASSINCRONA (nao
    `asyncio.get_event_loop()` de dentro de uma fixture sincrona) para
    compartilhar o MESMO event loop que o teste -- `create_async_engine`
    fica presa ao loop em que nasce, e um loop diferente produz
    `RuntimeError: Event loop is closed`/conexao presa a loop errado."""
    from worker.config import obter_configuracao as obter_config_worker
    from worker.tarefas import integracoes as tarefas_integracoes

    obter_config_worker.cache_clear()
    await tarefas_integracoes.reiniciar_engine_para_testes()
    yield
    await tarefas_integracoes.reiniciar_engine_para_testes()


def _transporte(handler):
    return httpx.MockTransport(handler)


async def test_entrega_bem_sucedida_zera_falhas_consecutivas(sessao_f13a3, contexto_webhooks_f13a3):
    from worker.tarefas.integracoes import enviar_webhook

    ctx = contexto_webhooks_f13a3
    webhook_id, _ = await _criar_webhook(
        sessao_f13a3, tenant_id=ctx.tenant_id, api_client_id=ctx.api_client_id
    )
    await sessao_f13a3.execute(
        text("UPDATE webhooks SET falhas_consecutivas = 3 WHERE id = :id"), {"id": webhook_id}
    )
    entrega_id = await _criar_entrega(sessao_f13a3, tenant_id=ctx.tenant_id, webhook_id=webhook_id)
    await sessao_f13a3.commit()
    await _reaplicar_tenant(sessao_f13a3, ctx.tenant_id)

    chamadas = []

    def handler(request: httpx.Request) -> httpx.Response:
        chamadas.append(request)
        assert request.headers.get("X-Ponto-Signature", "").startswith("t=")
        assert request.headers.get("X-Ponto-Event") == "colaborador.admitido"
        return httpx.Response(200, json={"ok": True})

    cliente = httpx.AsyncClient(transport=_transporte(handler))
    resultado = await enviar_webhook(
        {"job_id": "job-1"},
        tenant_id=str(ctx.tenant_id),
        entrega_id=str(entrega_id),
        webhook_id=str(webhook_id),
        evento="colaborador.admitido",
        tentativa=1,
        cliente_http=cliente,
    )
    await cliente.aclose()

    assert len(chamadas) == 1
    assert resultado["sucesso"] is True

    await _reaplicar_tenant(sessao_f13a3, ctx.tenant_id)
    linha_entrega = await _linha_entrega(sessao_f13a3, entrega_id)
    assert linha_entrega["status"] == "sucesso"
    assert linha_entrega["http_status"] == 200

    linha_webhook = await _linha_webhook(sessao_f13a3, webhook_id)
    assert linha_webhook["falhas_consecutivas"] == 0
    assert linha_webhook["ultima_entrega_em"] is not None


async def test_falha_agenda_proxima_tentativa_com_backoff(sessao_f13a3, contexto_webhooks_f13a3):
    from worker.tarefas.integracoes import enviar_webhook

    ctx = contexto_webhooks_f13a3
    webhook_id, _ = await _criar_webhook(
        sessao_f13a3, tenant_id=ctx.tenant_id, api_client_id=ctx.api_client_id, max_tentativas=3
    )
    entrega_id = await _criar_entrega(
        sessao_f13a3, tenant_id=ctx.tenant_id, webhook_id=webhook_id, tentativa=1
    )
    await sessao_f13a3.commit()
    await _reaplicar_tenant(sessao_f13a3, ctx.tenant_id)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="fora do ar")

    cliente = httpx.AsyncClient(transport=_transporte(handler))
    antes = datetime.now(tz=UTC)
    resultado = await enviar_webhook(
        {"job_id": "job-2"},
        tenant_id=str(ctx.tenant_id),
        entrega_id=str(entrega_id),
        webhook_id=str(webhook_id),
        evento="colaborador.admitido",
        tentativa=1,
        cliente_http=cliente,
    )
    await cliente.aclose()

    assert resultado["sucesso"] is False
    assert "dlq" not in resultado

    await _reaplicar_tenant(sessao_f13a3, ctx.tenant_id)
    linha = await _linha_entrega(sessao_f13a3, entrega_id)
    assert linha["status"] == "falha"
    assert linha["tentativa"] == 2  # proxima tentativa agendada
    assert linha["http_status"] == 503
    assert linha["proxima_tentativa_em"] is not None
    proxima = linha["proxima_tentativa_em"]
    if proxima.tzinfo is None:
        proxima = proxima.replace(tzinfo=UTC)
    # backoff da tentativa 1: 10s (events.yaml).
    assert (proxima - antes).total_seconds() >= 9


async def test_tentativas_esgotadas_vao_para_dlq(sessao_f13a3, contexto_webhooks_f13a3):
    """Criterio de aceite oficial: endpoint fora do ar acumula em DLQ."""
    from worker.tarefas.integracoes import enviar_webhook

    ctx = contexto_webhooks_f13a3
    webhook_id, _ = await _criar_webhook(
        sessao_f13a3, tenant_id=ctx.tenant_id, api_client_id=ctx.api_client_id, max_tentativas=2
    )
    entrega_id = await _criar_entrega(
        sessao_f13a3, tenant_id=ctx.tenant_id, webhook_id=webhook_id, tentativa=2
    )
    await sessao_f13a3.commit()
    await _reaplicar_tenant(sessao_f13a3, ctx.tenant_id)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="erro interno do destino")

    cliente = httpx.AsyncClient(transport=_transporte(handler))
    resultado = await enviar_webhook(
        {"job_id": "job-3"},
        tenant_id=str(ctx.tenant_id),
        entrega_id=str(entrega_id),
        webhook_id=str(webhook_id),
        evento="colaborador.admitido",
        tentativa=2,  # ultima tentativa permitida (max_tentativas=2)
        cliente_http=cliente,
    )
    await cliente.aclose()

    assert resultado["sucesso"] is False
    assert resultado["dlq"] is True

    await _reaplicar_tenant(sessao_f13a3, ctx.tenant_id)
    linha_entrega = await _linha_entrega(sessao_f13a3, entrega_id)
    assert linha_entrega["status"] == "dlq"
    assert linha_entrega["proxima_tentativa_em"] is None

    linha_webhook = await _linha_webhook(sessao_f13a3, webhook_id)
    assert linha_webhook["falhas_consecutivas"] == 1


async def test_falhas_consecutivas_acima_do_limite_desabilita_webhook_e_publica_evento(
    sessao_f13a3, contexto_webhooks_f13a3
):
    """Acima de `_LIMITE_FALHAS_CONSECUTIVAS_DESABILITA`, o webhook muda
    para `desabilitado_por_falha` e `webhook.desabilitado` e publicado (A3 e
    o primeiro produtor real deste evento, PCF criterio de aceite 9)."""
    from worker.tarefas.integracoes import _LIMITE_FALHAS_CONSECUTIVAS_DESABILITA, enviar_webhook

    from app.integracoes.webhooks import eventos as eventos_webhook

    ctx = contexto_webhooks_f13a3
    webhook_id, _ = await _criar_webhook(
        sessao_f13a3, tenant_id=ctx.tenant_id, api_client_id=ctx.api_client_id, max_tentativas=1
    )
    await sessao_f13a3.execute(
        text("UPDATE webhooks SET falhas_consecutivas = :n WHERE id = :id"),
        {"n": _LIMITE_FALHAS_CONSECUTIVAS_DESABILITA, "id": webhook_id},
    )
    entrega_id = await _criar_entrega(
        sessao_f13a3, tenant_id=ctx.tenant_id, webhook_id=webhook_id, tentativa=1
    )
    await sessao_f13a3.commit()
    await _reaplicar_tenant(sessao_f13a3, ctx.tenant_id)

    eventos_webhook.limpar_barramento()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="erro")

    cliente = httpx.AsyncClient(transport=_transporte(handler))
    resultado = await enviar_webhook(
        {"job_id": "job-4"},
        tenant_id=str(ctx.tenant_id),
        entrega_id=str(entrega_id),
        webhook_id=str(webhook_id),
        evento="colaborador.admitido",
        tentativa=1,
        cliente_http=cliente,
    )
    await cliente.aclose()

    assert resultado["desabilitadoPorFalha"] is True

    await _reaplicar_tenant(sessao_f13a3, ctx.tenant_id)
    linha_webhook = await _linha_webhook(sessao_f13a3, webhook_id)
    assert linha_webhook["status"] == "desabilitado_por_falha"
    assert linha_webhook["falhas_consecutivas"] == _LIMITE_FALHAS_CONSECUTIVAS_DESABILITA + 1

    assert len(eventos_webhook.BARRAMENTO_INTERNO) == 1
    publicado = eventos_webhook.BARRAMENTO_INTERNO[0]
    assert publicado["tipo"] == "webhook.desabilitado"
    assert publicado["dados"]["webhookId"] == str(webhook_id)
    eventos_webhook.limpar_barramento()


async def test_reativar_webhook_zera_falhas_consecutivas(sessao_f13a3, contexto_webhooks_f13a3):
    """PCF T12 'pronto quando': reativar o webhook zera falhas_consecutivas
    -- via `atualizarWebhook` (T10, `app.integracoes.webhooks.servico`)."""
    from app.integracoes.webhooks import servico
    from app.schemas import contrato as esquemas

    ctx = contexto_webhooks_f13a3
    webhook_id, _ = await _criar_webhook(
        sessao_f13a3, tenant_id=ctx.tenant_id, api_client_id=ctx.api_client_id
    )
    await sessao_f13a3.execute(
        text(
            "UPDATE webhooks SET status = 'desabilitado_por_falha', falhas_consecutivas = 42 "
            "WHERE id = :id"
        ),
        {"id": webhook_id},
    )
    await sessao_f13a3.commit()
    await _reaplicar_tenant(sessao_f13a3, ctx.tenant_id)

    atualizado = await servico.atualizar_webhook(
        sessao_f13a3,
        ctx.tenant_id,
        webhook_id,
        esquemas.WebhookAtualizar.model_validate({"status": "ativo"}),
        None,
    )
    assert atualizado.status == "ativo"
    assert atualizado.falhas_consecutivas == 0
