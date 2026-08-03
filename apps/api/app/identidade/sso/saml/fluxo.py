"""Fachada do fluxo SAML para `app.routers.sso` (T22, A10).

Reune `estado`, `protocolo` e `resolucao` num pequeno numero de funcoes com a
assinatura que o roteador compartilhado espera:

* `iniciar(sessao_db, *, tenant_id, request) -> RedirectResponse` -- e a
  funcao que `app.routers.sso._iniciar_saml` (A9) importa tardiamente no
  ramo `provedor == "saml"` de `GET /v1/sso/{provedor}/iniciar` (RFC-018: um
  unico `iniciar` compartilhado pelos tres provedores). Assinatura fixada por
  A9 no proprio router -- ver a docstring de `_iniciar_saml` la.
* `validar_relay_state`/`concluir_acs` -- usadas pela rota `concluirLoginSaml`
  (`POST /v1/sso/saml/acs`) que este mesmo agente acrescenta a
  `app.routers.sso` (arquivo compartilhado com A9, ver cabecalho daquele
  modulo: "acsSaml e exclusivo de A10... acrescenta a propria funcao a este
  mesmo arquivo, sem tocar nas de A9").
"""

from __future__ import annotations

import datetime as _dt
from typing import Any
from urllib.parse import urlencode, urlparse
from uuid import UUID

from fastapi import Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import obter_configuracao
from app.identidade.sso.saml import estado as estado_mod
from app.identidade.sso.saml import protocolo, resolucao
from app.identidade.sso.saml.config import ler_config_idp
from app.identidade.sso.saml.estado import EstadoSaml

TIPO_TOKEN_BEARER = "Bearer"  # noqa: S105 -- constante de protocolo, nao segredo.

_CAMINHO_ACS = "/v1/sso/saml/acs"
_CAMINHO_CONCLUSAO_SPA = "/sso/concluir"


def _acs_url() -> str:
    return obter_configuracao().api_base_url.rstrip("/") + _CAMINHO_ACS


def _sp_entity_id() -> str:
    # Sem metadata SP publicado num caminho separado: a propria URL do ACS
    # como entityId e a convencao mais comum quando isso acontece, e evita
    # inventar mais um endpoint (`/v1/sso/saml/metadata`) fora do que a
    # RFC-018 decidiu.
    return _acs_url()


async def iniciar(
    sessao_db: AsyncSession, *, tenant_id: UUID, request: Request
) -> RedirectResponse:
    """Assinatura fixada por `app.routers.sso._iniciar_saml` (A9)."""
    del request  # nao usado: nenhum dado da requisicao de `iniciar` entra no AuthnRequest.
    config = await ler_config_idp(sessao_db, tenant_id=tenant_id)
    saml_request, request_id = protocolo.montar_authn_request(
        config, acs_url=_acs_url(), sp_entity_id=_sp_entity_id()
    )
    relay_state = estado_mod.gerar_estado(tenant_id=tenant_id, request_id=request_id)
    url = protocolo.montar_url_redirecionamento(
        config, saml_request=saml_request, relay_state=relay_state
    )
    return RedirectResponse(url=url, status_code=302)


def validar_relay_state(relay_state: str) -> EstadoSaml:
    return estado_mod.validar_estado(relay_state)


def _dados_da_requisicao(request: Request) -> dict[str, Any]:
    """Formato que `onelogin.saml2` espera para reconstruir a URL/esquema
    "atuais" e comparar contra o `Destination`/`Recipient` da asserção.

    Deliberadamente NAO deriva `https`/`http_host` do `request.url` da
    requisicao ASGI recebida: atras de proxy reverso (producao, Traefik) ou
    de um cliente de teste (`starlette.testclient.TestClient`, que sempre
    apresenta `http://testserver`), a URL que o ASGI enxerga raramente bate
    com a URL PUBLICA que o IdP realmente usou para montar `Destination` (a
    mesma `_acs_url()`/`api_base_url` configurada, ja usada para
    `sp.assertionConsumerService.url` nas settings). Usar a configuracao como
    fonte de verdade nos dois lugares evita falso-negativo de
    `Destination`/`Recipient` sem enfraquecer a checagem -- ainda rejeita
    uma asserção destinada a outro host."""
    base = urlparse(_acs_url())
    return {
        "https": "on" if base.scheme == "https" else "off",
        "http_host": base.netloc,
        "script_name": base.path,
        "get_data": dict(request.query_params),
        "post_data": {},
    }


async def concluir_acs(
    sessao_db: AsyncSession,
    *,
    estado: EstadoSaml,
    saml_response_b64: str,
    request: Request,
    ip: str | None,
    user_agent: str | None,
) -> resolucao.ResultadoLoginSso:
    """Valida a asserção e emite a sessao. `sessao_db` ja precisa estar aberta
    para `estado.tenant_id` (responsabilidade do roteador, mesmo padrao de
    `callback_sso`/A9: valida o estado assinado ANTES de abrir a sessao de
    banco, so entao chama `sessao_com_tenant_id`)."""
    config = await ler_config_idp(sessao_db, tenant_id=estado.tenant_id)
    assercao = protocolo.validar_resposta(
        config,
        acs_url=_acs_url(),
        sp_entity_id=_sp_entity_id(),
        saml_response_b64=saml_response_b64,
        request_data=_dados_da_requisicao(request),
        request_id=estado.request_id,
    )
    agora = _dt.datetime.now(_dt.UTC)
    usuario = await resolucao.resolver_ou_vincular_usuario(
        sessao_db,
        tenant_id=estado.tenant_id,
        identificador_externo=assercao.name_id,
        agora=agora,
    )
    return await resolucao.emitir_sessao(
        sessao_db,
        tenant_id=estado.tenant_id,
        usuario=usuario,
        ip=ip,
        user_agent=user_agent,
        agora=agora,
    )


def url_conclusao_spa(resultado: resolucao.ResultadoLoginSso) -> str:
    """URL de redirecionamento final do navegador, com os tokens de sessao no
    FRAGMENTO (nunca na query string: o fragmento nunca trafega ate nenhum
    servidor, nem o nosso nem um proxy intermediario -- browser-only). O SPA
    hospeda `/sso/concluir` (fora do escopo desta fase implementar a pagina
    em si; o contrato so garante o formato do fragmento) e le
    `window.location.hash` para guardar os tokens do mesmo jeito que guarda
    os de `POST /v1/auth/login`."""
    base = obter_configuracao().web_base_url.rstrip("/")
    fragmento = urlencode(
        {
            "accessToken": resultado.access_token,
            "refreshToken": resultado.refresh_token,
            "tokenType": TIPO_TOKEN_BEARER,
            "expiresIn": str(resultado.expires_in),
            "sessaoId": str(resultado.sessao_id),
        }
    )
    return f"{base}{_CAMINHO_CONCLUSAO_SPA}#{fragmento}"
