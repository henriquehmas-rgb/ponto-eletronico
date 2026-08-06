"""Rotas da tag `sso` do contrato -- login federado (F13/A9, RFC-018/ADR-013).

`iniciarSso`/`callbackSso` (OIDC: Google Workspace, Microsoft Entra ID) sao
implementados aqui por A9. `acsSaml` (`POST /v1/sso/saml/acs`) e exclusivo de
A10 (T22) -- acrescenta a propria funcao a este mesmo arquivo, sem tocar nas
de A9 (PCF da fase, secao 5.2: "se A10 tambem precisar do mesmo arquivo,
dividem por funcao/rota dentro dele, nunca duas copias"). `iniciarSso` tem
provedor SAML no proprio enum de caminho (RFC-018: um unico `iniciar`
compartilhado pelos tres provedores) -- o ramo `saml` delega, por import
tardio, a `app.identidade.sso.saml` (pacote exclusivo de A10); se esse pacote
ainda nao existir quando este modulo for importado, cai em `NaoImplementado`
(501) em vez de quebrar a aplicacao inteira -- documentado no proprio corpo
da funcao.

Regra de negocio mora em `app.identidade.sso.oidc.*`; este modulo so traduz
HTTP <-> essas pecas, mesmo principio que `app/routers/auth.py` (F1)
documenta para a tag `auth`.

**Resolucao de tenant.** `iniciarSso` e alcancado por link/navegacao direta
do navegador (nunca por `fetch` com cabecalho customizado -- e um
redirecionamento de pagina inteira), entao usa a mesma precedencia de
`X-Tenant` > `?tenant=` > subdominio que `autenticar` ja usa para o corpo,
adaptada ao formato de link. `callbackSso` NUNCA usa `X-Tenant`/subdominio: o
`redirect_uri` registrado no IdP e um endpoint UNICO e compartilhado por
todos os tenants (ADR-013, app OIDC de aplicacao), sem subdominio proprio, e
o navegador nao preserva cabecalhos customizados atraves do redirecionamento
externo -- o tenant e recuperado do `state` assinado que `iniciarSso` emitiu
(`app.identidade.sso.oidc.estado`).
"""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, Header, Path, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.comum.ip_confiavel import ip_confiavel_do_cliente
from app.core.config import obter_configuracao
from app.core.erros import RESPOSTAS_PADRAO, ErroDeAplicacao, NaoImplementado
from app.core.seguranca import Sujeito, exigir_permissao, tenant_id_ou_erro
from app.db.sessao import SessaoDb
from app.identidade.autenticacao.tenant import (
    sessao_com_tenant_id,
    sessao_com_tenant_resolvido,
)
from app.identidade.sso.oidc import configuracao as config_sso
from app.identidade.sso.oidc import estado as estado_mod
from app.identidade.sso.oidc import protocolo, resolucao
from app.identidade.sso.oidc.provedores import obter_provedor
from app.schemas import contrato

roteador = APIRouter(tags=["sso"])

TIPO_TOKEN_BEARER = "Bearer"  # noqa: S105 -- constante de protocolo, nao segredo.

ProvedorIniciar = Literal["google", "entra_id", "saml"]
ProvedorCallback = Literal["google", "entra_id"]


def _ip_do_cliente(request: Request) -> str | None:
    """F14/A2, retrofit: agora delega a `app.comum.ip_confiavel` (honra
    `X-Forwarded-For`/`X-Real-IP` só quando a conexão vem do proxy reverso
    de produção -- ver docstring daquele módulo). Achado nomeado no PCF
    (`docs/backlog.md` 2026-08-03): o login federado alcança este código via
    `fetch` servidor-a-servidor de `apps/web`, então sem isto o IP gravado
    era sempre o do proxy, nunca o do usuário final."""
    return ip_confiavel_do_cliente(request)


def _user_agent(request: Request) -> str | None:
    return request.headers.get("user-agent")


