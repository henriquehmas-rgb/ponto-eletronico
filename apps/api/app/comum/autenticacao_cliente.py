"""Autenticação de CLIENTE de integração (OAuth 2.0 client credentials ou
`X-API-Key`) para as rotas novas desta fase (F13/A1, T1 — T1-first da fase
inteira: os outros nove agentes desta fase dependem da assinatura abaixo).

**Por que este módulo existe e não reabre `app/core/seguranca.py`.** O PCF da
fase (§2.3) documenta o achado: nenhuma rota do sistema hoje reconhece um
`Bearer <token OAuth>` nem um `X-API-Key` — `app/core/seguranca.py::
obter_sujeito` só decodifica JWT de sessão HUMANA (via `app.core.contexto`,
populado por `AutenticacaoMiddleware`/F1). Os dois arquivos que resolveriam
isso (`app/core/seguranca.py`, `app/identidade/tokens/middleware.py`) têm
trava explícita de ownership (F1/A3) e não são reabertos por esta fase. A
solução é esta dependência FastAPI **autocontida**: não importa `Sujeito`,
`obter_sujeito` nem qualquer `ContextVar` de `app.core.contexto` — lê
`Authorization`/`X-API-Key`/`X-Tenant` diretamente da `Request` e abre a
própria sessão de banco (mesmo padrão de isolamento que
`app.identidade.tokens.dependencias.obter_sujeito_autenticado` já usa para as
rotas de sessão humana: uma sessão própria, fora do `SessaoDb` do handler).

**Por que `X-Tenant` é obrigatório aqui (decisão registrada).** O contrato
declara `X-Tenant` como opcional no schema (`CabecalhoTenant`) porque acesso
por subdomínio dispensa o cabeçalho — mas a própria descrição do parâmetro diz
que ele é *"obrigatório quando o host não identifica o tenant (chamadas a
api.ponto.<domínio> por cliente de integração)"*, exatamente o caso de todo
cliente OAuth/API key. `TenantMiddleware` (F1/A2) já resolve tenant por
subdomínio e publica em `contexto.tenant_atual()`/`request.state.tenant`, mas
esta dependência delibera NÃO usar esse valor (seria depender de estado
publicado por um middleware de outra fase por um caminho indireto do mesmo
`ContextVar` que o T1 pede para evitar) — em vez disso resolve o tenant de
novo, a partir do cabeçalho, com
`app.identidade.autenticacao.tenant.resolver_tenant_para_autenticacao`
(reaproveitada por leitura, nunca editada — mesmo padrão que
`POST /v1/auth/token`, F1, já usa). Sem `X-Tenant`, a dependência responde
`PONTO-VAL-011`, o mesmo código que `emitirTokenOAuth` já usa para o mesmo
cabeçalho ausente.

**Ordem de tentativa.** `Authorization: Bearer <token>` presente → tenta OAuth;
inválido/expirado/revogado → `401 PONTO-AUTH-012` (mesmo código de
"credenciais de cliente OAuth inválidas" que `POST /v1/auth/token` já usa —
decisão do PCF T1: o cliente vê o mesmo código estivesse a rejeição na emissão
ou no uso do token). Sem `Authorization` (ou sem prefixo `Bearer`), cai para
`X-API-Key` → inválida/expirada/revogada → `401 PONTO-AUTH-013` (reaproveita
`oauth.autenticar_api_key`, que já levanta esse código). Nenhuma das duas
credenciais presentes → `401 PONTO-AUTH-002`. Escopo pedido fora do concedido
→ `403 PONTO-PERM-003`. Origem fora de `ips_permitidos` do cliente → `403
PONTO-PERM-006` (reaproveita `oauth.verificar_origem_permitida`).

**Cliente suspenso/revogado depois de o token ser emitido.** `api_clients.
status` é revalidado aqui (não só na emissão): um cliente revogado não deve
continuar autenticando com um token/chave ainda dentro do prazo. Tratado com o
MESMO código de credencial inválida (`012`/`013` conforme o método) — decisão
documentada no relatório da fase, não no contrato (nenhum código novo).
"""

