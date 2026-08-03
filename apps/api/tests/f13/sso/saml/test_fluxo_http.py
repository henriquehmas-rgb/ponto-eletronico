"""Fim a fim, contra a aplicacao real (T22, A10, "pronto quando: login
end-to-end contra um IdP de teste resulta em sessao valida; assinatura de
asserção adulterada e rejeitada").

`GET /v1/sso/{provedor}/iniciar` (provedor=saml) -> redireciona ao IdP falso
com um AuthnRequest real; `POST /v1/sso/saml/acs` com o SAMLResponse
correspondente (assinado pelo mesmo par de chaves do IdP configurado para o
tenant) -> 302 com os tokens de sessao no fragmento, `credenciais`/`sessoes`
gravadas no banco. A mesma resposta com o NameID trocado depois de assinada
-> 401 PONTO-AUTH-004, sem sessao nenhuma criada.
"""

from __future__ import annotations

import zlib
from base64 import b64decode
from urllib.parse import parse_qs, unquote, urlparse

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from lxml import etree
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.f13.sso.saml.conftest import (
    IdpFalso,
    TenantComUsuario,
    adulterar_name_id,
    montar_saml_response,
)

_NS_SAMLP = {"samlp": "urn:oasis:names:tc:SAML:2.0:protocol"}


@pytest.fixture
def cliente() -> TestClient:
    """Forca `app.db.sessao` a criar uma engine nova, presa ao loop deste
    `TestClient` -- mesma correcao que `tests/f13/sso/oidc/
    test_router_fluxo_completo.py:_engine_da_app_no_loop_do_teste` ja aplica.
    Sem isto, rodando junto de OUTROS arquivos que tambem usam `TestClient`
    (toda a suite de `tests/f13`), a engine global fica presa ao event loop
    de um `with TestClient(...)` ANTERIOR (ja encerrado) -- a query de
    `sessao_com_tenant_resolvido` roda contra uma conexao morta e devolve
    "tenant nao encontrado" (404) mesmo com o tenant recem-inserido e
    comitado, achado real ao rodar `pytest tests/f13` inteiro (nunca
    reproduz com este arquivo isolado)."""
    from app.core.config import obter_configuracao
    from app.db import sessao as db_sessao
    from app.main import app

    obter_configuracao.cache_clear()
    db_sessao._engine = None
    db_sessao._fabrica = None
    with TestClient(app, raise_server_exceptions=True) as cliente_de_teste:
        yield cliente_de_teste


def _extrair_saml_request_id(saml_request_b64: str) -> str:
    """Decodifica o AuthnRequest (base64 + deflate cru, perfil HTTP-Redirect)
    e devolve o atributo `ID`."""
    bruto = zlib.decompress(b64decode(saml_request_b64), -15)
    # S320: XML gerado por `app.identidade.sso.saml.protocolo` (nosso proprio
    # AuthnRequest, capturado do redirect que a propria aplicacao emitiu
    # neste teste), nunca dado externo nao confiavel.
    doc = etree.fromstring(bruto)  # noqa: S320
    valor = doc.get("ID")
    assert valor
    return valor


def _iniciar_e_capturar_redirect(cliente: TestClient, tenant: TenantComUsuario) -> tuple[str, str]:
    """GET iniciar (provedor=saml) e devolve `(saml_request_b64, relay_state)`
    extraidos do `Location` do 302."""
    resposta = cliente.get(
        "/v1/sso/saml/iniciar", params={"tenant": tenant.slug}, follow_redirects=False
    )
    assert resposta.status_code == 302, resposta.text
    location = resposta.headers["location"]
    query = parse_qs(urlparse(location).query)
    assert "SAMLRequest" in query
    assert "RelayState" in query
    return query["SAMLRequest"][0], query["RelayState"][0]


async def test_iniciar_redireciona_ao_idp_configurado(
    cliente: TestClient, tenant_com_saml_configurado: TenantComUsuario
) -> None:
    resposta = cliente.get(
        "/v1/sso/saml/iniciar",
        params={"tenant": tenant_com_saml_configurado.slug},
        follow_redirects=False,
    )
    assert resposta.status_code == 302, resposta.text
    location = resposta.headers["location"]
    assert location.startswith("https://idp-teste-f13-a10.example.com/sso")
    query = parse_qs(urlparse(location).query)
    assert query["SAMLRequest"][0]
    assert query["RelayState"][0]


async def test_iniciar_sem_configuracao_saml_responde_404(
    cliente: TestClient, tenant_com_usuario: TenantComUsuario
) -> None:
    """Tenant existe mas nunca configurou IdP SAML -- `tenant_com_usuario`
    (sem o fixture `tenant_com_saml_configurado`)."""
    resposta = cliente.get(
        "/v1/sso/saml/iniciar", params={"tenant": tenant_com_usuario.slug}, follow_redirects=False
    )
    assert resposta.status_code == 404, resposta.text
    assert resposta.json()["codigo"] == "PONTO-REC-001"


