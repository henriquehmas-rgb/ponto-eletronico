"""Fluxo completo via HTTP real (ASGI, sem TestClient sincrono -- ver nota de
loop abaixo): `GET /v1/sso/google/iniciar` -> `GET /v1/sso/google/callback`,
contra a aplicacao FastAPI de verdade (`app.main.app`) e o banco de teste
exclusivo (`ponto_f13_a9`).

Cobre o criterio de aceite 11/T21 do PCF de ponta a ponta pela camada HTTP
(nao so pela camada de servico, ja coberta por `test_resolucao.py`): "login
end-to-end contra um provedor de teste resulta em sessao valida do sistema,
com credenciais.tipo='sso' gravada corretamente".

A troca `code` -> `id_token` (`protocolo.trocar_code_por_claims`) e
substituida por um dublê (nunca rede real -- ADR-013): o resto do fluxo
(resolucao de tenant, `state` assinado, vinculo de credencial, emissao de
sessao, formato da resposta) roda de ponta a ponta sem mock nenhum.

**Por que `httpx.ASGITransport` e nao `fastapi.testclient.TestClient`.**
`TestClient` roda sua PROPRIA event loop sincrona por chamada; a engine
assincrona de `app.db.sessao` fica presa ao loop em que nasceu (mesmo motivo
documentado em `app/db/sessao.py`). Usar `httpx.AsyncClient` com
`ASGITransport` dentro de um teste `async def` mantem a chamada HTTP e as
asserções de banco no MESMO loop (o do proprio teste, gerido pelo
`pytest-asyncio`), sem precisar resetar a engine entre a chamada e a
asserção.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
import sqlalchemy as sa
from ponto_contracts import Credencial

from app.identidade.sso.oidc.protocolo import ClaimsIdToken

from .conftest import ContextoSsoOidcF13

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
async def _engine_da_app_no_loop_do_teste():
    """Forca `app.db.sessao` a criar uma engine nova, presa ao loop deste teste."""
    from app.core.config import obter_configuracao
    from app.db import sessao as db_sessao

    obter_configuracao.cache_clear()
    db_sessao._engine = None
    db_sessao._fabrica = None
    yield
    if db_sessao._engine is not None:
        await db_sessao.encerrar_engine()


@pytest.fixture
async def cliente_http():
    from app.main import app

    transporte = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transporte, base_url="http://testserver", follow_redirects=False
    ) as cliente:
        yield cliente


def _vinculo_e_hash() -> tuple[str, str]:
    """RFC-019: par (valor bruto, hash SHA-256 hex) que os testes usam para
    simular o que `botao-login-oidc.tsx` gera no navegador de verdade."""
    import hashlib
    import uuid as _uuid

    vinculo = _uuid.uuid4().hex
    return vinculo, hashlib.sha256(vinculo.encode("utf-8")).hexdigest()


async def test_login_federado_google_ponta_a_ponta(
    cliente_http: httpx.AsyncClient,
    contexto_sso_oidc_f13a9: ContextoSsoOidcF13,
    sessao_f13a9,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vinculo, vinculo_hash = _vinculo_e_hash()
    tenant_slug_resp = await cliente_http.get(
        "/v1/sso/google/iniciar",
        params={"tenant": str(contexto_sso_oidc_f13a9.tenant_id), "vinculoHash": vinculo_hash},
    )
    assert tenant_slug_resp.status_code == 302
    location = tenant_slug_resp.headers["location"]
    partes = urlsplit(location)
    assert partes.netloc == "accounts.google.com"
    query = parse_qs(partes.query)
    state = query["state"][0]
    nonce = query["nonce"][0]
    assert query["client_id"] == ["cliente-google-teste-f13a9"]

    async def _claims_falsas(*args: object, **kwargs: object) -> ClaimsIdToken:
        assert kwargs["nonce_esperado"] == nonce
        return ClaimsIdToken(
            sub="sub-e2e-google-1",
            email=contexto_sso_oidc_f13a9.usuario_email,
            email_verificado=True,
            tid=None,
            hd=None,
        )

    from app.routers import sso as sso_router

    monkeypatch.setattr(sso_router.protocolo, "trocar_code_por_claims", _claims_falsas)

    callback_resp = await cliente_http.get(
        "/v1/sso/google/callback",
        params={"code": "codigo-de-autorizacao-falso", "state": state, "vinculo": vinculo},
    )
    assert callback_resp.status_code == 200
    corpo = callback_resp.json()
    assert corpo["mfaRequerido"] is False
    assert corpo["tokenType"] == "Bearer"
    assert corpo["accessToken"]
    assert corpo["refreshToken"]
    assert corpo["usuario"]["email"] == contexto_sso_oidc_f13a9.usuario_email

    credencial = (
        await sessao_f13a9.execute(
            sa.select(Credencial).where(
                Credencial.tenant_id == contexto_sso_oidc_f13a9.tenant_id,
                Credencial.usuario_id == contexto_sso_oidc_f13a9.usuario_id,
                Credencial.tipo == "sso",
            )
        )
    ).scalar_one()
    assert credencial.provedor_sso == "google"
    assert credencial.identificador_externo == "sub-e2e-google-1"


async def test_iniciar_sso_provedor_nao_habilitado_no_tenant_responde_erro(
    cliente_http: httpx.AsyncClient,
    sessao_f13a9,
    contexto_sso_oidc_f13a9: ContextoSsoOidcF13,
) -> None:
    """Depende de `contexto_sso_oidc_f13a9` so para garantir que `DATABASE_URL`
    aponta para o banco de teste (efeito colateral da fixture) -- o tenant
    semeado por ela nao e usado aqui, este teste cria o PROPRIO tenant, sem
    nenhuma configuracao de SSO."""
    import uuid

    from .conftest import aplicar_tenant_teste

    tenant_sem_sso = uuid.uuid4()
    await aplicar_tenant_teste(sessao_f13a9, tenant_sem_sso)
    await sessao_f13a9.execute(
        sa.text(
            "INSERT INTO tenants (id, slug, razao_social, nome_exibicao, status) "
            "VALUES (:id, :slug, :razao, :nome, 'ativo')"
        ),
        {
            "id": tenant_sem_sso,
            "slug": f"sem-sso-{uuid.uuid4().hex[:8]}",
            "razao": "Tenant sem SSO",
            "nome": "Tenant sem SSO",
        },
    )
    await sessao_f13a9.commit()

    _vinculo, vinculo_hash = _vinculo_e_hash()
    resposta = await cliente_http.get(
        "/v1/sso/google/iniciar",
        params={"tenant": str(tenant_sem_sso), "vinculoHash": vinculo_hash},
    )
    assert resposta.status_code == 404
    corpo = resposta.json()
    assert corpo["codigo"] == "PONTO-TEN-001"


async def test_iniciar_sso_sem_vinculo_hash_responde_400(
    cliente_http: httpx.AsyncClient, contexto_sso_oidc_f13a9: ContextoSsoOidcF13
) -> None:
    """RFC-019: `vinculoHash` e exigido para google/entra_id antes de
    qualquer outra checagem -- sem ele, nao ha como o `callback` provar que
    o mesmo navegador que iniciou o fluxo e o que esta concluindo."""
    resposta = await cliente_http.get(
        "/v1/sso/google/iniciar", params={"tenant": str(contexto_sso_oidc_f13a9.tenant_id)}
    )
    assert resposta.status_code == 400
    assert resposta.json()["codigo"] == "PONTO-VAL-001"


async def test_callback_sso_state_invalido_responde_401(
    cliente_http: httpx.AsyncClient, contexto_sso_oidc_f13a9: ContextoSsoOidcF13
) -> None:
    resposta = await cliente_http.get(
        "/v1/sso/google/callback",
        params={"code": "x", "state": "state-invalido-e-adulterado", "vinculo": "qualquer-coisa"},
    )
    assert resposta.status_code == 401


async def test_callback_sso_sem_vinculo_responde_401(
    cliente_http: httpx.AsyncClient, contexto_sso_oidc_f13a9: ContextoSsoOidcF13
) -> None:
    """RFC-019: `state` valido sem `vinculo` nenhum e rejeitado -- prova que
    a checagem funciona mesmo quando o restante do `state` esta correto."""
    vinculo, vinculo_hash = _vinculo_e_hash()
    iniciar_resp = await cliente_http.get(
        "/v1/sso/google/iniciar",
        params={"tenant": str(contexto_sso_oidc_f13a9.tenant_id), "vinculoHash": vinculo_hash},
    )
    state = parse_qs(urlsplit(iniciar_resp.headers["location"]).query)["state"][0]

    resposta = await cliente_http.get(
        "/v1/sso/google/callback", params={"code": "x", "state": state}
    )
    assert resposta.status_code == 401
    assert resposta.json()["codigo"] == "PONTO-AUTH-004"


async def test_callback_sso_com_vinculo_de_outro_navegador_e_rejeitado(
    cliente_http: httpx.AsyncClient, contexto_sso_oidc_f13a9: ContextoSsoOidcF13
) -> None:
    """Prova o cenario de login-CSRF que motivou a RFC-019: um `state` valido
    (emitido de verdade por `iniciar`) apresentado com um `vinculo` de OUTRO
    navegador (nao o que gerou o `vinculoHash` embutido no `state`) e
    rejeitado -- exatamente o ataque em que um atacante intercepta o proprio
    `state`/`code` e induz a vitima a completa-los."""
    vinculo_da_vitima, vinculo_hash_da_vitima = _vinculo_e_hash()
    vinculo_do_atacante, _hash_do_atacante = _vinculo_e_hash()
    assert vinculo_da_vitima != vinculo_do_atacante

    iniciar_resp = await cliente_http.get(
        "/v1/sso/google/iniciar",
        params={
            "tenant": str(contexto_sso_oidc_f13a9.tenant_id),
            "vinculoHash": vinculo_hash_da_vitima,
        },
    )
    state = parse_qs(urlsplit(iniciar_resp.headers["location"]).query)["state"][0]

    resposta = await cliente_http.get(
        "/v1/sso/google/callback",
        params={"code": "x", "state": state, "vinculo": vinculo_do_atacante},
    )
    assert resposta.status_code == 401
    assert resposta.json()["codigo"] == "PONTO-AUTH-004"
    assert resposta.json()["codigo"] == "PONTO-AUTH-004"
