"""T1 -- `app.comum.autenticacao_cliente.exigir_escopo` (F13/A1).

Chama a dependência DIRETAMENTE (função assíncrona simples, sem passar pelo
FastAPI `Depends`) contra o banco real: é o jeito mais direto de provar as
quatro combinações que o PCF pede (OAuth válido, API key válida, sem
credencial, escopo insuficiente), mais os casos adversariais que a própria
função documenta (token/chave expirados ou revogados, cliente suspenso,
origem fora de `ips_permitidos`, `X-Tenant` ausente).
"""

from __future__ import annotations

import datetime as dt

import pytest
from starlette.requests import Request

from app.comum.autenticacao_cliente import ClienteAutenticado, exigir_escopo
from app.core.erros import ErroDeAplicacao
from tests.f13.conftest import (
    ContextoF13,
    criar_api_client_teste,
    criar_api_key_teste,
    emitir_oauth_token_teste,
)


def _requisicao(*, ip: str | None = "203.0.113.10") -> Request:
    scope = {
        "type": "http",
        "headers": [],
        "client": (ip, 12345) if ip else None,
        "method": "GET",
        "path": "/v1/teste",
        "query_string": b"",
    }

    async def _receive() -> dict[str, object]:
        return {"type": "http.request", "body": b"", "more_body": False}

    return Request(scope, _receive)


async def _autenticar(
    escopo: str,
    *,
    authorization: str | None = None,
    x_api_key: str | None = None,
    x_tenant: str | None = None,
    ip: str | None = "203.0.113.10",
) -> ClienteAutenticado:
    dependencia = exigir_escopo(escopo)
    return await dependencia(
        request=_requisicao(ip=ip),
        authorization=authorization,
        x_api_key=x_api_key,
        x_tenant=x_tenant,
    )


async def test_oauth_valido_autentica(sessao_f13, contexto_f13: ContextoF13) -> None:
    cliente = await criar_api_client_teste(
        sessao_f13, tenant_id=contexto_f13.tenant_id, escopos=["webhooks:ler"]
    )
    token = await emitir_oauth_token_teste(
        sessao_f13, tenant_id=contexto_f13.tenant_id, cliente=cliente
    )
    await sessao_f13.commit()

    resultado = await _autenticar(
        "webhooks:ler",
        authorization=f"Bearer {token}",
        x_tenant=contexto_f13.tenant_slug,
    )

    assert resultado.tenant_id == contexto_f13.tenant_id
    assert resultado.api_client_id == cliente.id
    assert resultado.ambiente == cliente.ambiente
    assert "webhooks:ler" in resultado.escopos
    assert resultado.rate_limit_por_minuto == cliente.rate_limit_por_minuto


async def test_api_key_valida_autentica(sessao_f13, contexto_f13: ContextoF13) -> None:
    cliente = await criar_api_client_teste(
        sessao_f13, tenant_id=contexto_f13.tenant_id, escopos=["integracoes:ler"]
    )
    chave = await criar_api_key_teste(sessao_f13, tenant_id=contexto_f13.tenant_id, cliente=cliente)
    await sessao_f13.commit()

    resultado = await _autenticar(
        "integracoes:ler", x_api_key=chave, x_tenant=contexto_f13.tenant_slug
    )

    assert resultado.api_client_id == cliente.id
    assert "integracoes:ler" in resultado.escopos


async def test_sem_credencial_responde_auth_002(contexto_f13: ContextoF13) -> None:
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await _autenticar("webhooks:ler", x_tenant=contexto_f13.tenant_slug)
    assert excinfo.value.codigo == "PONTO-AUTH-002"


async def test_escopo_insuficiente_responde_perm_003(sessao_f13, contexto_f13: ContextoF13) -> None:
    cliente = await criar_api_client_teste(
        sessao_f13, tenant_id=contexto_f13.tenant_id, escopos=["webhooks:ler"]
    )
    token = await emitir_oauth_token_teste(
        sessao_f13, tenant_id=contexto_f13.tenant_id, cliente=cliente, escopos=["webhooks:ler"]
    )
    await sessao_f13.commit()

    with pytest.raises(ErroDeAplicacao) as excinfo:
        await _autenticar(
            "webhooks:escrever",
            authorization=f"Bearer {token}",
            x_tenant=contexto_f13.tenant_slug,
        )
    assert excinfo.value.codigo == "PONTO-PERM-003"


async def test_oauth_expirado_responde_auth_012(sessao_f13, contexto_f13: ContextoF13) -> None:
    cliente = await criar_api_client_teste(sessao_f13, tenant_id=contexto_f13.tenant_id)
    token = await emitir_oauth_token_teste(
        sessao_f13,
        tenant_id=contexto_f13.tenant_id,
        cliente=cliente,
        expira_em=dt.datetime.now(dt.UTC) - dt.timedelta(minutes=1),
    )
    await sessao_f13.commit()

    with pytest.raises(ErroDeAplicacao) as excinfo:
        await _autenticar(
            "webhooks:ler", authorization=f"Bearer {token}", x_tenant=contexto_f13.tenant_slug
        )
    assert excinfo.value.codigo == "PONTO-AUTH-012"