def _identificador_tenant(x_tenant: str | None, tenant_query: str | None) -> str:
    """Precedencia: cabecalho > query > tenant ja resolvido pelo middleware
    (subdominio). Mesma logica de `app/routers/auth.py:_identificador_tenant`,
    adaptada: `iniciarSso` e alcancado por navegacao pura, entao `?tenant=`
    faz o papel que o campo do corpo faz em `autenticar`."""
    from app.core import contexto

    return (x_tenant or tenant_query or contexto.tenant_atual() or "").strip()


def _redirect_uri(provedor: str) -> str:
    """`redirect_uri` registrado no console do provedor (Google/Entra):
    aponta para uma pagina do SPA, nunca para esta API diretamente.

    O IdP so sabe navegar o browser inteiro ate essa URL (nao ha como um
    `fetch` seguir um redirecionamento entre origens) -- por isso a pagina
    (`apps/web/src/app/sso/callback/[provedor]/page.tsx`) recebe `code`/
    `state` na propria query string e so ENTAO chama `callbackSso` por
    `fetch`, exatamente como a descricao de `callbackSso` no contrato ja
    documentava ("Chamado via fetch pela pagina que recebe o
    redirecionamento do IdP, nunca por navegacao de documento completa").
    Apontar isto para `api_base_url` (como o codigo fazia antes) faz o
    navegador aterrissar direto no JSON desta API, sem nenhuma sessao de
    navegador ser estabelecida -- a mesma classe de lacuna que SAML evita
    tendo seu proprio redirecionamento final (`saml/fluxo.py:
    url_conclusao_spa`)."""
    base = obter_configuracao().web_base_url.rstrip("/")
    return f"{base}/sso/callback/{provedor}"


def _para_schema_usuario(usuario: object) -> contrato.Usuario:
    """Mesma receita de `app/routers/admin.py:_para_schema` e
    `app/routers/auth.py:_para_schema` (duplicada de proposito, ver nota de
    `_ip_do_cliente` acima): le, para cada campo do schema, o atributo
    homonimo do objeto ORM."""
    dados = {nome: getattr(usuario, nome, None) for nome in contrato.Usuario.model_fields}
    return contrato.Usuario.model_validate(dados)


def _resposta_login(resultado: resolucao.ResultadoLoginSso) -> contrato.LoginResposta:
    return contrato.LoginResposta.model_validate(
        {
            "mfa_requerido": False,
            "access_token": resultado.access_token,
            "refresh_token": resultado.refresh_token,
            "token_type": TIPO_TOKEN_BEARER,
            "expires_in": resultado.expires_in,
            "sessao_id": resultado.sessao_id,
            "usuario": _para_schema_usuario(resultado.usuario),
        }
    )


