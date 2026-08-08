"""Rotas da tag `webhooks` do contrato (T10-T13 do PCF da F13, agente A3).

Sete operacoes: `criarWebhook`, `listarWebhooks`, `obterWebhook`,
`atualizarWebhook`, `excluirWebhook`, `listarEntregasWebhook`,
`reenviarEntregaWebhook`. Regra de negocio em
`app.integracoes.webhooks.servico`; este modulo so traduz HTTP <-> servico
(mesmo padrao estrutural de `app/routers/terminais.py`).

Autenticacao dupla (contrato declara os tres esquemas alternativos por
operacao -- `bearerAuth`/`oauth2`/`apiKeyAuth`): sessao humana (painel de
RH/gestor, A4/T14) OU cliente de integracao (OAuth/API key, A1/T1). Ver
`app.comum.autenticacao_cliente.exigir_permissao_ou_escopo`.

Idempotencia (T3 de A1) e limite de taxa (T4 de A1) aplicados nas quatro
operacoes de escrita/execucao (`criarWebhook`, `atualizarWebhook`,
`excluirWebhook`, `reenviarEntregaWebhook` -- a ultima e uma execucao, nao
so escrita, mas o contrato marca `x-idempotente: true` para ela tambem).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Path, Query, Response

from app.comum.autenticacao_cliente import (
    ContextoAcesso,
    exigir_permissao_ou_escopo,
)
from app.comum.autenticacao_cliente import (
    aplicar_limite_taxa_se_cliente as _aplicar_limite_taxa_se_cliente,
)
from app.comum.autenticacao_cliente import (
    usuario_id_do_acesso as _usuario_id,
)
from app.comum.idempotencia_generica import (
    ChaveIdempotencia,
    abrir_operacao,
    concluir_operacao,
    exigir_idempotencia,
)
from app.core.config import obter_configuracao
from app.core.erros import RESPOSTAS_PADRAO
from app.db.sessao import SessaoDb
from app.integracoes.webhooks import servico
from app.schemas import contrato

roteador = APIRouter(tags=["webhooks"])

# `ContextoAcesso`/`exigir_permissao_ou_escopo`/`aplicar_limite_taxa_se_cliente`/
# `usuario_id_do_acesso` movidos para `app.comum.autenticacao_cliente` em
# 2026-08-08 (eram genéricos desde a origem em F13/A3, só moravam neste
# módulo por não terem tido consumidor fora de `webhooks`/`integracoes`
# ainda -- agora reaproveitados pelo retrofit de OAuth/API-key de F1-F12,
# ver `docs/backlog.md`). Uma instancia por operacao (nao uma fabrica
# chamada de novo dentro do handler): `exigir_limite_taxa`/o cache de
# dependencia do FastAPI dependem de identidade estavel do *callable* --
# mesmo motivo documentado em `app.comum.limitador_taxa`.
_ACESSO_CRIAR = exigir_permissao_ou_escopo(permissao="webhooks.criar", escopo="webhooks:escrever")
_ACESSO_LISTAR = exigir_permissao_ou_escopo(permissao="webhooks.ler", escopo="webhooks:ler")
_ACESSO_OBTER = exigir_permissao_ou_escopo(permissao="webhooks.ler", escopo="webhooks:ler")
_ACESSO_ATUALIZAR = exigir_permissao_ou_escopo(
    permissao="webhooks.editar", escopo="webhooks:escrever"
)
_ACESSO_EXCLUIR = exigir_permissao_ou_escopo(
    permissao="webhooks.excluir", escopo="webhooks:escrever"
)
_ACESSO_LISTAR_ENTREGAS = exigir_permissao_ou_escopo(
    permissao="webhooks.ler", escopo="webhooks:ler"
)
_ACESSO_REENVIAR = exigir_permissao_ou_escopo(
    permissao="webhooks.executar", escopo="webhooks:escrever"
)


@roteador.post(
    "/v1/webhooks",
    status_code=201,
    operation_id="criarWebhook",
    summary="Criar webhook",
    responses=RESPOSTAS_PADRAO,
)
async def criar_webhook(
    corpo: contrato.WebhookCriar,
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_CRIAR)],
    chave_idem: Annotated[ChaveIdempotencia, Depends(exigir_idempotencia())],
    sessao: SessaoDb,
    response: Response,
    x_tenant: Annotated[str | None, Header(alias="X-Tenant")] = None,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> contrato.WebhookCriado:
    """Criar webhook"""
    await _aplicar_limite_taxa_se_cliente(response, acesso)

    abertura = await abrir_operacao(
        sessao, tenant_id=acesso.tenant_id, escopo="webhooks.criarWebhook", chave=chave_idem
    )
    response.headers["Idempotency-Replayed"] = "true" if abertura.ja_concluido else "false"
    if abertura.ja_concluido:
        return contrato.WebhookCriado.model_validate(abertura.resposta_corpo)

    webhook, segredo = await servico.criar_webhook(
        sessao, acesso.tenant_id, corpo, _usuario_id(acesso)
    )
    resultado = contrato.WebhookCriado.model_validate(
        {
            "webhook": servico.montar_resposta_webhook(webhook),
            "segredoHmac": segredo,
            "cabecalhoAssinatura": servico.CABECALHO_ASSINATURA,
            "formatoAssinatura": servico.FORMATO_ASSINATURA,
        }
    )
    await concluir_operacao(
        sessao,
        registro_id=abertura.registro_id,
        status_http=201,
        corpo_resposta=resultado.model_dump(mode="json", by_alias=True),
    )
    return resultado


@roteador.get(
    "/v1/webhooks",
    status_code=200,
    operation_id="listarWebhooks",
    summary="Listar webhooks",
    responses=RESPOSTAS_PADRAO,
)
async def listar_webhooks(
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_LISTAR)],
    sessao: SessaoDb,
    response: Response,
    x_tenant: Annotated[str | None, Header(alias="X-Tenant")] = None,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
    cursor: Annotated[str | None, Query(alias="cursor")] = None,
    limite: Annotated[int | None, Query(alias="limite")] = None,
    ordenar: Annotated[str | None, Query(alias="ordenar")] = None,
    api_client_id: Annotated[UUID | None, Query(alias="apiClientId")] = None,
    evento: Annotated[str | None, Query(alias="evento")] = None,
    status: Annotated[str | None, Query(alias="status")] = None,
) -> contrato.ListaWebhook:
    """Listar webhooks"""
    await _aplicar_limite_taxa_se_cliente(response, acesso)
    linhas, paginacao = await servico.listar_webhooks(
        sessao,
        acesso.tenant_id,
        api_client_id=api_client_id,
        evento=evento,
        status=status,
        cursor=cursor,
        limite=limite,
        ordenar=ordenar,
    )
    dados = [servico.montar_resposta_webhook(linha) for linha in linhas]
    return contrato.ListaWebhook(dados=dados, paginacao=paginacao)


@roteador.get(
    "/v1/webhooks/{webhookId}",
    status_code=200,
    operation_id="obterWebhook",
    summary="Obter webhook",
    responses=RESPOSTAS_PADRAO,
)
async def obter_webhook(
    webhook_id: Annotated[UUID, Path(alias="webhookId")],
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_OBTER)],
    sessao: SessaoDb,
    response: Response,
    x_tenant: Annotated[str | None, Header(alias="X-Tenant")] = None,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> contrato.Webhook:
    """Obter webhook"""
    await _aplicar_limite_taxa_se_cliente(response, acesso)
    webhook = await servico.obter_webhook(sessao, acesso.tenant_id, webhook_id)
    return servico.montar_resposta_webhook(webhook)


@roteador.patch(
    "/v1/webhooks/{webhookId}",
    status_code=200,
    operation_id="atualizarWebhook",
    summary="Atualizar webhook",
    responses=RESPOSTAS_PADRAO,
)
async def atualizar_webhook(
    webhook_id: Annotated[UUID, Path(alias="webhookId")],
    corpo: contrato.WebhookAtualizar,
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_ATUALIZAR)],
    chave_idem: Annotated[ChaveIdempotencia, Depends(exigir_idempotencia())],
    sessao: SessaoDb,
    response: Response,
    x_tenant: Annotated[str | None, Header(alias="X-Tenant")] = None,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> contrato.Webhook:
    """Atualizar webhook"""
    await _aplicar_limite_taxa_se_cliente(response, acesso)

    abertura = await abrir_operacao(
        sessao,
        tenant_id=acesso.tenant_id,
        escopo=f"webhooks.atualizarWebhook:{webhook_id}",
        chave=chave_idem,
    )
    response.headers["Idempotency-Replayed"] = "true" if abertura.ja_concluido else "false"
    if abertura.ja_concluido:
        return contrato.Webhook.model_validate(abertura.resposta_corpo)

    webhook = await servico.atualizar_webhook(
        sessao, acesso.tenant_id, webhook_id, corpo, _usuario_id(acesso)
    )
    resultado = servico.montar_resposta_webhook(webhook)
    await concluir_operacao(
        sessao,
        registro_id=abertura.registro_id,
        status_http=200,
        corpo_resposta=resultado.model_dump(mode="json", by_alias=True),
    )
    return resultado


@roteador.delete(
    "/v1/webhooks/{webhookId}",
    status_code=204,
    operation_id="excluirWebhook",
    summary="Excluir webhook",
    responses=RESPOSTAS_PADRAO,
    response_class=Response,
)
async def excluir_webhook(
    webhook_id: Annotated[UUID, Path(alias="webhookId")],
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_EXCLUIR)],
    chave_idem: Annotated[ChaveIdempotencia, Depends(exigir_idempotencia())],
    sessao: SessaoDb,
    response: Response,
    x_tenant: Annotated[str | None, Header(alias="X-Tenant")] = None,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> Response:
    """Excluir webhook"""
    await _aplicar_limite_taxa_se_cliente(response, acesso)

    abertura = await abrir_operacao(
        sessao,
        tenant_id=acesso.tenant_id,
        escopo=f"webhooks.excluirWebhook:{webhook_id}",
        chave=chave_idem,
    )
    response.headers["Idempotency-Replayed"] = "true" if abertura.ja_concluido else "false"
    if not abertura.ja_concluido:
        await servico.excluir_webhook(sessao, acesso.tenant_id, webhook_id, _usuario_id(acesso))
        await concluir_operacao(
            sessao, registro_id=abertura.registro_id, status_http=204, corpo_resposta=None
        )
    # Reaproveita o `response` injetado (ja carrega os cabecalhos
    # `RateLimit-*`/`Idempotency-Replayed` setados acima) em vez de construir
    # um `Response` novo, que perderia esses cabecalhos.
    response.status_code = 204
    return response


@roteador.get(
    "/v1/webhooks/{webhookId}/entregas",
    status_code=200,
    operation_id="listarEntregasWebhook",
    summary="Listar entregas do webhook",
    responses=RESPOSTAS_PADRAO,
)
async def listar_entregas_webhook(
    webhook_id: Annotated[UUID, Path(alias="webhookId")],
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_LISTAR_ENTREGAS)],
    sessao: SessaoDb,
    response: Response,
    x_tenant: Annotated[str | None, Header(alias="X-Tenant")] = None,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
    cursor: Annotated[str | None, Query(alias="cursor")] = None,
    limite: Annotated[int | None, Query(alias="limite")] = None,
    ordenar: Annotated[str | None, Query(alias="ordenar")] = None,
    status: Annotated[str | None, Query(alias="status")] = None,
    evento: Annotated[str | None, Query(alias="evento")] = None,
    de: Annotated[datetime | None, Query(alias="de")] = None,
    ate: Annotated[datetime | None, Query(alias="ate")] = None,
) -> contrato.ListaWebhookEntrega:
    """Listar entregas do webhook"""
    await _aplicar_limite_taxa_se_cliente(response, acesso)
    linhas, paginacao = await servico.listar_entregas(
        sessao,
        acesso.tenant_id,
        webhook_id,
        status=status,
        evento=evento,
        de=de,
        ate=ate,
        cursor=cursor,
        limite=limite,
        ordenar=ordenar,
    )
    dados = [servico.montar_resposta_entrega(linha) for linha in linhas]
    return contrato.ListaWebhookEntrega(dados=dados, paginacao=paginacao)


@roteador.post(
    "/v1/webhooks/{webhookId}/entregas/{entregaId}/reenviar",
    status_code=202,
    operation_id="reenviarEntregaWebhook",
    summary="Reenviar entrega de webhook",
    responses=RESPOSTAS_PADRAO,
)
async def reenviar_entrega_webhook(
    webhook_id: Annotated[UUID, Path(alias="webhookId")],
    entrega_id: Annotated[UUID, Path(alias="entregaId")],
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_REENVIAR)],
    chave_idem: Annotated[ChaveIdempotencia, Depends(exigir_idempotencia())],
    sessao: SessaoDb,
    response: Response,
    x_tenant: Annotated[str | None, Header(alias="X-Tenant")] = None,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> contrato.WebhookEntrega:
    """Reenviar entrega de webhook"""
    await _aplicar_limite_taxa_se_cliente(response, acesso)

    abertura = await abrir_operacao(
        sessao,
        tenant_id=acesso.tenant_id,
        escopo=f"webhooks.reenviarEntregaWebhook:{webhook_id}:{entrega_id}",
        chave=chave_idem,
    )
    response.headers["Idempotency-Replayed"] = "true" if abertura.ja_concluido else "false"
    if abertura.ja_concluido:
        return contrato.WebhookEntrega.model_validate(abertura.resposta_corpo)

    config = obter_configuracao()
    entrega = await servico.reenviar_entrega(
        sessao, acesso.tenant_id, webhook_id, entrega_id, redis_url=config.redis_url
    )
    resultado = servico.montar_resposta_entrega(entrega)
    await concluir_operacao(
        sessao,
        registro_id=abertura.registro_id,
        status_http=202,
        corpo_resposta=resultado.model_dump(mode="json", by_alias=True),
    )
    return resultado
