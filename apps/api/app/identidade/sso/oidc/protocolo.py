"""Fala HTTP com o provedor OIDC: autorizacao, troca de `code` por `id_token`,
validacao de assinatura/emissor/audiencia/nonce (T21, A9).

Toda chamada de rede passa por um `httpx.AsyncClient` recebido por parametro
(nunca criado implicitamente sem que o chamador possa injetar um) -- e o que
permite o teste exercitar o fluxo inteiro contra um IdP falso local
(`httpx.MockTransport`), sem rede real, como o ADR-013 exige explicitamente
("ate la, os testes automatizados usam credenciais de teste/mock do
provedor, nunca um app real").
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt as pyjwt

from app.core.erros import ErroDeAplicacao
from app.identidade.sso.oidc.provedores import ProvedorOidc

TIMEOUT_S = 10.0


def montar_url_autorizacao(
    provedor: ProvedorOidc,
    *,
    redirect_uri: str,
    state: str,
    nonce: str,
    login_hint: str | None = None,
) -> str:
    """URL completa para redirecionar o navegador ao IdP (`GET iniciar`)."""
    parametros: dict[str, str] = {
        "client_id": provedor.client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": provedor.scope,
        "state": state,
        "nonce": nonce,
    }
    if login_hint:
        parametros["login_hint"] = login_hint
    return f"{provedor.authorization_endpoint}?{urlencode(parametros)}"


@dataclass(frozen=True, slots=True)
class ClaimsIdToken:
    """Subconjunto das claims do `id_token` que `resolucao.py` precisa."""

    sub: str
    email: str | None
    email_verificado: bool
    #: Entra ID: id do diretorio (tenant) que emitiu o token -- NAO e o
    #: `tenant_id` do SEEG Ponto, e o que `verificar_identidade_permitida`
    #: compara contra a allowlist `sso.entra_id.tenant_id` do tenant.
    tid: str | None
    #: Google: dominio hospedado (Google Workspace), quando o IdP a inclui.
    hd: str | None


def _como_bool(valor: object) -> bool:
    """`email_verified` as vezes chega como string ("true"/"false"), nao bool."""
    if isinstance(valor, bool):
        return valor
    if isinstance(valor, str):
        return valor.strip().lower() == "true"
    return bool(valor)


async def _trocar_code_por_id_token(
    provedor: ProvedorOidc, *, code: str, redirect_uri: str, cliente_http: httpx.AsyncClient
) -> str:
    try:
        resposta = await cliente_http.post(
            provedor.token_endpoint,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": provedor.client_id,
                "client_secret": provedor.client_secret,
            },
            headers={"Accept": "application/json"},
            timeout=TIMEOUT_S,
        )
    except httpx.HTTPError as exc:
        raise ErroDeAplicacao(
            "PONTO-INT-003", contexto_log={"provedor": provedor.nome, "erro": str(exc)}
        ) from exc

    if resposta.status_code != 200:
        raise ErroDeAplicacao(
            "PONTO-AUTH-004",
            detalhe="troca de code por token recusada pelo provedor",
            contexto_log={
                "provedor": provedor.nome,
                "status": resposta.status_code,
                "corpo": resposta.text[:500],
            },
        )
    corpo: dict[str, Any] = resposta.json()
    id_token_bruto = corpo.get("id_token")
    if not id_token_bruto or not isinstance(id_token_bruto, str):
        raise ErroDeAplicacao("PONTO-AUTH-004", detalhe="resposta do provedor sem id_token")
    id_token: str = id_token_bruto
    return id_token


async def _buscar_jwks(
    provedor: ProvedorOidc, *, cliente_http: httpx.AsyncClient
) -> dict[str, Any]:
    try:
        resposta = await cliente_http.get(provedor.jwks_uri, timeout=TIMEOUT_S)
        resposta.raise_for_status()
    except httpx.HTTPError as exc:
        raise ErroDeAplicacao(
            "PONTO-INT-003", contexto_log={"provedor": provedor.nome, "erro": str(exc)}
        ) from exc
    corpo: dict[str, Any] = resposta.json()
    return corpo


def _selecionar_chave_de_assinatura(jwks: dict[str, Any], *, kid: str | None) -> Any:
    conjunto = pyjwt.PyJWKSet.from_dict(jwks)
    if kid is not None:
        for chave in conjunto.keys:
            if chave.key_id == kid:
                return chave.key
    if len(conjunto.keys) == 1:
        # JWKS com uma unica chave: aceita mesmo sem `kid` no cabecalho (raro,
        # mas alguns IdP de teste omitem `kid`).
        return conjunto.keys[0].key
    raise ErroDeAplicacao(
        "PONTO-AUTH-004", detalhe="chave de assinatura do id_token nao encontrada no JWKS"
    )


def _validar_claims(
    provedor: ProvedorOidc, *, id_token: str, chave: Any, nonce_esperado: str
) -> dict[str, Any]:
    try:
        claims: dict[str, Any] = pyjwt.decode(
            id_token,
            chave,
            algorithms=["RS256"],
            audience=provedor.client_id,
            issuer=provedor.issuer or None,
            options={"verify_iss": bool(provedor.issuer)},
        )
    except pyjwt.InvalidTokenError as exc:
        raise ErroDeAplicacao("PONTO-AUTH-004", detalhe="id_token invalido") from exc

    if provedor.nome == "entra_id":
        # Entra ID e multi-tenant no lado do IdP: o emissor real varia por
        # diretorio (`tid`). Confirma que o `iss` declarado bate com o
        # diretorio que a propria claim `tid` afirma -- o valor de `tid` em
        # si so e comparado contra a allowlist do TENANT SEEG depois, em
        # `resolucao.verificar_identidade_permitida`.
        tid = claims.get("tid")
        emissor_esperado = f"https://login.microsoftonline.com/{tid}/v2.0"
        if not tid or claims.get("iss") != emissor_esperado:
            raise ErroDeAplicacao(
                "PONTO-AUTH-004", detalhe="emissor do id_token nao confere com tid"
            )

    if claims.get("nonce") != nonce_esperado:
        raise ErroDeAplicacao("PONTO-AUTH-004", detalhe="nonce do id_token nao confere")

    if "sub" not in claims:
        raise ErroDeAplicacao("PONTO-AUTH-004", detalhe="id_token sem claim sub")

    return claims


async def trocar_code_por_claims(
    provedor: ProvedorOidc,
    *,
    code: str,
    redirect_uri: str,
    nonce_esperado: str,
    cliente_http: httpx.AsyncClient,
) -> ClaimsIdToken:
    """Troca `code` por tokens e valida o `id_token` de ponta a ponta.

    `PONTO-INT-003` quando o provedor esta inalcancavel (token endpoint ou
    JWKS); `PONTO-AUTH-004` para qualquer falha de validacao (assinatura,
    emissor, audiencia, nonce, campo obrigatorio ausente).
    """
    id_token = await _trocar_code_por_id_token(
        provedor, code=code, redirect_uri=redirect_uri, cliente_http=cliente_http
    )
    cabecalho = pyjwt.get_unverified_header(id_token)
    jwks = await _buscar_jwks(provedor, cliente_http=cliente_http)
    chave = _selecionar_chave_de_assinatura(jwks, kid=cabecalho.get("kid"))
    claims = _validar_claims(
        provedor, id_token=id_token, chave=chave, nonce_esperado=nonce_esperado
    )

    return ClaimsIdToken(
        sub=str(claims["sub"]),
        email=claims.get("email"),
        email_verificado=_como_bool(claims.get("email_verified", False)),
        tid=claims.get("tid"),
        hd=claims.get("hd"),
    )
