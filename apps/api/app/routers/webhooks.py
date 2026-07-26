"""Rotas da tag `webhooks` do contrato. GERADO -- nao editar.

Assinatura de eventos de dominio para entrega por HTTPS, com assinatura HMAC-SHA256, retentativa exponencial e dead letter queue.
Os eventos assinaveis sao os marcados como publicos em packages/contracts/events.yaml.

Regra de negocio destas operacoes entra na fase F13. Ate la toda chamada
responde 501 com PONTO-INT-005. Regerar com
`python tools/gerar_do_contrato.py`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Path, Query, Response

from app.core.erros import RESPOSTAS_PADRAO, NaoImplementado
from app.schemas import contrato

roteador = APIRouter(tags=["webhooks"])


@roteador.post(
    "/v1/webhooks",
    status_code=201,
    operation_id="criarWebhook",
    summary="Criar webhook",
    responses=RESPOSTAS_PADRAO,
)
async def criar_webhook(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    corpo: contrato.WebhookCriar,
    x_tenant: Annotated[
        str | None,
        Header(
            alias="X-Tenant",
            description="Slug ou UUID do tenant alvo. Obrigatorio quando o host nao identifica o tenant (chamadas a api.ponto.<dominio> por cliente de integracao). Em acesso por…",
        ),
    ] = None,
    x_request_id: Annotated[
        str | None,
        Header(
            alias="X-Request-Id",
            description="Identificador de correlacao gerado pelo cliente. Quando ausente o servidor gera um e devolve no cabecalho de resposta de mesmo nome. Aparece na trilha de…",
        ),
    ] = None,
) -> contrato.WebhookCriado:
    """Criar webhook

    Fase 0 entrega andaime: a implementacao entra na fase F13.
    """
    raise NaoImplementado("criarWebhook", fase="F13")


@roteador.get(
    "/v1/webhooks",
    status_code=200,
    operation_id="listarWebhooks",
    summary="Listar webhooks",
    responses=RESPOSTAS_PADRAO,
)
async def listar_webhooks(
    x_tenant: Annotated[
        str | None,
        Header(
            alias="X-Tenant",
            description="Slug ou UUID do tenant alvo. Obrigatorio quando o host nao identifica o tenant (chamadas a api.ponto.<dominio> por cliente de integracao). Em acesso por…",
        ),
    ] = None,
    x_request_id: Annotated[
        str | None,
        Header(
            alias="X-Request-Id",
            description="Identificador de correlacao gerado pelo cliente. Quando ausente o servidor gera um e devolve no cabecalho de resposta de mesmo nome. Aparece na trilha de…",
        ),
    ] = None,
    cursor: Annotated[
        str | None,
        Query(
            alias="cursor",
            description="Cursor opaco devolvido em paginacao.proximoCursor da pagina anterior. Ausente retorna a primeira pagina. O cursor codifica a ordenacao usada: trocar o…",
        ),
    ] = None,
    limite: Annotated[
        int | None, Query(alias="limite", description="Quantidade de itens por pagina.")
    ] = None,
    ordenar: Annotated[
        str | None,
        Query(
            alias="ordenar",
            description="Ordenacao no formato campo:direcao, separando multiplos criterios por virgula. Direcoes aceitas: asc e desc. Campos aceitos sao os documentados em cada…",
        ),
    ] = None,
    api_client_id: Annotated[
        UUID | None,
        Query(alias="apiClientId", description="Filtra pelos webhooks de um cliente de API."),
    ] = None,
    evento: Annotated[
        str | None,
        Query(alias="evento", description="Lista os webhooks que assinam um evento especifico."),
    ] = None,
    status: Annotated[
        str | None, Query(alias="status", description="Filtra pela situacao.")
    ] = None,
) -> contrato.ListaWebhook:
    """Listar webhooks

    Fase 0 entrega andaime: a implementacao entra na fase F13.
    """
    raise NaoImplementado("listarWebhooks", fase="F13")


@roteador.get(
    "/v1/webhooks/{webhookId}",
    status_code=200,
    operation_id="obterWebhook",
    summary="Obter webhook",
    responses=RESPOSTAS_PADRAO,
)
async def obter_webhook(
    webhook_id: Annotated[UUID, Path(alias="webhookId", description="Identificador do webhook.")],
    x_tenant: Annotated[
        str | None,
        Header(
            alias="X-Tenant",
            description="Slug ou UUID do tenant alvo. Obrigatorio quando o host nao identifica o tenant (chamadas a api.ponto.<dominio> por cliente de integracao). Em acesso por…",
        ),
    ] = None,
    x_request_id: Annotated[
        str | None,
        Header(
            alias="X-Request-Id",
            description="Identificador de correlacao gerado pelo cliente. Quando ausente o servidor gera um e devolve no cabecalho de resposta de mesmo nome. Aparece na trilha de…",
        ),
    ] = None,
) -> contrato.Webhook:
    """Obter webhook

    Fase 0 entrega andaime: a implementacao entra na fase F13.
    """
    raise NaoImplementado("obterWebhook", fase="F13")


@roteador.patch(
    "/v1/webhooks/{webhookId}",
    status_code=200,
    operation_id="atualizarWebhook",
    summary="Atualizar webhook",
    responses=RESPOSTAS_PADRAO,
)
async def atualizar_webhook(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    webhook_id: Annotated[UUID, Path(alias="webhookId", description="Identificador do webhook.")],
    corpo: contrato.WebhookAtualizar,
    x_tenant: Annotated[
        str | None,
        Header(
            alias="X-Tenant",
            description="Slug ou UUID do tenant alvo. Obrigatorio quando o host nao identifica o tenant (chamadas a api.ponto.<dominio> por cliente de integracao). Em acesso por…",
        ),
    ] = None,
    x_request_id: Annotated[
        str | None,
        Header(
            alias="X-Request-Id",
            description="Identificador de correlacao gerado pelo cliente. Quando ausente o servidor gera um e devolve no cabecalho de resposta de mesmo nome. Aparece na trilha de…",
        ),
    ] = None,
) -> contrato.Webhook:
    """Atualizar webhook

    Fase 0 entrega andaime: a implementacao entra na fase F13.
    """
    raise NaoImplementado("atualizarWebhook", fase="F13")


@roteador.delete(
    "/v1/webhooks/{webhookId}",
    status_code=204,
    operation_id="excluirWebhook",
    summary="Excluir webhook",
    responses=RESPOSTAS_PADRAO,
    response_class=Response,
)
async def excluir_webhook(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    webhook_id: Annotated[UUID, Path(alias="webhookId", description="Identificador do webhook.")],
    x_tenant: Annotated[
        str | None,
        Header(
            alias="X-Tenant",
            description="Slug ou UUID do tenant alvo. Obrigatorio quando o host nao identifica o tenant (chamadas a api.ponto.<dominio> por cliente de integracao). Em acesso por…",
        ),
    ] = None,
    x_request_id: Annotated[
        str | None,
        Header(
            alias="X-Request-Id",
            description="Identificador de correlacao gerado pelo cliente. Quando ausente o servidor gera um e devolve no cabecalho de resposta de mesmo nome. Aparece na trilha de…",
        ),
    ] = None,
) -> Response:
    """Excluir webhook

    Fase 0 entrega andaime: a implementacao entra na fase F13.
    """
    raise NaoImplementado("excluirWebhook", fase="F13")


@roteador.get(
    "/v1/webhooks/{webhookId}/entregas",
    status_code=200,
    operation_id="listarEntregasWebhook",
    summary="Listar entregas do webhook",
    responses=RESPOSTAS_PADRAO,
)
async def listar_entregas_webhook(
    webhook_id: Annotated[UUID, Path(alias="webhookId", description="Identificador do webhook.")],
    x_tenant: Annotated[
        str | None,
        Header(
            alias="X-Tenant",
            description="Slug ou UUID do tenant alvo. Obrigatorio quando o host nao identifica o tenant (chamadas a api.ponto.<dominio> por cliente de integracao). Em acesso por…",
        ),
    ] = None,
    x_request_id: Annotated[
        str | None,
        Header(
            alias="X-Request-Id",
            description="Identificador de correlacao gerado pelo cliente. Quando ausente o servidor gera um e devolve no cabecalho de resposta de mesmo nome. Aparece na trilha de…",
        ),
    ] = None,
    cursor: Annotated[
        str | None,
        Query(
            alias="cursor",
            description="Cursor opaco devolvido em paginacao.proximoCursor da pagina anterior. Ausente retorna a primeira pagina. O cursor codifica a ordenacao usada: trocar o…",
        ),
    ] = None,
    limite: Annotated[
        int | None, Query(alias="limite", description="Quantidade de itens por pagina.")
    ] = None,
    ordenar: Annotated[
        str | None,
        Query(
            alias="ordenar",
            description="Ordenacao no formato campo:direcao, separando multiplos criterios por virgula. Direcoes aceitas: asc e desc. Campos aceitos sao os documentados em cada…",
        ),
    ] = None,
    status: Annotated[
        str | None, Query(alias="status", description="Filtra pela situacao.")
    ] = None,
    evento: Annotated[
        str | None, Query(alias="evento", description="Filtra pelo nome do evento.")
    ] = None,
    de: Annotated[
        datetime | None, Query(alias="de", description="Entregas a partir deste instante.")
    ] = None,
    ate: Annotated[
        datetime | None, Query(alias="ate", description="Entregas ate este instante.")
    ] = None,
) -> contrato.ListaWebhookEntrega:
    """Listar entregas do webhook

    Fase 0 entrega andaime: a implementacao entra na fase F13.
    """
    raise NaoImplementado("listarEntregasWebhook", fase="F13")


@roteador.post(
    "/v1/webhooks/{webhookId}/entregas/{entregaId}/reenviar",
    status_code=202,
    operation_id="reenviarEntregaWebhook",
    summary="Reenviar entrega de webhook",
    responses=RESPOSTAS_PADRAO,
)
async def reenviar_entrega_webhook(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    webhook_id: Annotated[UUID, Path(alias="webhookId", description="Identificador do webhook.")],
    entrega_id: Annotated[UUID, Path(alias="entregaId", description="Identificador da entrega.")],
    x_tenant: Annotated[
        str | None,
        Header(
            alias="X-Tenant",
            description="Slug ou UUID do tenant alvo. Obrigatorio quando o host nao identifica o tenant (chamadas a api.ponto.<dominio> por cliente de integracao). Em acesso por…",
        ),
    ] = None,
    x_request_id: Annotated[
        str | None,
        Header(
            alias="X-Request-Id",
            description="Identificador de correlacao gerado pelo cliente. Quando ausente o servidor gera um e devolve no cabecalho de resposta de mesmo nome. Aparece na trilha de…",
        ),
    ] = None,
) -> contrato.WebhookEntrega:
    """Reenviar entrega de webhook

    Fase 0 entrega andaime: a implementacao entra na fase F13.
    """
    raise NaoImplementado("reenviarEntregaWebhook", fase="F13")
