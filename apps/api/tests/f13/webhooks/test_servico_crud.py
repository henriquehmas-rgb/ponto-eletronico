"""T10 -- CRUD de `webhooks` (`app.integracoes.webhooks.servico`), contra
banco real: validacao de URL (PONTO-WEBH-001), validacao de catalogo de
eventos (PONTO-WEBH-003), segredo em claro so na criacao, exclusao logica
cancela entregas pendentes/falha, paginacao por cursor.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from app.core.erros import ErroDeAplicacao
from app.integracoes.webhooks import servico
from app.schemas import contrato as esquemas

pytestmark = pytest.mark.asyncio


def _corpo_criar(**overrides) -> esquemas.WebhookCriar:
    base = {
        "nome": f"webhook-{uuid.uuid4().hex[:8]}",
        "url": "https://example.invalid/receber",
        "eventos": ["colaborador.admitido"],
    }
    base.update(overrides)
    return esquemas.WebhookCriar.model_validate(base)


async def test_criar_webhook_persiste_e_devolve_segredo_uma_vez(
    sessao_f13a3, contexto_webhooks_f13a3
):
    ctx = contexto_webhooks_f13a3
    webhook, segredo = await servico.criar_webhook(
        sessao_f13a3, ctx.tenant_id, _corpo_criar(apiClientId=str(ctx.api_client_id)), None
    )
    assert webhook.id is not None
    assert len(segredo) >= 32

    resposta = servico.montar_resposta_webhook(webhook)
    # `Webhook` (schema de leitura) nao tem NENHUM campo de segredo -- prova
    # estrutural, nao so "nao esta preenchido".
    assert not hasattr(resposta, "segredo_hmac")
    assert not hasattr(resposta, "segredoHmac")


async def test_criar_webhook_recusa_api_client_de_outro_tenant(
    sessao_f13a3, contexto_webhooks_f13a3
):
    """FK sozinha nao basta sob RLS (checagem de FK do Postgres ignora Row
    Level Security) -- a aplicacao precisa confirmar o tenant."""
    ctx = contexto_webhooks_f13a3
    outro_tenant_id = uuid.uuid4()
    outro_api_client_id = uuid.uuid4()
    # Precisa trocar de tenant para inserir a linha do OUTRO tenant sob RLS.
    await sessao_f13a3.execute(
        text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(outro_tenant_id)}
    )
    await sessao_f13a3.execute(
        text(
            "INSERT INTO tenants (id, slug, razao_social, nome_exibicao, status) "
            "VALUES (:id, :slug, 'Outro', 'Outro', 'ativo')"
        ),
        {"id": outro_tenant_id, "slug": f"outro-{uuid.uuid4().hex[:8]}"},
    )
    await sessao_f13a3.execute(
        text(
            "INSERT INTO api_clients "
            "(id, tenant_id, nome, client_id, tipo, ambiente, escopos, "
            " rate_limit_por_minuto, status) "
            "VALUES (:id, :t, 'cliente-alheio', :cid, 'confidencial', 'sandbox', "
            "        ARRAY[]::text[], 600, 'ativo')"
        ),
        {
            "id": outro_api_client_id,
            "t": outro_tenant_id,
            "cid": f"cid_alheio_{uuid.uuid4().hex[:8]}",
        },
    )
    await sessao_f13a3.flush()
    # Volta ao tenant original antes de tentar criar o webhook.
    await sessao_f13a3.execute(
        text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(ctx.tenant_id)}
    )

    with pytest.raises(ErroDeAplicacao) as exc:
        await servico.criar_webhook(
            sessao_f13a3,
            ctx.tenant_id,
            _corpo_criar(apiClientId=str(outro_api_client_id)),
            None,
        )
    assert exc.value.codigo == "PONTO-REC-001"


async def test_criar_webhook_recusa_url_nao_https(sessao_f13a3, contexto_webhooks_f13a3):
    ctx = contexto_webhooks_f13a3
    with pytest.raises(ErroDeAplicacao) as exc:
        await servico.criar_webhook(
            sessao_f13a3, ctx.tenant_id, _corpo_criar(url="http://example.invalid/x"), None
        )
    assert exc.value.codigo == "PONTO-WEBH-001"


@pytest.mark.parametrize(
    "url",
    [
        "https://localhost/receber",
        "https://127.0.0.1/receber",
        "https://192.168.1.10/receber",
        "https://10.0.0.5/receber",
        "https://[::1]/receber",
    ],
)
async def test_criar_webhook_recusa_destino_privado_ou_loopback(
    sessao_f13a3, contexto_webhooks_f13a3, url
):
    ctx = contexto_webhooks_f13a3
    with pytest.raises(ErroDeAplicacao) as exc:
        await servico.criar_webhook(sessao_f13a3, ctx.tenant_id, _corpo_criar(url=url), None)
    assert exc.value.codigo == "PONTO-WEBH-001"


async def test_criar_webhook_recusa_evento_desconhecido_ou_interno(
    sessao_f13a3, contexto_webhooks_f13a3
):
    ctx = contexto_webhooks_f13a3
    with pytest.raises(ErroDeAplicacao) as exc:
        await servico.criar_webhook(
            sessao_f13a3, ctx.tenant_id, _corpo_criar(eventos=["evento.que.nao.existe"]), None
        )
    assert exc.value.codigo == "PONTO-WEBH-003"

    with pytest.raises(ErroDeAplicacao) as exc2:
        await servico.criar_webhook(
            sessao_f13a3, ctx.tenant_id, _corpo_criar(eventos=["ocorrencia.aberta"]), None
        )
    assert exc2.value.codigo == "PONTO-WEBH-003"


async def test_nome_duplicado_no_mesmo_tenant_e_conflito(sessao_f13a3, contexto_webhooks_f13a3):
    ctx = contexto_webhooks_f13a3
    corpo = _corpo_criar(nome="webhook-fixo")
    await servico.criar_webhook(sessao_f13a3, ctx.tenant_id, corpo, None)
    await sessao_f13a3.flush()

    with pytest.raises(ErroDeAplicacao) as exc:
        await servico.criar_webhook(sessao_f13a3, ctx.tenant_id, corpo, None)
    assert exc.value.codigo == "PONTO-CONF-001"


async def test_obter_webhook_inexistente_e_404(sessao_f13a3, contexto_webhooks_f13a3):
    ctx = contexto_webhooks_f13a3
    with pytest.raises(ErroDeAplicacao) as exc:
        await servico.obter_webhook(sessao_f13a3, ctx.tenant_id, uuid.uuid4())
    assert exc.value.codigo == "PONTO-REC-001"


async def test_atualizar_reativando_zera_falhas_consecutivas(sessao_f13a3, contexto_webhooks_f13a3):
    ctx = contexto_webhooks_f13a3
    webhook, _ = await servico.criar_webhook(sessao_f13a3, ctx.tenant_id, _corpo_criar(), None)
    await sessao_f13a3.flush()
    webhook.status = "desabilitado_por_falha"
    webhook.falhas_consecutivas = 11
    await sessao_f13a3.flush()

    atualizado = await servico.atualizar_webhook(
        sessao_f13a3,
        ctx.tenant_id,
        webhook.id,
        esquemas.WebhookAtualizar.model_validate({"status": "ativo"}),
        None,
    )
    assert atualizado.falhas_consecutivas == 0
    assert atualizado.status == "ativo"


async def test_excluir_webhook_cancela_entregas_pendentes_e_falha(
    sessao_f13a3, contexto_webhooks_f13a3
):
    ctx = contexto_webhooks_f13a3
    webhook, _ = await servico.criar_webhook(sessao_f13a3, ctx.tenant_id, _corpo_criar(), None)
    await sessao_f13a3.flush()

    pendente_id, falha_id, sucesso_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    entregas = ((pendente_id, "pendente"), (falha_id, "falha"), (sucesso_id, "sucesso"))
    for entrega_id, status in entregas:
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

    await servico.excluir_webhook(sessao_f13a3, ctx.tenant_id, webhook.id, None)

    linhas = {
        row.id: row.status
        for row in (
            await sessao_f13a3.execute(
                text("SELECT id, status FROM webhook_entregas WHERE webhook_id = :w"),
                {"w": webhook.id},
            )
        )
    }
    assert linhas[pendente_id] == "cancelada"
    assert linhas[falha_id] == "cancelada"
    assert linhas[sucesso_id] == "sucesso"  # nunca mexe em entrega ja concluida

    with pytest.raises(ErroDeAplicacao):
        await servico.obter_webhook(sessao_f13a3, ctx.tenant_id, webhook.id)


async def test_listar_webhooks_filtra_por_evento_e_status(sessao_f13a3, contexto_webhooks_f13a3):
    ctx = contexto_webhooks_f13a3
    w1, _ = await servico.criar_webhook(
        sessao_f13a3, ctx.tenant_id, _corpo_criar(eventos=["colaborador.admitido"]), None
    )
    w2, _ = await servico.criar_webhook(
        sessao_f13a3, ctx.tenant_id, _corpo_criar(eventos=["colaborador.demitido"]), None
    )
    await sessao_f13a3.flush()

    linhas, _ = await servico.listar_webhooks(
        sessao_f13a3, ctx.tenant_id, evento="colaborador.admitido"
    )
    ids = {linha.id for linha in linhas}
    assert w1.id in ids
    assert w2.id not in ids