async def test_login_saml_fim_a_fim_gera_sessao_valida(
    cliente: TestClient,
    tenant_com_saml_configurado: TenantComUsuario,
    idp_falso: IdpFalso,
    engine: AsyncEngine,
) -> None:
    saml_request_b64, relay_state = _iniciar_e_capturar_redirect(
        cliente, tenant_com_saml_configurado
    )
    request_id = _extrair_saml_request_id(saml_request_b64)

    saml_response_b64 = montar_saml_response(
        idp_falso,
        name_id=tenant_com_saml_configurado.email,
        audience="https://api.ponto.teste.local/v1/sso/saml/acs",
        acs_url="https://api.ponto.teste.local/v1/sso/saml/acs",
        issuer="https://idp-teste-f13-a10.example.com/metadata",
        in_response_to=request_id,
    )

    resposta = cliente.post(
        "/v1/sso/saml/acs",
        data={"SAMLResponse": saml_response_b64, "RelayState": unquote(relay_state)},
        follow_redirects=False,
    )

    assert resposta.status_code == 302, resposta.text
    location = resposta.headers["location"]
    assert location.startswith("https://app.ponto.teste.local/sso/concluir#")
    fragmento = location.split("#", 1)[1]
    campos = parse_qs(fragmento)
    assert campos["accessToken"][0]
    assert campos["refreshToken"][0]
    assert campos["tokenType"][0] == "Bearer"
    assert int(campos["expiresIn"][0]) > 0

    sessao_id = campos["sessaoId"][0]
    async with engine.begin() as conexao:
        await conexao.execute(
            text_set_tenant(),
            {"tenant": str(tenant_com_saml_configurado.tenant_id)},
        )
        linha = (
            (
                await conexao.execute(
                    sa.text("SELECT canal, usuario_id FROM sessoes WHERE id = :id"),
                    {"id": sessao_id},
                )
            )
            .mappings()
            .one()
        )
    assert linha["canal"] == "web"
    assert str(linha["usuario_id"]) == str(tenant_com_saml_configurado.usuario_id)


async def test_login_saml_com_assercao_adulterada_e_rejeitado_e_nao_cria_sessao(
    cliente: TestClient,
    tenant_com_saml_configurado: TenantComUsuario,
    idp_falso: IdpFalso,
    engine: AsyncEngine,
) -> None:
    saml_request_b64, relay_state = _iniciar_e_capturar_redirect(
        cliente, tenant_com_saml_configurado
    )
    request_id = _extrair_saml_request_id(saml_request_b64)

    saml_response_legitimo = montar_saml_response(
        idp_falso,
        name_id=tenant_com_saml_configurado.email,
        audience="https://api.ponto.teste.local/v1/sso/saml/acs",
        acs_url="https://api.ponto.teste.local/v1/sso/saml/acs",
        issuer="https://idp-teste-f13-a10.example.com/metadata",
        in_response_to=request_id,
    )
    saml_response_adulterado = adulterar_name_id(
        saml_response_legitimo,
        de=tenant_com_saml_configurado.email,
        para="atacante@fora-do-tenant.teste",
    )

    async with engine.begin() as conexao:
        await conexao.execute(
            text_set_tenant(), {"tenant": str(tenant_com_saml_configurado.tenant_id)}
        )
        sessoes_antes = (
            await conexao.execute(
                sa.text("SELECT count(*) FROM sessoes WHERE usuario_id = :usuario_id"),
                {"usuario_id": str(tenant_com_saml_configurado.usuario_id)},
            )
        ).scalar_one()

    resposta = cliente.post(
        "/v1/sso/saml/acs",
        data={"SAMLResponse": saml_response_adulterado, "RelayState": unquote(relay_state)},
        follow_redirects=False,
    )

    assert resposta.status_code == 401, resposta.text
    assert resposta.json()["codigo"] == "PONTO-AUTH-004"

    async with engine.begin() as conexao:
        await conexao.execute(
            text_set_tenant(), {"tenant": str(tenant_com_saml_configurado.tenant_id)}
        )
        sessoes_depois = (
            await conexao.execute(
                sa.text("SELECT count(*) FROM sessoes WHERE usuario_id = :usuario_id"),
                {"usuario_id": str(tenant_com_saml_configurado.usuario_id)},
            )
        ).scalar_one()
    assert sessoes_depois == sessoes_antes


def text_set_tenant() -> sa.TextClause:
    return sa.text("SELECT set_config('app.tenant_id', :tenant, true)")