@roteador.get(
    "/v1/sso/{provedor}/iniciar",
    status_code=302,
    operation_id="iniciarSso",
    summary="Iniciar login federado",
    responses=RESPOSTAS_PADRAO,
)
async def iniciar_sso(
    provedor: Annotated[ProvedorIniciar, Path(description="Identity Provider alvo.")],
    request: Request,
    tenant: Annotated[
        str | None,
        Query(description="Slug ou UUID do tenant alvo, para acesso por link direto."),
    ] = None,
    vinculo_hash: Annotated[
        str | None,
        Query(
            alias="vinculoHash",
            description="RFC-019: hash SHA-256 (hex) do vinculo de navegador anti-login-CSRF.",
        ),
    ] = None,
    x_tenant: Annotated[str | None, Header(alias="X-Tenant")] = None,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> RedirectResponse:
    """Iniciar login federado."""
    identificador = _identificador_tenant(x_tenant, tenant)
    async with sessao_com_tenant_resolvido(identificador) as (sessao_db, tenant_resolvido):
        if provedor == "saml":
            return await _iniciar_saml(sessao_db, tenant_id=tenant_resolvido.id, request=request)

        if not vinculo_hash:
            # RFC-019: sem vinculo de navegador, o `state` fica vulneravel a
            # login-CSRF (qualquer navegador que apresente um `state`/`code`
            # validos completa o login, nao so o que iniciou o fluxo).
            raise ErroDeAplicacao("PONTO-VAL-001", detalhe="vinculoHash")

        await resolucao.verificar_provedor_habilitado(
            sessao_db, tenant_id=tenant_resolvido.id, provedor=provedor
        )
        state, nonce = estado_mod.gerar_estado(
            tenant_id=tenant_resolvido.id, provedor=provedor, vinculo_hash=vinculo_hash
        )

    config_provedor = obter_provedor(provedor)
    url = protocolo.montar_url_autorizacao(
        config_provedor,
        redirect_uri=_redirect_uri(provedor),
        state=state,
        nonce=nonce,
    )
    return RedirectResponse(url=url, status_code=302)


async def _iniciar_saml(
    sessao_db: AsyncSession, *, tenant_id: UUID, request: Request
) -> RedirectResponse:
    """Delega ao pacote exclusivo de A10 (T22): `app.identidade.sso.saml.fluxo.iniciar(
    sessao_db, *, tenant_id, request) -> RedirectResponse` (ou qualquer `Response`).

    Import por `importlib` (nunca `from ... import ...` estatico) de
    proposito: os dois pacotes evoluem em paralelo sem ordem de commit
    garantida (PCF da fase, secao 5.2), e um `import` estatico faria o mypy
    (que resolve o modulo real em disco) falhar sempre que A10 ainda nao
    tiver publicado `fluxo.iniciar`, mesmo quando o corpo deste modulo esta
    correto -- `importlib` mantem a checagem so em tempo de execucao.
    `NaoImplementado` (501, `PONTO-INT-005`) e a resposta enquanto o modulo
    de A10 nao existir; nunca um 500 de import quebrado."""
    import importlib

    try:
        saml_fluxo = importlib.import_module("app.identidade.sso.saml.fluxo")
        iniciar_saml = saml_fluxo.iniciar
    except (ImportError, AttributeError) as exc:
        raise NaoImplementado("iniciarSso(saml)", fase="F13/A10") from exc
    resultado: RedirectResponse = await iniciar_saml(
        sessao_db, tenant_id=tenant_id, request=request
    )
    return resultado


@roteador.get(
    "/v1/sso/{provedor}/callback",
    status_code=200,
    operation_id="callbackSso",
    summary="Concluir login federado (OIDC)",
    responses=RESPOSTAS_PADRAO,
)
async def callback_sso(
    provedor: Annotated[
        ProvedorCallback, Path(description="Identity Provider que concluiu a autenticacao.")
    ],
    code: Annotated[str, Query(description="Authorization code emitido pelo provedor.")],
    state: Annotated[
        str, Query(description="Valor opaco emitido por GET /v1/sso/{provedor}/iniciar.")
    ],
    request: Request,
    vinculo: Annotated[
        str | None,
        Query(description="RFC-019: valor bruto do vinculo de navegador anti-login-CSRF."),
    ] = None,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> contrato.LoginResposta:
    """Concluir login federado (OIDC)."""
    # `validar_estado` (RFC-019) ja rejeita `vinculo` ausente/divergente
    # quando o `state` carrega a claim -- e sempre carrega, `iniciar_sso`
    # exige `vinculoHash` para google/entra_id. Sem checagem duplicada aqui.
    estado = estado_mod.validar_estado(state, provedor_esperado=provedor, vinculo=vinculo)
    config_provedor = obter_provedor(provedor)

    async with httpx.AsyncClient(timeout=protocolo.TIMEOUT_S) as cliente_http:
        claims = await protocolo.trocar_code_por_claims(
            config_provedor,
            code=code,
            redirect_uri=_redirect_uri(provedor),
            nonce_esperado=estado.nonce,
            cliente_http=cliente_http,
        )

    async with sessao_com_tenant_id(estado.tenant_id) as sessao_db:
        resultado = await resolucao.resolver_e_emitir_sessao(
            sessao_db,
            tenant_id=estado.tenant_id,
            provedor=provedor,
            claims=claims,
            ip=_ip_do_cliente(request),
            user_agent=_user_agent(request),
        )
    return _resposta_login(resultado)


@roteador.get(
    "/v1/admin/sso/provedores",
    status_code=200,
    operation_id="obterConfiguracaoSso",
    summary="Obter configuracao de SSO do tenant",
    responses=RESPOSTAS_PADRAO,
)
async def obter_configuracao_sso(
    sessao: SessaoDb,
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("admin.configurar"))],
    x_tenant: Annotated[str | None, Header(alias="X-Tenant")] = None,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> contrato.ConfiguracaoSso:
    """Obter configuracao de SSO do tenant."""
    tenant_id = tenant_id_ou_erro(sujeito)
    dados = await config_sso.carregar_configuracao(sessao, tenant_id=tenant_id)
    return contrato.ConfiguracaoSso.model_validate(dados)


@roteador.put(
    "/v1/admin/sso/provedores",
    status_code=200,
    operation_id="atualizarConfiguracaoSso",
    summary="Atualizar configuracao de SSO do tenant",
    responses=RESPOSTAS_PADRAO,
)
async def atualizar_configuracao_sso(
    sessao: SessaoDb,
    corpo: contrato.ConfiguracaoSso,
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("admin.configurar"))],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    x_tenant: Annotated[str | None, Header(alias="X-Tenant")] = None,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> contrato.ConfiguracaoSso:
    """Atualizar configuracao de SSO do tenant."""
    tenant_id = tenant_id_ou_erro(sujeito)
    campos = corpo.model_dump(by_alias=False, exclude_unset=True)
    dados = await config_sso.atualizar_configuracao(
        sessao, tenant_id=tenant_id, campos=campos, usuario_id=sujeito.usuario_id
    )
    return contrato.ConfiguracaoSso.model_validate(dados)


