"""OAuth 2.0 client credentials (`POST /v1/auth/token`) e chaves de API.

Fluxo suportado: `grant_type=client_credentials` apenas, como o contrato
declara (`TokenOAuthRequisicao.grantType` so aceita esse valor). As credenciais
chegam no corpo OU em `Authorization: Basic <client_id:client_secret em
base64>`; os dois formatos convivem porque e assim que a maioria dos clientes
OAuth de mercado (e o RFC 6749 secao 2.3.1) esperam.

Escopo efetivo e a INTERSECAO entre o que foi pedido e o que o cliente tem
concedido (`api_clients.escopos`); pedir um escopo fora do que o cliente tem
responde `PONTO-PERM-003`. Nenhum escopo pedido -> concede todos os do
cliente.
"""

from __future__ import annotations

import base64
import binascii
import datetime as _dt
import hashlib
import ipaddress
import secrets
import uuid
from dataclasses import dataclass

import sqlalchemy as sa
from ponto_contracts import ApiClient, ApiKey, OauthToken
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.erros import ErroDeAplicacao
from app.identidade.autenticacao.senha import gerar_hash, verificar_hash

#: Vida do access token de integracao. Mais longa que o access token humano
#: (15 min) porque o cliente de integracao normalmente nao tem refresh token
#: dedicado -- ele repete o client_credentials quando expira.
VIDA_TOKEN_OAUTH = _dt.timedelta(hours=1)

VIDA_API_KEY_PADRAO = None  # api_keys.expira_em e opcional; sem prazo por padrao.


@dataclass(frozen=True, slots=True)
class CredenciaisClient:
    client_id: str
    client_secret: str


def extrair_credenciais(
    *,
    client_id_corpo: str | None,
    client_secret_corpo: str | None,
    cabecalho_authorization: str | None,
) -> CredenciaisClient:
    """Corpo tem precedencia; cai para `Authorization: Basic` quando ausente."""
    if client_id_corpo and client_secret_corpo:
        return CredenciaisClient(client_id_corpo, client_secret_corpo)
    if cabecalho_authorization and cabecalho_authorization.lower().startswith("basic "):
        bruto = cabecalho_authorization.split(" ", 1)[1].strip()
        try:
            decodificado = base64.b64decode(bruto).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError) as exc:
            raise ErroDeAplicacao("PONTO-AUTH-012") from exc
        if ":" not in decodificado:
            raise ErroDeAplicacao("PONTO-AUTH-012")
        client_id, _, client_secret = decodificado.partition(":")
        return CredenciaisClient(client_id, client_secret)
    raise ErroDeAplicacao("PONTO-AUTH-012")


async def autenticar_client(
    sessao_db: AsyncSession, *, tenant_id: uuid.UUID, credenciais: CredenciaisClient
) -> ApiClient:
    cliente = (
        await sessao_db.execute(
            sa.select(ApiClient).where(
                ApiClient.tenant_id == tenant_id,
                ApiClient.client_id == credenciais.client_id,
                ApiClient.excluido_em.is_(None),
            )
        )
    ).scalar_one_or_none()
    if (
        cliente is None
        or cliente.status != "ativo"
        or not cliente.client_secret_hash
        or not verificar_hash(cliente.client_secret_hash, credenciais.client_secret)
    ):
        raise ErroDeAplicacao("PONTO-AUTH-012")
    return cliente


def verificar_origem_permitida(cliente: ApiClient, ip_origem: str | None) -> None:
    """`PONTO-PERM-006` quando o cliente restringe origem e o IP nao esta na lista."""
    permitidos = cliente.ips_permitidos or []
    if not permitidos:
        return
    if not ip_origem:
        raise ErroDeAplicacao("PONTO-PERM-006")
    try:
        endereco = ipaddress.ip_address(ip_origem)
    except ValueError as exc:
        raise ErroDeAplicacao("PONTO-PERM-006") from exc
    for faixa in permitidos:
        try:
            if endereco in ipaddress.ip_network(faixa, strict=False):
                return
        except ValueError:
            continue
    raise ErroDeAplicacao("PONTO-PERM-006")


def calcular_escopo_efetivo(escopo_pedido: str | None, escopos_concedidos: list[str]) -> list[str]:
    pedidos = escopo_pedido.split() if escopo_pedido else []
    if not pedidos:
        return list(escopos_concedidos)
    concedidos = set(escopos_concedidos)
    faltantes = [item for item in pedidos if item not in concedidos]
    if faltantes:
        raise ErroDeAplicacao("PONTO-PERM-003", detalhe=" ".join(faltantes))
    # Preserva a ordem pedida, sem duplicar.
    vistos: set[str] = set()
    efetivos = []
    for item in pedidos:
        if item not in vistos:
            efetivos.append(item)
            vistos.add(item)
    return efetivos


async def emitir_token(
    sessao_db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    cliente: ApiClient,
    escopos: list[str],
    ip: str | None = None,
    agora: _dt.datetime | None = None,
) -> tuple[str, int]:
    agora = agora or _dt.datetime.now(_dt.UTC)
    bruto = secrets.token_urlsafe(48)
    registro = OauthToken(
        tenant_id=tenant_id,
        api_client_id=cliente.id,
        tipo="access",
        token_hash=hashlib.sha256(bruto.encode("utf-8")).hexdigest(),
        escopos=escopos,
        emitido_em=agora,
        expira_em=agora + VIDA_TOKEN_OAUTH,
        ip=ip,
    )
    sessao_db.add(registro)
    await sessao_db.flush()
    return bruto, int(VIDA_TOKEN_OAUTH.total_seconds())


def gerar_client_secret() -> tuple[str, str]:
    """Devolve `(segredo_em_claro, hash)`. O segredo em claro nunca e persistido."""
    segredo = secrets.token_urlsafe(32)
    return segredo, gerar_hash(segredo)


def gerar_api_key(*, prefixo_ambiente: str = "prd") -> tuple[str, str, str]:
    """Devolve `(chave_em_claro, prefixo_exibivel, hash_sha256)`.

    A chave de API usa SHA-256 (nao Argon2id) porque `api_keys.hash` e
    `dom_sha256` no contrato -- e uma comparacao de posse, nao uma senha
    memorizada por humano, e o volume de verificacao por requisicao pede um
    hash rapido, nao lento.
    """
    bruto = secrets.token_urlsafe(32)
    prefixo = f"pk_{prefixo_ambiente}_{bruto[:8]}"
    hash_ = hashlib.sha256(bruto.encode("utf-8")).hexdigest()
    return bruto, prefixo, hash_


async def autenticar_api_key(
    sessao_db: AsyncSession, *, tenant_id: uuid.UUID, chave_bruta: str
) -> ApiKey:
    """Verifica uma `X-API-Key`. `PONTO-AUTH-013` quando invalida/expirada/revogada.

    Exportada para uso futuro por `app/core/seguranca.py` (T8, agente A3): esta
    fase entrega a primitiva de verificacao; a fiacao com `obter_sujeito` real
    e RBAC e da F1/A3.
    """
    hash_ = hashlib.sha256(chave_bruta.encode("utf-8")).hexdigest()
    chave = (
        await sessao_db.execute(
            sa.select(ApiKey).where(ApiKey.tenant_id == tenant_id, ApiKey.hash == hash_)
        )
    ).scalar_one_or_none()
    agora = _dt.datetime.now(_dt.UTC)
    if (
        chave is None
        or chave.revogada_em is not None
        or (chave.expira_em is not None and chave.expira_em <= agora)
    ):
        raise ErroDeAplicacao("PONTO-AUTH-013")
    return chave
