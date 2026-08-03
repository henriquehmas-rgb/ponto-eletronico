"""Barramento interno e publicacao de `webhook.desabilitado` (`events.yaml`,
evento INTERNO -- `webhook_publico: false`, nunca entregue por webhook).

Mesmo padrao estrutural das outras nove `eventos.py` do catalogo
(`BARRAMENTO_INTERNO` + `montar_envelope` + `publicar`), mas o PRODUTOR real
e o worker: `apps/worker/worker/tarefas/integracoes.py::enviar_webhook`
(T12), quando uma entrega esgota `max_tentativas` e o webhook ultrapassa o
limite de falhas consecutivas. `apps/worker` importa este modulo como
biblioteca (ADR-009 -- mesmo padrao ja usado por `worker.notificacoes_
verificacao` para `app.notificacao.motor`), entao viver aqui em vez de
duplicado no worker evita duas copias do mesmo envelope divergindo.

Por que `publicar()` aqui NAO chama `app.integracoes.webhooks.fan_out.
registrar_pendente`: o evento e interno -- nenhum webhook pode assina-lo
(`criarWebhook` recusa com `PONTO-WEBH-003` qualquer evento fora do
catalogo publico), entao a consulta de fan-out nunca encontraria uma linha
`webhooks.eventos @> ARRAY['webhook.desabilitado']`. Chamar seria
trabalho gratuito, nao um bug se chamado -- mas omitir e mais claro.
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Any
from uuid import UUID, uuid4

logger = logging.getLogger("integracoes.webhooks.eventos")

NOME_WEBHOOK_DESABILITADO = "webhook.desabilitado"
VERSAO_WEBHOOK_DESABILITADO = 1

BARRAMENTO_INTERNO: list[dict[str, Any]] = []


def limpar_barramento() -> None:
    """Esvazia o barramento interno. Uso exclusivo de teste, entre casos."""
    BARRAMENTO_INTERNO.clear()


def montar_envelope(*, tenant_id: UUID, dados: dict[str, Any]) -> dict[str, Any]:
    agora = dt.datetime.now(tz=dt.UTC)
    return {
        "id": str(uuid4()),
        "tipo": NOME_WEBHOOK_DESABILITADO,
        "versao": VERSAO_WEBHOOK_DESABILITADO,
        "ocorridoEm": agora.isoformat(),
        "publicadoEm": agora.isoformat(),
        "tenantId": str(tenant_id),
        "dados": dados,
    }


def publicar(envelope: dict[str, Any]) -> None:
    BARRAMENTO_INTERNO.append(envelope)
    logger.info(
        "evento de dominio publicado",
        extra={"tipo": envelope["tipo"], "id": envelope["id"], "tenantId": envelope["tenantId"]},
    )


def publicar_webhook_desabilitado(
    *,
    tenant_id: UUID,
    webhook_id: UUID,
    nome: str,
    falhas_consecutivas: int,
    ultimo_erro: str | None = None,
    entregas_na_dlq: int = 0,
    desabilitado_em: dt.datetime | None = None,
) -> dict[str, Any]:
    """Publica `webhook.desabilitado` com os `required` de `events.yaml`
    preenchidos: `webhookId`, `nome`, `falhasConsecutivas`, `desabilitadoEm`."""
    dados: dict[str, Any] = {
        "webhookId": str(webhook_id),
        "nome": nome,
        "falhasConsecutivas": falhas_consecutivas,
        "desabilitadoEm": (desabilitado_em or dt.datetime.now(tz=dt.UTC)).isoformat(),
        "entregasNaDlq": entregas_na_dlq,
    }
    if ultimo_erro:
        dados["ultimoErro"] = ultimo_erro
    envelope = montar_envelope(tenant_id=tenant_id, dados=dados)
    publicar(envelope)
    return envelope
