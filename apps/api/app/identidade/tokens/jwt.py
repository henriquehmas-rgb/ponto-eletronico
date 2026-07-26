"""Access token JWT RS256, de vida curta.

Claims emitidas:

* `sub`    -- `usuarios.id`.
* `tenant` -- `tenants.id`. Comparado pela F2/A2 contra o tenant resolvido da
  requisicao (`X-Tenant`/subdominio); divergencia responde `PONTO-TEN-002`.
* `email`  -- copia do e-mail no momento da emissao (evita outra consulta so
  para exibir o usuario).
* `sid`    -- `sessoes.id`. E o que liga o access token a sessao revogavel.
* `jti`    -- identificador unico do token, para correlacao em log/auditoria.
* `iat`, `exp`, `iss`, `aud` -- campos padrao do RFC 7519.

A assinatura e RS256 (par assimetrico): o serviço que EMITE guarda a chave
privada; qualquer serviço que precise apenas VALIDAR (worker, device-gw,
facial-svc) so precisa da chave publica, nunca da privada.
"""

from __future__ import annotations

import datetime as _dt
import uuid
from typing import Any, Final, TypedDict

import jwt as pyjwt

from app.core.erros import ErroDeAplicacao
from app.identidade.tokens.chaves import chave_privada, chave_publica

ALGORITMO: Final[str] = "RS256"
EMISSOR: Final[str] = "ponto-eletronico"
AUDIENCIA: Final[str] = "ponto-api"
VIDA_ACCESS_TOKEN_S: Final[int] = 15 * 60


class ClaimsAccessToken(TypedDict):
    sub: str
    tenant: str
    email: str
    sid: str
    jti: str
    iat: int
    exp: int
    iss: str
    aud: str


def emitir_access_token(
    *,
    usuario_id: uuid.UUID,
    tenant_id: uuid.UUID,
    email: str,
    sessao_id: uuid.UUID,
    agora: _dt.datetime | None = None,
    vida_s: int = VIDA_ACCESS_TOKEN_S,
) -> tuple[str, int]:
    """Emite o access token. Devolve `(token, expires_in_segundos)`."""
    agora = agora or _dt.datetime.now(_dt.UTC)
    expira = agora + _dt.timedelta(seconds=vida_s)
    claims: ClaimsAccessToken = {
        "sub": str(usuario_id),
        "tenant": str(tenant_id),
        "email": email,
        "sid": str(sessao_id),
        "jti": str(uuid.uuid4()),
        "iat": int(agora.timestamp()),
        "exp": int(expira.timestamp()),
        "iss": EMISSOR,
        "aud": AUDIENCIA,
    }
    token = pyjwt.encode(dict(claims), chave_privada(), algorithm=ALGORITMO)
    return token, vida_s


def decodificar_access_token(token: str) -> ClaimsAccessToken:
    """Valida assinatura, emissor, audiencia e validade. Nunca devolve claims de token invalido.

    `PONTO-AUTH-003` para expirado (o cliente so precisa renovar);
    `PONTO-AUTH-004` para qualquer outra falha de validacao (assinatura,
    emissor, audiencia, formato) -- inclui token de outro ambiente.
    """
    try:
        claims: dict[str, Any] = pyjwt.decode(
            token,
            chave_publica(),
            algorithms=[ALGORITMO],
            audience=AUDIENCIA,
            issuer=EMISSOR,
        )
    except pyjwt.ExpiredSignatureError as exc:
        raise ErroDeAplicacao("PONTO-AUTH-003") from exc
    except pyjwt.InvalidTokenError as exc:
        raise ErroDeAplicacao("PONTO-AUTH-004") from exc
    campos_obrigatorios = ("sub", "tenant", "email", "sid", "jti", "iat", "exp", "iss", "aud")
    if any(campo not in claims for campo in campos_obrigatorios):
        raise ErroDeAplicacao("PONTO-AUTH-004")
    return claims  # type: ignore[return-value]


AUDIENCIA_OPERACAO: Final[str] = "ponto-operacao"
VIDA_TOKEN_OPERACAO_S: Final[int] = 10 * 60


def emitir_token_operacao(
    *,
    usuario_id: uuid.UUID,
    tenant_id: uuid.UUID,
    sessao_id: uuid.UUID,
    agora: _dt.datetime | None = None,
) -> tuple[str, _dt.datetime]:
    """Token curto de `POST /v1/auth/reautenticar`, consumido por outras fases
    (F8, registro de ponto pela web) para provar reautenticacao recente.

    Mesma chave RS256 do access token, `aud` distinto (`ponto-operacao`) para
    que um access token comum nunca seja aceito no lugar deste.
    """
    agora = agora or _dt.datetime.now(_dt.UTC)
    valido_ate = agora + _dt.timedelta(seconds=VIDA_TOKEN_OPERACAO_S)
    claims = {
        "sub": str(usuario_id),
        "tenant": str(tenant_id),
        "sid": str(sessao_id),
        "jti": str(uuid.uuid4()),
        "iat": int(agora.timestamp()),
        "exp": int(valido_ate.timestamp()),
        "iss": EMISSOR,
        "aud": AUDIENCIA_OPERACAO,
    }
    token = pyjwt.encode(claims, chave_privada(), algorithm=ALGORITMO)
    return token, valido_ate
