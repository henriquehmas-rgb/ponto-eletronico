"""RelayState anti-CSRF/anti-replay do fluxo SAML, assinado (HS256) e com TTL curto.

Mesmo espirito de `app.identidade.sso.oidc.estado` (T20/A9): o SAMLRequest sai
de `GET /v1/sso/{provedor}/iniciar` (provedor=saml) e a unica coisa que
sobrevive a ida-e-volta pelo IdP e o proprio `RelayState`, que o IdP e
OBRIGADO a ecoar sem alteracao (perfil SAML 2.0 HTTP-Redirect/HTTP-POST). Este
modulo assina esse valor para que `POST /v1/sso/saml/acs` recupere
`tenant_id` com garantia de integridade, sem tabela nova nem estado de
servidor entre as duas chamadas.

Diferenca deliberada em relacao ao `state` OIDC: o RelayState tambem carrega o
`request_id` do `AuthnRequest` que `iniciar` gerou. Isso permite validar
`InResponseTo` da asserção de volta (`OneLogin_Saml2_Response.is_valid(...,
request_id=...)`) sem persistir o ID em lugar nenhum -- o proprio RelayState
assinado E o "banco" de um unico valor, de vida curta (5 minutos).
"""

from __future__ import annotations

import datetime as _dt
import secrets
import uuid
from dataclasses import dataclass

import jwt as pyjwt

from app.core.config import obter_configuracao
from app.core.erros import ErroDeAplicacao

ALGORITMO = "HS256"

#: Janela do fluxo inteiro (redirecionar, autenticar no IdP, voltar pelo ACS).
#: Mais curta que a do OIDC (10 min): o perfil HTTP-POST do SAML e tipicamente
#: mais rapido (sem tela de consentimento OAuth) e o Recipient/NotOnOrAfter da
#: propria asserção ja impoe um teto adicional, independente deste TTL.
VIDA_ESTADO_S = 5 * 60


@dataclass(frozen=True, slots=True)
class EstadoSaml:
    tenant_id: uuid.UUID
    request_id: str
    nonce: str


def _chave_secreta() -> bytes:
    valor = obter_configuracao().sso_saml_estado_chave.get_secret_value()
    if not valor:
        # Falha fechada: sem a chave configurada, nao ha como emitir nem
        # validar RelayState -- nunca aceita um valor nao assinado.
        raise ErroDeAplicacao(
            "PONTO-INT-001",
            contexto_log={"motivo": "SSO_SAML_ESTADO_CHAVE ausente ou vazia"},
        )
    return valor.encode("utf-8")


def gerar_estado(
    *, tenant_id: uuid.UUID, request_id: str, agora: _dt.datetime | None = None
) -> str:
    """Emite o RelayState assinado, embutindo o `request_id` do AuthnRequest
    para validacao de InResponseTo em `POST /v1/sso/saml/acs`."""
    agora = agora or _dt.datetime.now(_dt.UTC)
    claims = {
        "tenant_id": str(tenant_id),
        "request_id": request_id,
        "nonce": secrets.token_urlsafe(16),
        "iat": int(agora.timestamp()),
        "exp": int((agora + _dt.timedelta(seconds=VIDA_ESTADO_S)).timestamp()),
    }
    return pyjwt.encode(claims, _chave_secreta(), algorithm=ALGORITMO)


def validar_estado(relay_state: str) -> EstadoSaml:
    """`PONTO-AUTH-004` para RelayState ausente, expirado, adulterado ou malformado."""
    if not relay_state:
        raise ErroDeAplicacao("PONTO-AUTH-004", detalhe="RelayState ausente")
    try:
        claims = pyjwt.decode(relay_state, _chave_secreta(), algorithms=[ALGORITMO])
    except pyjwt.InvalidTokenError as exc:
        raise ErroDeAplicacao("PONTO-AUTH-004", detalhe="RelayState invalido ou expirado") from exc

    try:
        tenant_id = uuid.UUID(str(claims["tenant_id"]))
    except (KeyError, ValueError) as exc:
        raise ErroDeAplicacao("PONTO-AUTH-004", detalhe="RelayState malformado") from exc

    request_id = claims.get("request_id")
    if not request_id or not isinstance(request_id, str):
        raise ErroDeAplicacao("PONTO-AUTH-004", detalhe="RelayState sem request_id")

    nonce = claims.get("nonce")
    if not nonce or not isinstance(nonce, str):
        raise ErroDeAplicacao("PONTO-AUTH-004", detalhe="RelayState sem nonce")

    return EstadoSaml(tenant_id=tenant_id, request_id=request_id, nonce=nonce)
