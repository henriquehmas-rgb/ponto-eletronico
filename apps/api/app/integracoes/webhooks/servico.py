"""Regra de dominio da tag `webhooks` (T10-T13 do PCF da F13, agente A3).

Padrao de estrutura copiado de `app/terminais/servico.py` (CRUD, paginacao
por cursor, `traduzir_integridade`) -- self-contained, nao importa nada de
outro dominio de negocio.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from ponto_contracts import ApiClient, Webhook, WebhookEntrega
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.erros import ErroDeAplicacao
from app.integracoes.webhooks import despacho
from app.integracoes.webhooks.catalogo import evento_e_assinavel
from app.integracoes.webhooks.cifra import cifrar_segredo, gerar_segredo
from app.integracoes.webhooks.erros_bd import traduzir_integridade
from app.integracoes.webhooks.paginacao import (
    CampoOrdenacao,
    codificar_cursor,
    executar_pagina,
    interpretar_ordenar,
    montar_paginacao,
    normalizar_limite,
)
from app.integracoes.webhooks.validacao_url import url_e_valida
from app.schemas import contrato as esquemas

CABECALHO_ASSINATURA = "X-Ponto-Signature"
FORMATO_ASSINATURA = "t=<epoch_segundos>,v1=<hex_minusculo>"

_CAMPOS_ORDENACAO_WEBHOOK: dict[str, CampoOrdenacao] = {
    "nome": CampoOrdenacao(Webhook.nome, str),
    "ultimaEntregaEm": CampoOrdenacao(Webhook.ultima_entrega_em, dt.datetime.fromisoformat),
}
_ATRIBUTO_POR_CAMPO_WEBHOOK: dict[str, str] = {
    "nome": "nome",
    "ultimaEntregaEm": "ultima_entrega_em",
}

_CAMPOS_ORDENACAO_ENTREGA: dict[str, CampoOrdenacao] = {
    "criadoEm": CampoOrdenacao(WebhookEntrega.criado_em, dt.datetime.fromisoformat),
}


def montar_resposta_webhook(webhook: Webhook) -> esquemas.Webhook:
    """`segredoHmac` NUNCA aparece aqui -- o schema `Webhook` do contrato nem
    tem esse campo, so `WebhookCriado` tem, e so na resposta de criacao."""
    return esquemas.Webhook.model_validate(webhook, from_attributes=True)


def montar_resposta_entrega(entrega: WebhookEntrega) -> esquemas.WebhookEntrega:
    return esquemas.WebhookEntrega.model_validate(entrega, from_attributes=True)


async def obter_webhook(sessao: AsyncSession, tenant_id: UUID, webhook_id: UUID) -> Webhook:
    consulta = sa.select(Webhook).where(
        Webhook.id == webhook_id, Webhook.tenant_id == tenant_id, Webhook.excluido_em.is_(None)
    )
    webhook = (await sessao.execute(consulta)).scalar_one_or_none()
    if webhook is None:
        raise ErroDeAplicacao("PONTO-REC-001", detalhe="Webhook nao encontrado.")
    return webhook


def _validar_eventos(eventos: list[str]) -> None:
    if not eventos:
        raise ErroDeAplicacao("PONTO-VAL-001", detalhe="Informe ao menos um evento para assinar.")
    desconhecidos = [nome for nome in eventos if not evento_e_assinavel(nome)]
    if desconhecidos:
        raise ErroDeAplicacao(
            "PONTO-WEBH-003",
            detalhe=f"Evento(s) desconhecido(s) ou nao publico(s): {', '.join(desconhecidos)}.",
            contexto_log={"eventos": desconhecidos},
        )


def _validar_url(url: str) -> None:
    if not url_e_valida(url):
        raise ErroDeAplicacao(
            "PONTO-WEBH-001",
            detalhe=(
                "A URL precisa ser HTTPS, publica e nao apontar para faixa privada ou de loopback."
            ),
        )


async def _validar_api_client_do_tenant(
    sessao: AsyncSession, tenant_id: UUID, api_client_id: UUID
) -> None:
    """Confirma que `apiClientId` pertence ao MESMO tenant do webhook antes
    de gravar a associacao. Necessario porque a FK de `webhooks.
    api_client_id` sozinha NAO basta: verificacao de chave estrangeira do
    Postgres roda com o privilegio de dono da tabela referenciada, ignorando
    Row Level Security (comportamento documentado do proprio Postgres) --
    sem esta checagem em aplicacao, um `apiClientId` de OUTRO tenant passaria
    a FK sem erro, associando o webhook a um cliente de API alheio."""
    existe = (
        await sessao.execute(
            sa.select(sa.literal(1)).where(
                sa.exists(
                    sa.select(ApiClient.id).where(
                        ApiClient.id == api_client_id, ApiClient.tenant_id == tenant_id
                    )
                )
            )
        )
    ).scalar_one_or_none()
    if not existe:
        raise ErroDeAplicacao(
            "PONTO-REC-001", detalhe="Cliente de API informado nao encontrado neste tenant."
        )


async def criar_webhook(
    sessao: AsyncSession, tenant_id: UUID, dados: esquemas.WebhookCriar, usuario_id: UUID | None
) -> tuple[Webhook, str]:
    """Devolve `(webhook, segredo_em_claro)`. O segredo em claro so pode ser
    lido pelo chamador desta funcao (o handler de `criarWebhook`), NUNCA
    persistido em claro nem logado."""
    url = str(dados.url)
    _validar_url(url)
    _validar_eventos(list(dados.eventos))
    if dados.api_client_id is not None:
        await _validar_api_client_do_tenant(sessao, tenant_id, dados.api_client_id)

    segredo = gerar_segredo()
    blob, chave_id = cifrar_segredo(segredo)

    campos: dict[str, Any] = {
        "tenant_id": tenant_id,
        "api_client_id": dados.api_client_id,
        "nome": dados.nome,
        "url": url,
        "eventos": list(dados.eventos),
        "segredo_hmac_cifrado": blob,
        "chave_id": chave_id,
        "criado_por": usuario_id,
    }
    if dados.cabecalhos_extras is not None:
        campos["cabecalhos_extras"] = dados.cabecalhos_extras
    if dados.max_tentativas is not None:
        campos["max_tentativas"] = dados.max_tentativas
    if dados.timeout_segundos is not None:
        campos["timeout_segundos"] = dados.timeout_segundos
    if dados.status is not None:
        campos["status"] = dados.status.value

    webhook = Webhook(**campos)
    sessao.add(webhook)
    try:
        await sessao.flush()
    except IntegrityError as exc:
        raise traduzir_integridade(exc) from exc
    return webhook, segredo


async def atualizar_webhook(
    sessao: AsyncSession,
    tenant_id: UUID,
    webhook_id: UUID,
    dados: esquemas.WebhookAtualizar,
    usuario_id: UUID | None,
) -> Webhook:
    webhook = await obter_webhook(sessao, tenant_id, webhook_id)

    if dados.url is not None:
        _validar_url(str(dados.url))
    if dados.eventos is not None:
        _validar_eventos(list(dados.eventos))
    if dados.api_client_id is not None:
        await _validar_api_client_do_tenant(sessao, tenant_id, dados.api_client_id)

    campos: dict[str, Any] = dados.model_dump(exclude_unset=True, by_alias=False)
    reativando = (
        webhook.status == "desabilitado_por_falha"
        and dados.status is not None
        and dados.status.value == "ativo"
    )
    for campo, valor in campos.items():
        if campo == "url" and valor is not None:
            valor = str(valor)
        if campo == "eventos" and valor is not None:
            valor = list(valor)
        if hasattr(valor, "value"):  # enum do contrato (Status45)
            valor = valor.value
        setattr(webhook, campo, valor)

    if reativando:
        # "Reativar um webhook desabilitado por falhas zera o contador de
        # falhas consecutivas" (openapi.yaml, descricao de `atualizarWebhook`).
        webhook.falhas_consecutivas = 0

    webhook.atualizado_por = usuario_id
    webhook.atualizado_em = dt.datetime.now(tz=dt.UTC)
    try:
        await sessao.flush()
    except IntegrityError as exc:
        raise traduzir_integridade(exc) from exc
    return webhook


async def excluir_webhook(
    sessao: AsyncSession, tenant_id: UUID, webhook_id: UUID, usuario_id: UUID | None
) -> None:
    """Exclusao logica. 'Entregas pendentes na fila sao canceladas'
    (openapi.yaml, descricao de `excluirWebhook`) -- muda o status das
    entregas `pendente`/`falha` para `cancelada` em vez de deleta-las (o
    historico continua consultavel)."""
    webhook = await obter_webhook(sessao, tenant_id, webhook_id)
    webhook.excluido_em = dt.datetime.now(tz=dt.UTC)
    webhook.excluido_por = usuario_id

    await sessao.execute(
        sa.update(WebhookEntrega)
        .where(
            WebhookEntrega.tenant_id == tenant_id,
            WebhookEntrega.webhook_id == webhook_id,
            WebhookEntrega.status.in_(("pendente", "falha")),
        )
        .values(
            status="cancelada",
            atualizado_por=usuario_id,
            atualizado_em=dt.datetime.now(tz=dt.UTC),
        )
    )
    await sessao.flush()


async def listar_webhooks(
    sessao: AsyncSession,
    tenant_id: UUID,
    *,
    api_client_id: UUID | None = None,
    evento: str | None = None,
    status: str | None = None,
    cursor: str | None = None,
    limite: int | None = None,
    ordenar: str | None = None,
) -> tuple[Sequence[Webhook], esquemas.Paginacao]:
    ordenacao = interpretar_ordenar(
        ordenar, campos_aceitos=frozenset(_CAMPOS_ORDENACAO_WEBHOOK), padrao="nome"
    )
    limite_efetivo = normalizar_limite(limite)

    consulta = sa.select(Webhook).where(
        Webhook.tenant_id == tenant_id, Webhook.excluido_em.is_(None)
    )
    if api_client_id is not None:
        consulta = consulta.where(Webhook.api_client_id == api_client_id)
    if evento is not None:
        consulta = consulta.where(Webhook.eventos.contains([evento]))
    if status is not None:
        consulta = consulta.where(Webhook.status == status)

    campo = _CAMPOS_ORDENACAO_WEBHOOK[ordenacao.campo]
    linhas, tem_mais = await executar_pagina(
        sessao,
        consulta,
        ordenacao=ordenacao,
        campo=campo,
        coluna_id=Webhook.id,
        cursor=cursor,
        limite=limite_efetivo,
    )
    proximo_cursor = None
    if tem_mais and linhas:
        ultimo = linhas[-1]
        valor_ultimo = getattr(ultimo, _ATRIBUTO_POR_CAMPO_WEBHOOK[ordenacao.campo])
        proximo_cursor = codificar_cursor(ordenacao, valor_ultimo, ultimo.id)
    paginacao = montar_paginacao(
        proximo_cursor=proximo_cursor, tem_mais=tem_mais, limite=limite_efetivo
    )
    return linhas, paginacao


async def listar_entregas(
    sessao: AsyncSession,
    tenant_id: UUID,
    webhook_id: UUID,
    *,
    status: str | None = None,
    evento: str | None = None,
    de: dt.datetime | None = None,
    ate: dt.datetime | None = None,
    cursor: str | None = None,
    limite: int | None = None,
    ordenar: str | None = None,
) -> tuple[Sequence[WebhookEntrega], esquemas.Paginacao]:
    # Confirma que o webhook existe (e pertence ao tenant) antes de listar --
    # devolve PONTO-REC-001 em vez de uma lista vazia enganosa.
    await obter_webhook(sessao, tenant_id, webhook_id)

    ordenacao = interpretar_ordenar(
        ordenar, campos_aceitos=frozenset(_CAMPOS_ORDENACAO_ENTREGA), padrao="criadoEm"
    )
    limite_efetivo = normalizar_limite(limite)

    consulta = sa.select(WebhookEntrega).where(
        WebhookEntrega.tenant_id == tenant_id, WebhookEntrega.webhook_id == webhook_id
    )
    if status is not None:
        consulta = consulta.where(WebhookEntrega.status == status)
    if evento is not None:
        consulta = consulta.where(WebhookEntrega.evento == evento)
    if de is not None:
        consulta = consulta.where(WebhookEntrega.criado_em >= de)
    if ate is not None:
        consulta = consulta.where(WebhookEntrega.criado_em <= ate)

    campo = _CAMPOS_ORDENACAO_ENTREGA[ordenacao.campo]
    linhas, tem_mais = await executar_pagina(
        sessao,
        consulta,
        ordenacao=ordenacao,
        campo=campo,
        coluna_id=WebhookEntrega.id,
        cursor=cursor,
        limite=limite_efetivo,
    )
    proximo_cursor = None
    if tem_mais and linhas:
        ultimo = linhas[-1]
        proximo_cursor = codificar_cursor(ordenacao, ultimo.criado_em, ultimo.id)
    paginacao = montar_paginacao(
        proximo_cursor=proximo_cursor, tem_mais=tem_mais, limite=limite_efetivo
    )
    return linhas, paginacao


async def obter_entrega(
    sessao: AsyncSession, tenant_id: UUID, webhook_id: UUID, entrega_id: UUID
) -> WebhookEntrega:
    consulta = sa.select(WebhookEntrega).where(
        WebhookEntrega.id == entrega_id,
        WebhookEntrega.tenant_id == tenant_id,
        WebhookEntrega.webhook_id == webhook_id,
    )
    entrega = (await sessao.execute(consulta)).scalar_one_or_none()
    if entrega is None:
        raise ErroDeAplicacao("PONTO-REC-001", detalhe="Entrega de webhook nao encontrada.")
    return entrega


async def reenviar_entrega(
    sessao: AsyncSession,
    tenant_id: UUID,
    webhook_id: UUID,
    entrega_id: UUID,
    *,
    redis_url: str,
) -> WebhookEntrega:
    """T13: reseta `tentativa=1`, `status='pendente'`, enfileira IMEDIATAMENTE
    -- mesmo de uma entrega em `dlq` (openapi.yaml, descricao de
    `reenviarEntregaWebhook`: "O identificador do evento e preservado ... so
    o identificador da tentativa muda")."""
    webhook = await obter_webhook(sessao, tenant_id, webhook_id)
    entrega = await obter_entrega(sessao, tenant_id, webhook_id, entrega_id)

    entrega.tentativa = 1
    entrega.status = "pendente"
    entrega.proxima_tentativa_em = dt.datetime.now(tz=dt.UTC)
    entrega.http_status = None
    entrega.resposta = None
    entrega.erro = None
    entrega.atualizado_em = dt.datetime.now(tz=dt.UTC)
    await sessao.flush()

    await despacho.enfileirar_tentativa(
        tenant_id=tenant_id,
        entrega_id=entrega.id,
        webhook_id=webhook.id,
        evento=entrega.evento,
        tentativa=1,
        redis_url=redis_url,
    )
    return entrega