from __future__ import annotations

import datetime as _dt
import hashlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

import sqlalchemy as sa
from fastapi import Header, Request
from ponto_contracts import ApiClient, ApiKey, OauthToken
from sqlalchemy.ext.asyncio import AsyncSession

from app.comum.ip_confiavel import ip_confiavel_do_cliente
from app.core.erros import ErroDeAplicacao
from app.identidade.autenticacao.tenant import sessao_com_tenant_resolvido
from app.identidade.tokens import oauth as oauth_mod

__all__ = ["ClienteAutenticado", "exigir_escopo"]


@dataclass(frozen=True, slots=True)
class ClienteAutenticado:
    """Identidade de um cliente de integração autenticado (OAuth ou API key).

    Deliberadamente NÃO é o `Sujeito` de `app/core/seguranca.py`: é um tipo
    próprio desta fase, sem RBAC hierárquico nem permissões humanas — só o
    necessário para autorizar por escopo OAuth e aplicar limite de taxa.

    `rate_limit_por_minuto` é um campo aditivo além dos quatro que o PCF nomeia
    (`tenant_id`/`api_client_id`/`ambiente`/`escopos`): `exigir_escopo` já
    carrega a linha de `ApiClient` em mãos (para `verificar_origem_permitida`),
    então expor o limite aqui evita uma segunda consulta ao banco só para o
    limitador de taxa (T4) — `app.comum.limitador_taxa` fica Redis-only, sem
    sessão de banco própria.
    """

    tenant_id: UUID
    api_client_id: UUID
    ambiente: str
    escopos: tuple[str, ...]
    rate_limit_por_minuto: int


def _extrair_bearer(cabecalho_authorization: str | None) -> str | None:
    if not cabecalho_authorization or not cabecalho_authorization.lower().startswith("bearer "):
        return None
    token = cabecalho_authorization.split(" ", 1)[1].strip()
    return token or None


async def _carregar_api_client(
    sessao_db: AsyncSession,
    *,
    tenant_id: UUID,
    api_client_id: UUID,
) -> ApiClient | None:
    return (
        await sessao_db.execute(
            sa.select(ApiClient).where(
                ApiClient.tenant_id == tenant_id,
                ApiClient.id == api_client_id,
                ApiClient.excluido_em.is_(None),
            )
        )
    ).scalar_one_or_none()


async def _autenticar_via_oauth(
    sessao_db: AsyncSession,
    *,
    tenant_id: UUID,
    token_bruto: str,
) -> tuple[ApiClient, list[str]]:
    """`401 PONTO-AUTH-012` quando o token não confere, expirou, foi revogado,
    não é do tipo `access` ou o cliente dono já não está `ativo`."""
    hash_token = hashlib.sha256(token_bruto.encode("utf-8")).hexdigest()
    agora = _dt.datetime.now(_dt.UTC)
    token = (
        await sessao_db.execute(
            sa.select(OauthToken).where(
                OauthToken.tenant_id == tenant_id,
                OauthToken.token_hash == hash_token,
                OauthToken.tipo == "access",
            )
        )
    ).scalar_one_or_none()
    if token is None or token.revogado_em is not None or token.expira_em <= agora:
        raise ErroDeAplicacao("PONTO-AUTH-012")
    cliente = await _carregar_api_client(
        sessao_db, tenant_id=tenant_id, api_client_id=token.api_client_id
    )
    if cliente is None or cliente.status != "ativo":
        raise ErroDeAplicacao("PONTO-AUTH-012")
    return cliente, list(token.escopos or [])


