"""`state` anti-CSRF/anti-replay do fluxo OIDC, assinado (HS256) e com TTL curto.

**Por que isto existe.** O app OIDC e COMPARTILHADO por todos os tenants
(ADR-013): o `redirect_uri` registrado no Google/Entra e um endpoint UNICO e
fixo (`{API_BASE_URL}/v1/sso/{provedor}/callback`), nao um por subdominio de
tenant. Isso significa que, quando o IdP devolve o navegador para o
`callback`, nao ha subdominio nem cabecalho `X-Tenant` para resolver o
tenant -- o unico dado que sobrevive a volta e o proprio `state` que
`iniciar` mandou. Este modulo assina esse valor (HMAC-SHA256 via `pyjwt`,
mesma biblioteca que `app.identidade.tokens.jwt` ja usa, algoritmo simetrico
porque so este processo emite e valida, ao contrario do access token RS256
que outros servicos tambem precisam verificar) para que o `callback` recupere
`tenant_id`/`provedor`/`nonce` com garantia de integridade, sem tabela nova
nem estado de servidor entre as duas chamadas.

O `nonce` embutido tambem vai no pedido de autorizacao ao IdP (parametro
`nonce=`) e volta dentro do `id_token`: `protocolo.trocar_code_por_claims`
confere os dois batem, o que impede um `id_token` de uma sessao de
autorizacao diferente ser reaproveitado aqui (replay).

**RFC-019 (achado de revisao adversarial no fechamento da F13): nada acima
impede login-CSRF.** Assinatura/expiracao/nonce provam que o `state` foi
emitido por este servidor e ainda e valido -- nunca provam que o NAVEGADOR
que o esta apresentando em `callback` e o MESMO que o recebeu de `iniciar`.
Um atacante que complete o proprio login, capture `code`+`state` validos
antes do proprio navegador os consumir, e induza a vitima a visitar o link
de callback com esses valores, faz a vitima autenticar como o ATACANTE.
`vinculo_hash` (embutido aqui, opcional só na assinatura da funcao por
compatibilidade de teste unitario -- o roteador em `app/routers/sso.py`
exige o parametro de verdade para google/entra_id) fecha esse gap: um
valor aleatorio gerado pelo navegador em `iniciar`, guardado em
`sessionStorage` (nunca em cookie -- `api_base_url`/`web_base_url` podem
ser hosts sem dominio-pai comum), cujo HASH vai no `state` e cujo valor
BRUTO só reaparece no `fetch` servidor-a-servidor de `callback` -- nunca na
querystring que um terceiro poderia ler/re-hospedar.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import hmac
import secrets
import uuid
from dataclasses import dataclass

import jwt as pyjwt

from app.core.config import obter_configuracao
from app.core.erros import ErroDeAplicacao

ALGORITMO = "HS256"

#: Janela do fluxo de autorizacao inteiro (redirecionar, autenticar no IdP,
#: voltar). Mesma ordem de grandeza da sessao pendente de MFA
#: (`app.identidade.tokens.sessao.VIDA_SESSAO_PENDENTE_MFA`, 10 minutos).
VIDA_ESTADO_S = 10 * 60


@dataclass(frozen=True, slots=True)
class EstadoSso:
    tenant_id: uuid.UUID
    provedor: str
    nonce: str


def _chave_secreta() -> bytes:
    valor = obter_configuracao().sso_estado_chave_secreta.get_secret_value()
    if not valor:
        # Falha fechada: sem a chave configurada, nao ha como emitir nem
        # validar `state` -- nunca aceita um valor nao assinado.
        raise ErroDeAplicacao(
            "PONTO-INT-001",
            contexto_log={"motivo": "SSO_ESTADO_CHAVE_SECRETA ausente ou vazia"},
        )
    return valor.encode("utf-8")


def gerar_estado(
    *,
    tenant_id: uuid.UUID,
    provedor: str,
    vinculo_hash: str | None = None,
    agora: _dt.datetime | None = None,
) -> tuple[str, str]:
    """Emite o `state` assinado. Devolve `(state, nonce)`.

    `nonce` tambem deve ir no pedido de autorizacao ao IdP -- ver docstring
    do modulo. `vinculo_hash` (RFC-019) e o hash SHA-256 (hex) do valor de
    vinculo de navegador gerado pelo chamador -- embutido como claim quando
    presente, para `validar_estado` conferir de volta.
    """
    agora = agora or _dt.datetime.now(_dt.UTC)
    nonce = secrets.token_urlsafe(16)
    claims = {
        "tenant_id": str(tenant_id),
        "provedor": provedor,
        "nonce": nonce,
        "iat": int(agora.timestamp()),
        "exp": int((agora + _dt.timedelta(seconds=VIDA_ESTADO_S)).timestamp()),
    }
    if vinculo_hash:
        claims["vinculo"] = vinculo_hash
    token = pyjwt.encode(claims, _chave_secreta(), algorithm=ALGORITMO)
    return token, nonce


def validar_estado(state: str, *, provedor_esperado: str, vinculo: str | None = None) -> EstadoSso:
    """`PONTO-AUTH-004` para `state` ausente, expirado, adulterado, de outro
    provedor, ou (RFC-019) sem vinculo de navegador correto -- os quatro
    casos respondem o MESMO codigo de proposito (nao vaza a um atacante qual
    checagem especifica falhou).

    `vinculo` (RFC-019): valor BRUTO recebido no `callback`. Se o `state`
    tiver uma claim `vinculo` (emitido com `vinculo_hash` em `gerar_estado`),
    o hash de `vinculo` PRECISA bater com ela -- ausencia ou divergencia
    rejeita. Comparacao em tempo constante (`hmac.compare_digest`) para nao
    abrir um oraculo de tempo na propria checagem anti-CSRF.
    """
    try:
        claims = pyjwt.decode(state, _chave_secreta(), algorithms=[ALGORITMO])
    except pyjwt.InvalidTokenError as exc:
        raise ErroDeAplicacao("PONTO-AUTH-004", detalhe="state invalido ou expirado") from exc

    if claims.get("provedor") != provedor_esperado:
        raise ErroDeAplicacao("PONTO-AUTH-004", detalhe="state emitido para outro provedor")

    try:
        tenant_id = uuid.UUID(str(claims["tenant_id"]))
    except (KeyError, ValueError) as exc:
        raise ErroDeAplicacao("PONTO-AUTH-004", detalhe="state malformado") from exc

    nonce = claims.get("nonce")
    if not nonce or not isinstance(nonce, str):
        raise ErroDeAplicacao("PONTO-AUTH-004", detalhe="state sem nonce")

    vinculo_esperado = claims.get("vinculo")
    if vinculo_esperado:
        vinculo_recebido_hash = (
            hashlib.sha256(vinculo.encode("utf-8")).hexdigest() if vinculo else ""
        )
        if not vinculo or not hmac.compare_digest(vinculo_recebido_hash, str(vinculo_esperado)):
            raise ErroDeAplicacao("PONTO-AUTH-004", detalhe="state sem vinculo de navegador valido")

    return EstadoSso(tenant_id=tenant_id, provedor=provedor_esperado, nonce=nonce)