# =============================================================================
# `POST /v1/sso/saml/acs` -- exclusivo de A10 (T22). Ver nota no cabecalho do
# modulo: acrescenta a propria funcao a este arquivo compartilhado com A9,
# sem tocar em nenhuma das funcoes acima.
# =============================================================================


@roteador.post(
    "/v1/sso/saml/acs",
    status_code=302,
    operation_id="concluirLoginSaml",
    summary="Concluir login federado (SAML)",
    responses=RESPOSTAS_PADRAO,
)
async def concluir_login_saml(request: Request) -> RedirectResponse:
    """Assertion Consumer Service (RFC-018/ADR-013, T22/A10).

    `content: application/x-www-form-urlencoded` (perfil HTTP-POST do SAML
    2.0) -- por isso le o corpo com `request.form()` em vez de um schema
    Pydantic, a mesma excecao a JSON que `openapi.yaml` documenta na propria
    operacao. Sem `Idempotency-Key`: quem chama este endpoint e o Identity
    Provider de terceiro, que nao envia cabecalhos proprios da SEEG.

    Valida o RelayState assinado (recupera `tenant_id`) ANTES de abrir a
    sessao de banco -- mesmo padrao que `callback_sso` (A9, OIDC) ja usa para
    o `state` OIDC. Responde 302 para `{webBaseUrl}/sso/concluir` com os
    tokens de sessao no fragmento da URL (nunca visivel a nenhum servidor).
    """
    from app.core.erros import ErroDeAplicacao
    from app.identidade.sso.saml import fluxo as saml_fluxo

    formulario = await request.form()
    saml_response_b64 = formulario.get("SAMLResponse")
    relay_state = formulario.get("RelayState")
    if not saml_response_b64 or not isinstance(saml_response_b64, str):
        raise ErroDeAplicacao("PONTO-VAL-001", detalhe="SAMLResponse ausente")
    if not relay_state or not isinstance(relay_state, str):
        raise ErroDeAplicacao("PONTO-AUTH-004", detalhe="RelayState ausente")

    estado = saml_fluxo.validar_relay_state(relay_state)
    async with sessao_com_tenant_id(estado.tenant_id) as sessao_db:
        resultado = await saml_fluxo.concluir_acs(
            sessao_db,
            estado=estado,
            saml_response_b64=saml_response_b64,
            request=request,
            ip=_ip_do_cliente(request),
            user_agent=_user_agent(request),
        )
    url = saml_fluxo.url_conclusao_spa(resultado)
    return RedirectResponse(url=url, status_code=302)
