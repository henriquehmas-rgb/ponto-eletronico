"""T7 -- OAuth 2.0 client credentials e chaves de API."""

from __future__ import annotations

import base64

from fastapi.testclient import TestClient
from ponto_contracts import ApiClient

from app.db.sessao import aplicar_tenant
from app.identidade.autenticacao.senha import verificar_hash
from app.identidade.tokens import oauth as oauth_mod
from tests.f1.autenticacao.conftest import IdentidadeDeTeste, cabecalhos


async def _cadastrar_client(
    sessao_db, identidade: IdentidadeDeTeste, *, escopos: list[str]
) -> tuple[str, str]:
    """Cria um `api_clients` ativo e devolve `(client_id, client_secret_em_claro)`."""
    await aplicar_tenant(sessao_db, str(identidade.tenant_id))
    client_id = f"client-{identidade.tenant_slug}"
    segredo, hash_ = oauth_mod.gerar_client_secret()
    sessao_db.add(
        ApiClient(
            tenant_id=identidade.tenant_id,
            nome="Integracao de teste",
            client_id=client_id,
            client_secret_hash=hash_,
            tipo="confidencial",
            ambiente="sandbox",
            escopos=escopos,
            status="ativo",
        )
    )
    await sessao_db.commit()
    return client_id, segredo


def _pedir_token(
    cliente: TestClient,
    tenant_slug: str,
    *,
    client_id: str,
    client_secret: str,
    scope: str | None = None,
):
    corpo = {
        "grantType": "client_credentials",
        "clientId": client_id,
        "clientSecret": client_secret,
    }
    if scope is not None:
        corpo["scope"] = scope
    return cliente.post("/v1/auth/token", json=corpo, headers=cabecalhos(tenant_slug))


async def test_emite_token_com_escopo_concedido(
    cliente: TestClient, identidade: IdentidadeDeTeste, sessao_db
) -> None:
    client_id, segredo = await _cadastrar_client(
        sessao_db, identidade, escopos=["marcacoes:ler", "jornadas:ler"]
    )
    resposta = _pedir_token(
        cliente,
        identidade.tenant_slug,
        client_id=client_id,
        client_secret=segredo,
        scope="marcacoes:ler",
    )
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["accessToken"]
    assert corpo["tokenType"] == "Bearer"
    assert corpo["scope"] == "marcacoes:ler"


async def test_escopo_fora_do_concedido_responde_perm_003(
    cliente: TestClient, identidade: IdentidadeDeTeste, sessao_db
) -> None:
    client_id, segredo = await _cadastrar_client(sessao_db, identidade, escopos=["marcacoes:ler"])
    resposta = _pedir_token(
        cliente,
        identidade.tenant_slug,
        client_id=client_id,
        client_secret=segredo,
        scope="marcacoes:escrever",
    )
    assert resposta.status_code == 403
    assert resposta.json()["codigo"] == "PONTO-PERM-003"


async def test_sem_escopo_pedido_concede_todos_os_do_cliente(
    cliente: TestClient, identidade: IdentidadeDeTeste, sessao_db
) -> None:
    client_id, segredo = await _cadastrar_client(
        sessao_db, identidade, escopos=["marcacoes:ler", "jornadas:ler"]
    )
    resposta = _pedir_token(
        cliente, identidade.tenant_slug, client_id=client_id, client_secret=segredo
    )
    assert resposta.status_code == 200
    escopos_devolvidos = set(resposta.json()["scope"].split())
    assert escopos_devolvidos == {"marcacoes:ler", "jornadas:ler"}


async def test_client_secret_incorreto_responde_auth_012(
    cliente: TestClient, identidade: IdentidadeDeTeste, sessao_db
) -> None:
    client_id, _segredo_correto = await _cadastrar_client(
        sessao_db, identidade, escopos=["marcacoes:ler"]
    )
    resposta = _pedir_token(
        cliente,
        identidade.tenant_slug,
        client_id=client_id,
        client_secret="segredo-completamente-errado",  # noqa: S106 -- valor de teste, nao segredo real.
    )
    assert resposta.status_code == 401
    assert resposta.json()["codigo"] == "PONTO-AUTH-012"


async def test_client_id_inexistente_responde_auth_012(
    cliente: TestClient, identidade: IdentidadeDeTeste
) -> None:
    resposta = _pedir_token(
        cliente,
        identidade.tenant_slug,
        client_id="client-que-nao-existe",
        client_secret="qualquer",  # noqa: S106 -- valor de teste, nao segredo real.
    )
    assert resposta.status_code == 401
    assert resposta.json()["codigo"] == "PONTO-AUTH-012"


async def test_credenciais_via_authorization_basic_funcionam(
    cliente: TestClient, identidade: IdentidadeDeTeste, sessao_db
) -> None:
    client_id, segredo = await _cadastrar_client(sessao_db, identidade, escopos=["marcacoes:ler"])
    basico = base64.b64encode(f"{client_id}:{segredo}".encode()).decode("ascii")
    resposta = cliente.post(
        "/v1/auth/token",
        json={"grantType": "client_credentials"},
        headers={**cabecalhos(identidade.tenant_slug), "Authorization": f"Basic {basico}"},
    )
    assert resposta.status_code == 200
    assert resposta.json()["accessToken"]


def test_segredo_do_cliente_e_devolvido_uma_unica_vez_e_o_banco_guarda_hash() -> None:
    """`gerar_client_secret` e a primitiva por tras de `criarApiClient` (F1/A3):
    o valor em claro so existe no retorno desta chamada -- o que persiste
    (`client_secret_hash`) e Argon2id, nunca o segredo, e a unica forma de
    confirmar posse depois e verificando o hash, nao comparando string."""
    segredo, hash_ = oauth_mod.gerar_client_secret()
    assert segredo != hash_
    assert verificar_hash(hash_, segredo)
    assert not verificar_hash(hash_, segredo + "x")
