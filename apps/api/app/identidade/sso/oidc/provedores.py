"""Registro dos dois provedores OIDC suportados (T20/T21, A9).

**Escolha de biblioteca (T20).** O PCF sugere `authlib` como opcao pronta para
OIDC compativel com `httpx`. Avaliada e descartada: este modulo so precisa de
tres operacoes -- montar a URL de autorizacao, trocar `code` por token
(`POST` simples) e validar um `id_token` JWT contra um JWKS -- e o projeto ja
depende de `httpx` (chamadas HTTP) e `pyjwt[crypto]` (assinatura RS256 do
access token proprio, `app.identidade.tokens.jwt`) para exatamente isso.
`pyjwt` decodifica e valida JWT (`jwt.decode(..., algorithms=["RS256"])`) e
`jwt.PyJWKSet.from_dict` interpreta um JWKS sem depender de rede na hora da
validacao (o JWKS e buscado por `app.identidade.sso.oidc.protocolo` via
`httpx`, ver docstring do modulo). Escolher `httpx`+`pyjwt` em vez de
`authlib` evita uma dependencia nova inteira (licenca BSD-3, seria
compativel, mas o criterio decisivo foi footprint de imagem/superficie de
auditoria, nao licenca) para cobrir uma fatia pequena do que `authlib`
ofereceria.

Os dois provedores usam o app OIDC COMPARTILHADO da aplicacao inteira
(ADR-013): um client_id/client_secret por provedor, nunca por tenant. A
restricao por tenant e so a allowlist de dominio (google) ou tenant_id/issuer
(entra_id), lida de `tenant_configuracoes` por
`app.identidade.sso.oidc.configuracao`.

Entra ID usa o endpoint multi-tenant `organizations` (qualquer conta
corporativa/de estudo, nunca conta pessoal Microsoft) porque o app e
compartilhado por todos os tenants SEEG -- o `issuer` real de cada token
varia por diretorio (`https://login.microsoftonline.com/{tid}/v2.0`), por
isso a validacao de emissor é feita dinamicamente contra a propria claim
`tid` em `protocolo.py`, nao contra um valor fixo aqui.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Configuracao, obter_configuracao

#: Nomes de provedor aceitos por `GET /v1/sso/{provedor}/callback` (RFC-018).
#: `saml` participa de `iniciar` (T22, A10) mas nunca de `callback` OIDC.
PROVEDORES_OIDC: tuple[str, ...] = ("google", "entra_id")

_GOOGLE_AUTHORIZATION_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"  # noqa: S105 -- URL, nao segredo
_GOOGLE_JWKS_URI = "https://www.googleapis.com/oauth2/v3/certs"
_GOOGLE_ISSUER = "https://accounts.google.com"

_ENTRA_AUTHORIZATION_ENDPOINT = (
    "https://login.microsoftonline.com/organizations/oauth2/v2.0/authorize"
)
_ENTRA_TOKEN_ENDPOINT = "https://login.microsoftonline.com/organizations/oauth2/v2.0/token"  # noqa: S105 -- URL, nao segredo
_ENTRA_JWKS_URI = "https://login.microsoftonline.com/organizations/discovery/v2.0/keys"

ESCOPO_PADRAO = "openid email profile"


@dataclass(frozen=True, slots=True)
class ProvedorOidc:
    """Metadados fixos + credencial de aplicacao (ADR-013) de um provedor OIDC."""

    nome: str
    authorization_endpoint: str
    token_endpoint: str
    jwks_uri: str
    #: Emissor esperado no `id_token`. Vazio para entra_id: o emissor real
    #: varia por diretorio e e validado dinamicamente contra a claim `tid`
    #: (ver `protocolo.trocar_code_por_claims`).
    issuer: str
    client_id: str
    client_secret: str
    scope: str = ESCOPO_PADRAO


def obter_provedor(nome: str, *, config: Configuracao | None = None) -> ProvedorOidc:
    """Monta o `ProvedorOidc` de `nome` a partir da `Configuracao` do processo.

    Levanta `ValueError` para nome fora de `PROVEDORES_OIDC` -- erro de
    programacao do chamador (o path param ja e validado por enum no FastAPI
    antes de qualquer codigo deste modulo rodar), nunca uma condicao de
    negocio que vire resposta HTTP.
    """
    config = config or obter_configuracao()
    if nome == "google":
        return ProvedorOidc(
            nome="google",
            authorization_endpoint=_GOOGLE_AUTHORIZATION_ENDPOINT,
            token_endpoint=_GOOGLE_TOKEN_ENDPOINT,
            jwks_uri=_GOOGLE_JWKS_URI,
            issuer=_GOOGLE_ISSUER,
            client_id=config.sso_google_client_id,
            client_secret=config.sso_google_client_secret.get_secret_value(),
        )
    if nome == "entra_id":
        return ProvedorOidc(
            nome="entra_id",
            authorization_endpoint=_ENTRA_AUTHORIZATION_ENDPOINT,
            token_endpoint=_ENTRA_TOKEN_ENDPOINT,
            jwks_uri=_ENTRA_JWKS_URI,
            issuer="",
            client_id=config.sso_entra_client_id,
            client_secret=config.sso_entra_client_secret.get_secret_value(),
        )
    raise ValueError(f"provedor OIDC desconhecido: {nome!r}")