async def _autenticar_via_api_key(
    sessao_db: AsyncSession,
    *,
    tenant_id: UUID,
    chave_bruta: str,
) -> tuple[ApiClient, list[str]]:
    """`401 PONTO-AUTH-013` quando a chave não confere, expirou, foi revogada
    ou o cliente dono já não está `ativo`."""
    chave: ApiKey = await oauth_mod.autenticar_api_key(
        sessao_db, tenant_id=tenant_id, chave_bruta=chave_bruta
    )
    cliente = await _carregar_api_client(
        sessao_db, tenant_id=tenant_id, api_client_id=chave.api_client_id
    )
    if cliente is None or cliente.status != "ativo":
        raise ErroDeAplicacao("PONTO-AUTH-013")
    # Uso registrado mesmo em caminho de sucesso: `ultimo_uso_em`/`ultimo_ip`
    # existem na tabela exatamente para isto (RFC-016 não os expõe em nenhuma
    # resposta, só a auditoria/painel os lê). Melhor esforço: uma falha aqui
    # nunca deve derrubar a autenticação em si.
    chave.ultimo_uso_em = _dt.datetime.now(_dt.UTC)
    return cliente, list(chave.escopos or [])


def exigir_escopo(escopo: str) -> Callable[..., Awaitable[ClienteAutenticado]]:
    """Fábrica de dependência FastAPI: exige um cliente OAuth/API key com
    `escopo` concedido. Uso: `Depends(exigir_escopo("webhooks:ler"))`.

    Guarde a instância devolvida (não chame `exigir_escopo(...)` de novo com o
    mesmo argumento) quando outra dependência da mesma rota também precisar do
    `ClienteAutenticado` resolvido — por exemplo `app.comum.limitador_taxa.
    exigir_limite_taxa(...)` — para o FastAPI reaproveitar o resultado (cache
    por dependência, chave é a identidade do *callable*) em vez de autenticar
    duas vezes na mesma requisição.
    """

    async def _dependencia(
        request: Request,
        authorization: Annotated[str | None, Header()] = None,
        x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
        x_tenant: Annotated[str | None, Header(alias="X-Tenant")] = None,
    ) -> ClienteAutenticado:
        token_bearer = _extrair_bearer(authorization)
        chave_api = (x_api_key or "").strip() or None
        if not token_bearer and not chave_api:
            raise ErroDeAplicacao("PONTO-AUTH-002")

        async with sessao_com_tenant_resolvido(x_tenant or "") as (sessao_db, tenant_resolvido):
            if token_bearer:
                cliente, escopos_concedidos = await _autenticar_via_oauth(
                    sessao_db, tenant_id=tenant_resolvido.id, token_bruto=token_bearer
                )
            elif chave_api:
                cliente, escopos_concedidos = await _autenticar_via_api_key(
                    sessao_db, tenant_id=tenant_resolvido.id, chave_bruta=chave_api
                )
            else:  # pragma: no cover - descartado pela checagem no topo da funcao
                raise ErroDeAplicacao("PONTO-AUTH-002")

            if escopo not in escopos_concedidos:
                raise ErroDeAplicacao("PONTO-PERM-003", detalhe=escopo)

            # F14/A2, retrofit: `app.comum.ip_confiavel` honra
            # `X-Forwarded-For`/`X-Real-IP` só quando a conexão vem do proxy
            # reverso de produção -- sem isto, um cliente de integração que
            # fala com a API por trás de `apps/web` (ou de qualquer proxy)
            # sempre veria `ips_permitidos` comparado contra o IP do proxy,
            # nunca o do chamador real, tornando a allowlist inútil nesse
            # caminho.
            ip_origem = ip_confiavel_do_cliente(request)
            oauth_mod.verificar_origem_permitida(cliente, ip_origem)

            return ClienteAutenticado(
                tenant_id=tenant_resolvido.id,
                api_client_id=cliente.id,
                ambiente=cliente.ambiente,
                escopos=tuple(escopos_concedidos),
                rate_limit_por_minuto=cliente.rate_limit_por_minuto,
            )

    return _dependencia
