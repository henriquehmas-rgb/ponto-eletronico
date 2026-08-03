"""T2 -- rotas novas de `admin` (RFC-016: `listarApiKeys`/`criarApiKey`/
`revogarApiKey`) e o retrofit de idempotência genérica (T3) em
`criarApiClient` (F13/A1).

Testa via HTTP real (`TestClient` contra `app.main:app`, mesmo padrão que
`tests/f1/autenticacao/test_oauth.py` já usa), com
`app.dependency_overrides[obter_sujeito]` substituindo a resolução de RBAC
por um `Sujeito` fixo com as permissões que RFC-016 exige (`api_clients.
ler/criar/editar`) -- isolando "a rota/serviço desta fase fazem a coisa
certa" de "o RBAC do F1 concede a permissão certa" (já coberto pela própria
suíte de F1).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.core.seguranca import Sujeito, obter_sujeito
from tests.f13.conftest import ContextoF13


def _sujeito_fixo(tenant_id: uuid.UUID, permissoes: set[str]) -> object:
    usuario_id = uuid.uuid4()

    async def _fake() -> Sujeito:
        return Sujeito(
            usuario_id=usuario_id,
            tenant_id=tenant_id,
            email="admin-teste@exemplo.com.br",
            perfis=("teste",),
            permissoes=frozenset(permissoes),
            autenticado=True,
        )

    return _fake


@pytest.fixture
def cliente_admin(contexto_f13: ContextoF13) -> Iterator[TestClient]:
    from app.main import app

    app.dependency_overrides[obter_sujeito] = _sujeito_fixo(
        contexto_f13.tenant_id,
        {"api_clients.ler", "api_clients.criar", "api_clients.editar"},
    )
    try:
        with TestClient(app, raise_server_exceptions=True) as cliente:
            yield cliente
    finally:
        app.dependency_overrides.pop(obter_sujeito, None)


def _cabecalhos(tenant_slug: str, *, idempotencia: str | None = None) -> dict[str, str]:
    cabecalhos = {"X-Tenant": tenant_slug}
    if idempotencia:
        cabecalhos["Idempotency-Key"] = idempotencia
    return cabecalhos


def _criar_api_client_http(
    cliente_admin: TestClient, contexto_f13: ContextoF13, *, ambiente: str = "producao"
) -> dict:
    resposta = cliente_admin.post(
        "/v1/admin/api-clients",
        json={
            "nome": f"Cliente de teste {uuid.uuid4().hex[:8]}",
            "ambiente": ambiente,
            "escopos": ["marcacoes:ler", "colaboradores:ler"],
        },
        headers=_cabecalhos(contexto_f13.tenant_slug, idempotencia=str(uuid.uuid4())),
    )
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


async def test_criar_api_client_segredo_autentica_via_oauth_token(
    cliente_admin: TestClient, contexto_f13: ContextoF13
) -> None:
    """Round-trip real: `criarApiClient` -> `emitirTokenOAuth` com o segredo
    devolvido. Prova que `client_secret_hash` gravado por `criar_api_client`
    (rbac/servico.py) e um hash Argon2id valido para `autenticar_client`
    (identidade/tokens/oauth.py) -- regressao do bug em que
    `criar_api_client` gravava SHA-256 puro e todo cliente novo ficava
    permanentemente incapaz de autenticar (`verificar_hash` rejeita qualquer
    string que nao seja um hash Argon2id valido, sem levantar excecao)."""
    api_client = _criar_api_client_http(cliente_admin, contexto_f13)
    client_id = api_client["cliente"]["clientId"]
    client_secret = api_client["clientSecret"]

    resposta = cliente_admin.post(
        "/v1/auth/token",
        json={
            "grantType": "client_credentials",
            "clientId": client_id,
            "clientSecret": client_secret,
        },
        headers={
            "X-Tenant": contexto_f13.tenant_slug,
            "Idempotency-Key": str(uuid.uuid4()),
        },
    )
    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()
    assert corpo["accessToken"]
    assert corpo["tokenType"] == "Bearer"


async def test_criar_api_client_segredo_errado_nao_autentica(
    cliente_admin: TestClient, contexto_f13: ContextoF13
) -> None:
    api_client = _criar_api_client_http(cliente_admin, contexto_f13)
    client_id = api_client["cliente"]["clientId"]

    resposta = cliente_admin.post(
        "/v1/auth/token",
        json={
            "grantType": "client_credentials",
            "clientId": client_id,
            "clientSecret": "segredo-errado-nunca-emitido",
        },
        headers={
            "X-Tenant": contexto_f13.tenant_slug,
            "Idempotency-Key": str(uuid.uuid4()),
        },
    )
    assert resposta.status_code == 401, resposta.text


async def test_criar_api_key_devolve_valor_em_claro_uma_vez(
    cliente_admin: TestClient, contexto_f13: ContextoF13
) -> None:
    api_client = _criar_api_client_http(cliente_admin, contexto_f13)
    api_client_id = api_client["cliente"]["id"]

    resposta = cliente_admin.post(
        f"/v1/admin/api-clients/{api_client_id}/chaves",
        json={"rotulo": "chave de teste", "escopos": ["marcacoes:ler"]},
        headers=_cabecalhos(contexto_f13.tenant_slug, idempotencia=str(uuid.uuid4())),
    )
    assert resposta.status_code == 201, resposta.text
    corpo = resposta.json()
    # `oauth.gerar_api_key` (F1, reaproveitada, nunca reimplementada) devolve
    # o valor em claro como o token bruto (`secrets.token_urlsafe`); o rotulo
    # "pk_<ambiente>_<8 chars>" e um PREFIXO DE EXIBICAO separado
    # (`apiKey.prefixo`), nao um literal dentro do proprio valor da chave.
    assert corpo["chave"]
    assert corpo["apiKey"]["prefixo"].startswith("pk_prd_")
    assert "hash" not in corpo["apiKey"]


async def test_criar_api_key_ambiente_nao_excede_o_do_cliente(
    cliente_admin: TestClient, contexto_f13: ContextoF13
) -> None:
    api_client = _criar_api_client_http(cliente_admin, contexto_f13, ambiente="sandbox")
    api_client_id = api_client["cliente"]["id"]

    resposta = cliente_admin.post(
        f"/v1/admin/api-clients/{api_client_id}/chaves",
        json={"ambiente": "producao", "escopos": ["marcacoes:ler"]},
        headers=_cabecalhos(contexto_f13.tenant_slug, idempotencia=str(uuid.uuid4())),
    )
    assert resposta.status_code == 400, resposta.text
    assert resposta.json()["codigo"] == "PONTO-VAL-001"


async def test_criar_api_key_escopo_fora_do_cliente_e_perm_003(
    cliente_admin: TestClient, contexto_f13: ContextoF13
) -> None:
    api_client = _criar_api_client_http(cliente_admin, contexto_f13)
    api_client_id = api_client["cliente"]["id"]

    resposta = cliente_admin.post(
        f"/v1/admin/api-clients/{api_client_id}/chaves",
        json={"escopos": ["escopo:que:o:cliente:nao:tem"]},
        headers=_cabecalhos(contexto_f13.tenant_slug, idempotencia=str(uuid.uuid4())),
    )
    assert resposta.status_code == 403, resposta.text
    assert resposta.json()["codigo"] == "PONTO-PERM-003"


async def test_listar_api_keys_nunca_devolve_hash(
    cliente_admin: TestClient, contexto_f13: ContextoF13
) -> None:
    api_client = _criar_api_client_http(cliente_admin, contexto_f13)
    api_client_id = api_client["cliente"]["id"]
    cliente_admin.post(
        f"/v1/admin/api-clients/{api_client_id}/chaves",
        json={"escopos": ["marcacoes:ler"]},
        headers=_cabecalhos(contexto_f13.tenant_slug, idempotencia=str(uuid.uuid4())),
    )

    resposta = cliente_admin.get(
        f"/v1/admin/api-clients/{api_client_id}/chaves",
        headers=_cabecalhos(contexto_f13.tenant_slug),
    )
    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()
    assert len(corpo["dados"]) == 1
    assert "hash" not in corpo["dados"][0]
    assert "chave" not in corpo["dados"][0]


async def test_revogar_api_key_e_idempotente_por_natureza(
    cliente_admin: TestClient, contexto_f13: ContextoF13
) -> None:
    api_client = _criar_api_client_http(cliente_admin, contexto_f13)
    api_client_id = api_client["cliente"]["id"]
    criada = cliente_admin.post(
        f"/v1/admin/api-clients/{api_client_id}/chaves",
        json={"escopos": ["marcacoes:ler"]},
        headers=_cabecalhos(contexto_f13.tenant_slug, idempotencia=str(uuid.uuid4())),
    ).json()
    chave_id = criada["apiKey"]["id"]

    resposta_1 = cliente_admin.delete(
        f"/v1/admin/api-clients/{api_client_id}/chaves/{chave_id}",
        headers=_cabecalhos(contexto_f13.tenant_slug, idempotencia=str(uuid.uuid4())),
    )
    assert resposta_1.status_code == 204

    resposta_2 = cliente_admin.delete(
        f"/v1/admin/api-clients/{api_client_id}/chaves/{chave_id}",
        headers=_cabecalhos(contexto_f13.tenant_slug, idempotencia=str(uuid.uuid4())),
    )
    assert resposta_2.status_code == 204


async def test_criar_api_client_idempotencia_replay_mesma_chave_mesmo_corpo(
    cliente_admin: TestClient, contexto_f13: ContextoF13
) -> None:
    chave_idem = str(uuid.uuid4())
    corpo = {
        "nome": f"Cliente idempotente {uuid.uuid4().hex[:8]}",
        "ambiente": "producao",
        "escopos": ["marcacoes:ler"],
    }
    cabecalhos = _cabecalhos(contexto_f13.tenant_slug, idempotencia=chave_idem)

    primeira = cliente_admin.post("/v1/admin/api-clients", json=corpo, headers=cabecalhos)
    assert primeira.status_code == 201
    assert primeira.headers["Idempotency-Replayed"] == "false"

    segunda = cliente_admin.post("/v1/admin/api-clients", json=corpo, headers=cabecalhos)
    assert segunda.status_code == 201
    assert segunda.headers["Idempotency-Replayed"] == "true"
    # Mesmo segredo devolvido -- prova que a segunda chamada NUNCA reexecutou
    # `criar_api_client` (um segundo segredo seria gerado do zero).
    assert segunda.json()["clientSecret"] == primeira.json()["clientSecret"]
    assert segunda.json()["cliente"]["id"] == primeira.json()["cliente"]["id"]


async def test_criar_api_client_idempotencia_chave_reused_corpo_diferente_e_idem_002(
    cliente_admin: TestClient, contexto_f13: ContextoF13
) -> None:
    chave_idem = str(uuid.uuid4())
    cabecalhos = _cabecalhos(contexto_f13.tenant_slug, idempotencia=chave_idem)

    primeira = cliente_admin.post(
        "/v1/admin/api-clients",
        json={"nome": f"Cliente A {uuid.uuid4().hex[:8]}", "escopos": ["marcacoes:ler"]},
        headers=cabecalhos,
    )
    assert primeira.status_code == 201

    segunda = cliente_admin.post(
        "/v1/admin/api-clients",
        json={"nome": f"Cliente B {uuid.uuid4().hex[:8]}", "escopos": ["colaboradores:ler"]},
        headers=cabecalhos,
    )
    assert segunda.status_code == 409, segunda.text
    assert segunda.json()["codigo"] == "PONTO-IDEM-002"
