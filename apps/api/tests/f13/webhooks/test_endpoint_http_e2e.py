"""Teste de ponta a ponta HTTP real de `POST /v1/webhooks` (T10), contra a
aplicacao FastAPI inteira (`app.main.app`) -- exercita
`app.integracoes.webhooks.seguranca.exigir_permissao_ou_escopo` pelo
caminho de CLIENTE (X-API-Key), idempotencia genuina (A1/T3) e o limitador
de taxa (A1/T4) de ponta a ponta, nao so a camada de servico isolada (ja
coberta em `test_servico_crud.py`).

So roda depois que TODOS os routers da fase importam sem erro (depende de
`apps/api/app/routers/__init__.py` conseguir montar a aplicacao inteira --
fora do ownership desta suite, mas necessario para o TestClient funcionar).
"""

from __future__ import annotations

import uuid

import httpx
import pytest
from sqlalchemy import text

from app.identidade.tokens.oauth import gerar_api_key

pytestmark = pytest.mark.asyncio


async def _semear_api_key(
    sessao, *, tenant_id: uuid.UUID, escopos: list[str]
) -> tuple[uuid.UUID, str]:
    chave_bruta, prefixo, hash_sha256 = gerar_api_key()
    api_client_id = uuid.uuid4()
    await sessao.execute(
        text(
            "INSERT INTO api_clients "
            "(id, tenant_id, nome, client_id, tipo, ambiente, escopos, "
            " rate_limit_por_minuto, status) "
            "VALUES (:id, :t, :nome, :cid, 'confidencial', 'sandbox', :escopos, 600, 'ativo')"
        ),
        {
            "id": api_client_id,
            "t": tenant_id,
            "nome": f"cliente-e2e-{uuid.uuid4().hex[:8]}",
            "cid": f"cid_e2e_{uuid.uuid4().hex[:8]}",
            "escopos": escopos,
        },
    )
    chave_id = uuid.uuid4()
    await sessao.execute(
        text(
            "INSERT INTO api_keys "
            "(id, tenant_id, api_client_id, prefixo, hash, ambiente, escopos) "
            "VALUES (:id, :t, :api, :prefixo, :hash, 'sandbox', :escopos)"
        ),
        {
            "id": chave_id,
            "t": tenant_id,
            "api": api_client_id,
            "prefixo": prefixo,
            "hash": hash_sha256,
            "escopos": escopos,
        },
    )
    return api_client_id, chave_bruta


@pytest.fixture
def _tenant_slug(contexto_webhooks_f13a3):
    # `X-Tenant` no `TenantMiddleware` aceita slug OU UUID -- usa o UUID,
    # que ja temos sem precisar de outra consulta.
    return str(contexto_webhooks_f13a3.tenant_id)


async def test_criar_webhook_ponta_a_ponta_via_api_key(
    sessao_f13a3, contexto_webhooks_f13a3, _tenant_slug
):
    from app.db.sessao import encerrar_engine

    ctx = contexto_webhooks_f13a3
    _, chave_bruta = await _semear_api_key(
        sessao_f13a3, tenant_id=ctx.tenant_id, escopos=["webhooks:escrever", "webhooks:ler"]
    )
    await sessao_f13a3.commit()

    # `app.db.sessao` cacheia a propria engine (independente do cache de
    # `obter_configuracao`) -- descarta para reconstruir contra o banco de
    # teste desta suite (`ponto_f13_a3`), mesmo `DATABASE_URL` que
    # `contexto_webhooks_f13a3` ja publicou em `os.environ`.
    await encerrar_engine()

    from app.main import app

    idempotency_key = str(uuid.uuid4())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as cliente:
        resposta = await cliente.post(
            "/v1/webhooks",
            headers={
                "X-Tenant": _tenant_slug,
                "X-API-Key": chave_bruta,
                "Idempotency-Key": idempotency_key,
            },
            json={
                "nome": f"webhook-e2e-{uuid.uuid4().hex[:8]}",
                "url": "https://example.invalid/receber",
                "eventos": ["colaborador.admitido"],
            },
        )

    assert resposta.status_code == 201, resposta.text
    corpo = resposta.json()
    assert corpo["segredoHmac"]
    assert corpo["webhook"]["status"] == "ativo"
    assert resposta.headers.get("Idempotency-Replayed") == "false"
    assert resposta.headers.get("RateLimit-Limit") == "600"

    await encerrar_engine()


async def test_criar_webhook_sem_credencial_e_401(contexto_webhooks_f13a3, _tenant_slug):
    from app.db.sessao import encerrar_engine
    from app.main import app

    await encerrar_engine()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as cliente:
        resposta = await cliente.post(
            "/v1/webhooks",
            headers={"X-Tenant": _tenant_slug, "Idempotency-Key": str(uuid.uuid4())},
            json={
                "nome": "webhook-sem-credencial",
                "url": "https://example.invalid/receber",
                "eventos": ["colaborador.admitido"],
            },
        )

    assert resposta.status_code == 401
    assert resposta.json()["codigo"] == "PONTO-AUTH-002"

    await encerrar_engine()


async def test_criar_webhook_escopo_insuficiente_e_403(
    sessao_f13a3, contexto_webhooks_f13a3, _tenant_slug
):
    from app.db.sessao import encerrar_engine
    from app.main import app

    ctx = contexto_webhooks_f13a3
    _, chave_bruta = await _semear_api_key(
        sessao_f13a3,
        tenant_id=ctx.tenant_id,
        escopos=["webhooks:ler"],  # sem :escrever
    )
    await sessao_f13a3.commit()
    await encerrar_engine()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as cliente:
        resposta = await cliente.post(
            "/v1/webhooks",
            headers={
                "X-Tenant": _tenant_slug,
                "X-API-Key": chave_bruta,
                "Idempotency-Key": str(uuid.uuid4()),
            },
            json={
                "nome": "webhook-sem-escopo",
                "url": "https://example.invalid/receber",
                "eventos": ["colaborador.admitido"],
            },
        )

    assert resposta.status_code == 403
    assert resposta.json()["codigo"] == "PONTO-PERM-003"

    await encerrar_engine()