async def test_oauth_revogado_responde_auth_012(sessao_f13, contexto_f13: ContextoF13) -> None:
    cliente = await criar_api_client_teste(sessao_f13, tenant_id=contexto_f13.tenant_id)
    token = await emitir_oauth_token_teste(
        sessao_f13,
        tenant_id=contexto_f13.tenant_id,
        cliente=cliente,
        revogado_em=dt.datetime.now(dt.UTC),
    )
    await sessao_f13.commit()

    with pytest.raises(ErroDeAplicacao) as excinfo:
        await _autenticar(
            "webhooks:ler", authorization=f"Bearer {token}", x_tenant=contexto_f13.tenant_slug
        )
    assert excinfo.value.codigo == "PONTO-AUTH-012"


async def test_oauth_token_de_outro_cliente_nunca_confere(
    sessao_f13, contexto_f13: ContextoF13
) -> None:
    """Um token que simplesmente não existe (string aleatória) confere o
    mesmo código de token inválido -- nunca revela se "quase" bateu."""
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await _autenticar(
            "webhooks:ler",
            authorization="Bearer token-que-nunca-foi-emitido",
            x_tenant=contexto_f13.tenant_slug,
        )
    assert excinfo.value.codigo == "PONTO-AUTH-012"


async def test_api_key_expirada_responde_auth_013(sessao_f13, contexto_f13: ContextoF13) -> None:
    cliente = await criar_api_client_teste(sessao_f13, tenant_id=contexto_f13.tenant_id)
    chave = await criar_api_key_teste(
        sessao_f13,
        tenant_id=contexto_f13.tenant_id,
        cliente=cliente,
        expira_em=dt.datetime.now(dt.UTC) - dt.timedelta(minutes=1),
    )
    await sessao_f13.commit()

    with pytest.raises(ErroDeAplicacao) as excinfo:
        await _autenticar("webhooks:ler", x_api_key=chave, x_tenant=contexto_f13.tenant_slug)
    assert excinfo.value.codigo == "PONTO-AUTH-013"


async def test_api_key_revogada_responde_auth_013(sessao_f13, contexto_f13: ContextoF13) -> None:
    cliente = await criar_api_client_teste(sessao_f13, tenant_id=contexto_f13.tenant_id)
    chave = await criar_api_key_teste(
        sessao_f13,
        tenant_id=contexto_f13.tenant_id,
        cliente=cliente,
        revogada_em=dt.datetime.now(dt.UTC),
    )
    await sessao_f13.commit()

    with pytest.raises(ErroDeAplicacao) as excinfo:
        await _autenticar("webhooks:ler", x_api_key=chave, x_tenant=contexto_f13.tenant_slug)
    assert excinfo.value.codigo == "PONTO-AUTH-013"


async def test_cliente_suspenso_invalida_token_ja_emitido(
    sessao_f13, contexto_f13: ContextoF13
) -> None:
    """O token continua dentro do prazo, mas o cliente foi suspenso depois de
    emiti-lo -- `exigir_escopo` revalida `api_clients.status`, não só o
    token (ver docstring do módulo)."""
    cliente = await criar_api_client_teste(sessao_f13, tenant_id=contexto_f13.tenant_id)
    token = await emitir_oauth_token_teste(
        sessao_f13, tenant_id=contexto_f13.tenant_id, cliente=cliente
    )
    cliente.status = "suspenso"
    await sessao_f13.commit()

    with pytest.raises(ErroDeAplicacao) as excinfo:
        await _autenticar(
            "webhooks:ler", authorization=f"Bearer {token}", x_tenant=contexto_f13.tenant_slug
        )
    assert excinfo.value.codigo == "PONTO-AUTH-012"


async def test_origem_fora_da_lista_responde_perm_006(
    sessao_f13, contexto_f13: ContextoF13
) -> None:
    cliente = await criar_api_client_teste(
        sessao_f13,
        tenant_id=contexto_f13.tenant_id,
        ips_permitidos=["198.51.100.0/24"],
    )
    token = await emitir_oauth_token_teste(
        sessao_f13, tenant_id=contexto_f13.tenant_id, cliente=cliente
    )
    await sessao_f13.commit()

    with pytest.raises(ErroDeAplicacao) as excinfo:
        await _autenticar(
            "webhooks:ler",
            authorization=f"Bearer {token}",
            x_tenant=contexto_f13.tenant_slug,
            ip="203.0.113.10",
        )
    assert excinfo.value.codigo == "PONTO-PERM-006"


async def test_origem_dentro_da_lista_autentica(sessao_f13, contexto_f13: ContextoF13) -> None:
    cliente = await criar_api_client_teste(
        sessao_f13,
        tenant_id=contexto_f13.tenant_id,
        ips_permitidos=["203.0.113.0/24"],
    )
    token = await emitir_oauth_token_teste(
        sessao_f13, tenant_id=contexto_f13.tenant_id, cliente=cliente
    )
    await sessao_f13.commit()

    resultado = await _autenticar(
        "webhooks:ler",
        authorization=f"Bearer {token}",
        x_tenant=contexto_f13.tenant_slug,
        ip="203.0.113.10",
    )
    assert resultado.api_client_id == cliente.id


async def test_sem_x_tenant_responde_val_011(sessao_f13, contexto_f13: ContextoF13) -> None:
    cliente = await criar_api_client_teste(sessao_f13, tenant_id=contexto_f13.tenant_id)
    token = await emitir_oauth_token_teste(
        sessao_f13, tenant_id=contexto_f13.tenant_id, cliente=cliente
    )
    await sessao_f13.commit()

    with pytest.raises(ErroDeAplicacao) as excinfo:
        await _autenticar("webhooks:ler", authorization=f"Bearer {token}", x_tenant=None)
    assert excinfo.value.codigo == "PONTO-VAL-011"
