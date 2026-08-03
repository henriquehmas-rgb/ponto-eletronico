"""Cobertura adicional (criterio de aceite 13, >= 85%): paginacao por
cursor (ida e volta real, segunda pagina), campos opcionais de
`WebhookCriar`/`WebhookAtualizar`, `listar_entregas`/`obter_entrega`."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from app.core.erros import ErroDeAplicacao
from app.integracoes.webhooks import servico
from app.integracoes.webhooks.paginacao import (
    codificar_cursor,
    decodificar_cursor,
    interpretar_ordenar,
    normalizar_limite,
)
from app.schemas import contrato as esquemas


def test_normalizar_limite_padrao_e_limites() -> None:
    assert servico is not None  # so para o import acima nao ficar orfao
    assert normalizar_limite(None) == 50
    assert normalizar_limite(10) == 10
    with pytest.raises(ErroDeAplicacao):
        normalizar_limite(0)
    with pytest.raises(ErroDeAplicacao):
        normalizar_limite(999)


def test_interpretar_ordenar_padrao_e_invalido() -> None:
    ordenacao = interpretar_ordenar(None, campos_aceitos=frozenset({"nome"}), padrao="nome")
    assert ordenacao.campo == "nome"
    assert ordenacao.direcao == "desc"

    explicita = interpretar_ordenar("nome:asc", campos_aceitos=frozenset({"nome"}), padrao="nome")
    assert explicita.direcao == "asc"

    with pytest.raises(ErroDeAplicacao):
        interpretar_ordenar("campoInvalido:asc", campos_aceitos=frozenset({"nome"}), padrao="nome")
    with pytest.raises(ErroDeAplicacao):
        interpretar_ordenar("nome:lateral", campos_aceitos=frozenset({"nome"}), padrao="nome")


def test_cursor_ida_e_volta() -> None:
    ordenacao = interpretar_ordenar("nome:asc", campos_aceitos=frozenset({"nome"}), padrao="nome")
    id_ = uuid.uuid4()
    cursor = codificar_cursor(ordenacao, "abc", id_)
    valor, id_decodificado = decodificar_cursor(cursor, ordenacao=ordenacao)
    assert valor == "abc"
    assert id_decodificado == id_


def test_cursor_incompativel_com_outra_ordenacao() -> None:
    ordenacao1 = interpretar_ordenar("nome:asc", campos_aceitos=frozenset({"nome"}), padrao="nome")
    ordenacao2 = interpretar_ordenar(
        "ultimaEntregaEm:desc", campos_aceitos=frozenset({"ultimaEntregaEm"}), padrao="nome"
    )
    cursor = codificar_cursor(ordenacao1, "abc", uuid.uuid4())
    with pytest.raises(ErroDeAplicacao):
        decodificar_cursor(cursor, ordenacao=ordenacao2)


def test_cursor_ilegivel() -> None:
    ordenacao = interpretar_ordenar(None, campos_aceitos=frozenset({"nome"}), padrao="nome")
    with pytest.raises(ErroDeAplicacao):
        decodificar_cursor("!!!nao-e-base64-valido!!!", ordenacao=ordenacao)


@pytest.mark.asyncio
async def test_criar_webhook_com_todos_os_campos_opcionais(sessao_f13a3, contexto_webhooks_f13a3):
    ctx = contexto_webhooks_f13a3
    corpo = esquemas.WebhookCriar.model_validate(
        {
            "apiClientId": str(ctx.api_client_id),
            "nome": f"webhook-completo-{uuid.uuid4().hex[:8]}",
            "url": "https://example.invalid/receber",
            "eventos": ["colaborador.admitido", "colaborador.demitido"],
            "cabecalhosExtras": {"X-Origem": "teste"},
            "maxTentativas": 5,
            "timeoutSegundos": 20,
            "status": "suspenso",
        }
    )
    webhook, segredo = await servico.criar_webhook(sessao_f13a3, ctx.tenant_id, corpo, None)
    assert segredo
    assert webhook.cabecalhos_extras == {"X-Origem": "teste"}
    assert webhook.max_tentativas == 5
    assert webhook.timeout_segundos == 20
    assert webhook.status == "suspenso"
    assert webhook.api_client_id == ctx.api_client_id


@pytest.mark.asyncio
async def test_criar_webhook_sem_nenhum_evento_e_recusado(sessao_f13a3, contexto_webhooks_f13a3):
    ctx = contexto_webhooks_f13a3
    corpo = esquemas.WebhookCriar.model_validate(
        {"nome": "webhook-sem-evento", "url": "https://example.invalid/x", "eventos": []}
    )
    with pytest.raises(ErroDeAplicacao) as exc:
        await servico.criar_webhook(sessao_f13a3, ctx.tenant_id, corpo, None)
    assert exc.value.codigo == "PONTO-VAL-001"


@pytest.mark.asyncio
async def test_atualizar_webhook_url_e_eventos(sessao_f13a3, contexto_webhooks_f13a3):
    ctx = contexto_webhooks_f13a3
    webhook, _ = await servico.criar_webhook(
        sessao_f13a3,
        ctx.tenant_id,
        esquemas.WebhookCriar.model_validate(
            {
                "nome": "webhook-att",
                "url": "https://example.invalid/a",
                "eventos": ["colaborador.admitido"],
            }
        ),
        None,
    )
    await sessao_f13a3.flush()

    atualizado = await servico.atualizar_webhook(
        sessao_f13a3,
        ctx.tenant_id,
        webhook.id,
        esquemas.WebhookAtualizar.model_validate(
            {"url": "https://example.invalid/b", "eventos": ["colaborador.demitido"]}
        ),
        None,
    )
    assert str(atualizado.url) == "https://example.invalid/b"
    assert atualizado.eventos == ["colaborador.demitido"]


@pytest.mark.asyncio
async def test_atualizar_webhook_url_invalida_e_recusada(sessao_f13a3, contexto_webhooks_f13a3):
    ctx = contexto_webhooks_f13a3
    webhook, _ = await servico.criar_webhook(
        sessao_f13a3,
        ctx.tenant_id,
        esquemas.WebhookCriar.model_validate(
            {
                "nome": "webhook-att2",
                "url": "https://example.invalid/a",
                "eventos": ["colaborador.admitido"],
            }
        ),
        None,
    )
    await sessao_f13a3.flush()
    with pytest.raises(ErroDeAplicacao) as exc:
        await servico.atualizar_webhook(
            sessao_f13a3,
            ctx.tenant_id,
            webhook.id,
            esquemas.WebhookAtualizar.model_validate({"url": "http://example.invalid/inseguro"}),
            None,
        )
    assert exc.value.codigo == "PONTO-WEBH-001"


@pytest.mark.asyncio
async def test_listar_webhooks_segunda_pagina_via_cursor(sessao_f13a3, contexto_webhooks_f13a3):
    ctx = contexto_webhooks_f13a3
    for i in range(3):
        await servico.criar_webhook(
            sessao_f13a3,
            ctx.tenant_id,
            esquemas.WebhookCriar.model_validate(
                {
                    "nome": f"webhook-pag-{i}-{uuid.uuid4().hex[:6]}",
                    "url": "https://example.invalid/x",
                    "eventos": ["colaborador.admitido"],
                }
            ),
            None,
        )
    await sessao_f13a3.flush()

    primeira, paginacao1 = await servico.listar_webhooks(sessao_f13a3, ctx.tenant_id, limite=2)
    assert len(primeira) == 2
    assert paginacao1.tem_mais is True
    assert paginacao1.proximo_cursor

    segunda, paginacao2 = await servico.listar_webhooks(
        sessao_f13a3, ctx.tenant_id, limite=2, cursor=paginacao1.proximo_cursor
    )
    assert len(segunda) == 1
    ids_primeira = {w.id for w in primeira}
    ids_segunda = {w.id for w in segunda}
    assert ids_primeira.isdisjoint(ids_segunda)


@pytest.mark.asyncio
async def test_listar_entregas_webhook_inexistente_e_404(sessao_f13a3, contexto_webhooks_f13a3):
    ctx = contexto_webhooks_f13a3
    with pytest.raises(ErroDeAplicacao) as exc:
        await servico.listar_entregas(sessao_f13a3, ctx.tenant_id, uuid.uuid4())
    assert exc.value.codigo == "PONTO-REC-001"


@pytest.mark.asyncio
async def test_listar_entregas_filtra_por_status_evento_e_data(
    sessao_f13a3, contexto_webhooks_f13a3
):
    ctx = contexto_webhooks_f13a3
    webhook, _ = await servico.criar_webhook(
        sessao_f13a3,
        ctx.tenant_id,
        esquemas.WebhookCriar.model_validate(
            {
                "nome": "webhook-entregas",
                "url": "https://example.invalid/x",
                "eventos": ["colaborador.admitido"],
            }
        ),
        None,
    )
    await sessao_f13a3.flush()

    entrega_ok = uuid.uuid4()
    entrega_dlq = uuid.uuid4()
    for entrega_id, status in ((entrega_ok, "sucesso"), (entrega_dlq, "dlq")):
        await sessao_f13a3.execute(
            text(
                "INSERT INTO webhook_entregas "
                "(id, tenant_id, webhook_id, evento, evento_id, payload, tentativa, status) "
                "VALUES (:id, :t, :w, 'colaborador.admitido', :eid, '{}'::jsonb, 1, :status)"
            ),
            {
                "id": entrega_id,
                "t": ctx.tenant_id,
                "w": webhook.id,
                "eid": uuid.uuid4(),
                "status": status,
            },
        )
    await sessao_f13a3.flush()

    linhas, _ = await servico.listar_entregas(
        sessao_f13a3, ctx.tenant_id, webhook.id, status="dlq", evento="colaborador.admitido"
    )
    assert {linha.id for linha in linhas} == {entrega_dlq}

    entrega = await servico.obter_entrega(sessao_f13a3, ctx.tenant_id, webhook.id, entrega_ok)
    assert entrega.status == "sucesso"

    with pytest.raises(ErroDeAplicacao) as exc:
        await servico.obter_entrega(sessao_f13a3, ctx.tenant_id, webhook.id, uuid.uuid4())
    assert exc.value.codigo == "PONTO-REC-001"

    resposta = servico.montar_resposta_entrega(entrega)
    assert resposta.status.value == "sucesso"
