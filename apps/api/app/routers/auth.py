"""Rotas da tag `auth` do contrato -- autenticacao (F1/A1).

Login, segundo fator, rotacao de refresh token com deteccao de reuso,
reautenticacao para operacao sensivel, recuperacao de senha, OAuth 2.0
client credentials e o ciclo de vida de sessao. A regra de negocio mora em
`app.identidade.autenticacao`, `app.identidade.tokens` e `app.identidade.mfa`;
este modulo so traduz HTTP <-> essas pecas, sem logica propria alem da
resolucao de tenant e da conversao para os schemas do contrato.

**Resolucao de tenant nas rotas publicas** (login, mfa/verificar, refresh,
token OAuth, redefinir senha): o `TenantMiddleware` (F1/A2) ja valida e
publica o tenant em `app.core.contexto` quando o cliente manda `X-Tenant` ou
acessa por subdominio. Ainda assim, cada rota resolve de novo via
`app.identidade.autenticacao.tenant.sessao_com_tenant_resolvido` -- e
idempotente quando o middleware ja rodou, e e o UNICO caminho quando o
identificador so vem no corpo (`LoginRequisicao.tenant`,
`RecuperacaoSenhaRequisicao.tenant`), que o middleware nao enxerga.

**`solicitarRecuperacaoSenha` e o unico caso especial**: identificador ausente
e erro do chamador (`PONTO-VAL-011`), mas identificador presente que nao
resolve a tenant nenhum vira silenciosamente "conta nao encontrada" (202) --
nunca `PONTO-TEN-001`/`003` -- para nao virar oraculo de tenant existente,
espelhando o mesmo cuidado que a resposta ja tem para e-mail inexistente.

**Rotas autenticadas** (`logout`, `reautenticar`, `obterSessaoAtual`) usam
`app.identidade.tokens.dependencias.obter_sujeito_autenticado`: alem de
validar o JWT, reconfirma contra o banco que a sessao (`sid`) segue ativa e
que o tenant do cabecalho, quando enviado, bate com o do token
(`PONTO-TEN-002`). `listarSessoes`/`revogarSessao` usam
`app.core.seguranca.exigir_permissao`, como as demais rotas administrativas
da fase (mesmo padrao de `app/routers/admin.py`).
"""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, Header, Path, Query, Request, Response
from ponto_contracts import Sessao as SessaoOrm
from ponto_contracts import Tenant as TenantOrm
from ponto_contracts import Usuario as UsuarioOrm
from pydantic import BaseModel

from app.comum.ip_confiavel import ip_confiavel_do_cliente
from app.core import contexto
from app.core.erros import RESPOSTAS_PADRAO, ErroDeAplicacao
from app.core.seguranca import Sujeito, exigir_permissao, tenant_id_ou_erro
from app.db.sessao import SessaoDb, fabrica_de_sessoes
from app.identidade.autenticacao import servico as auth_servico
from app.identidade.autenticacao.tenant import (
    resolver_tenant_para_autenticacao as _resolver_tenant,
)
from app.identidade.autenticacao.tenant import (
    sessao_com_tenant_id,
    sessao_com_tenant_resolvido,
)
from app.identidade.rbac.paginacao import paginar
from app.identidade.rbac.resolucao import resolver_sujeito
from app.identidade.tokens import oauth as oauth_mod
from app.identidade.tokens import refresh as refresh_mod
from app.identidade.tokens import sessao as sessao_mod
from app.identidade.tokens.dependencias import SujeitoAutenticado, obter_sujeito_autenticado
from app.schemas import contrato

roteador = APIRouter(tags=["auth"])

#: Unico valor de `tokenType` do contrato. Constante (em vez de literal inline)
#: para nao acionar o alarme falso de "segredo hardcoded" do bandit (S106) em
#: um parametro cujo nome contem "token".
TIPO_TOKEN_BEARER = "Bearer"  # noqa: S105 -- constante de protocolo, nao segredo.


def _para_schema(schema_cls: type[BaseModel], origem: Any, **extras: Any) -> Any:
    """Converte um objeto ORM no schema pydantic do contrato.

    Mesma receita de `app/routers/admin.py:_para_schema`: le, para cada campo
    declarado no schema, o atributo homonimo do objeto ORM (os models de
    `packages/contracts` usam os mesmos nomes de coluna dos schemas gerados) e
    aplica `extras` por cima para os campos computados que nao sao coluna.
    """
    dados = {nome: getattr(origem, nome, None) for nome in schema_cls.model_fields}
    dados.update(extras)
    return schema_cls.model_validate(dados)


def _ip_do_cliente(request: Request) -> str | None:
    """Endereco do cliente final (F14/A2, retrofit -- `app.comum.ip_confiavel`
    honra `X-Forwarded-For`/`X-Real-IP` só quando a conexão vem do proxy
    reverso de produção, `Configuracao.proxies_confiaveis`; nunca de um
    cabeçalho que qualquer chamador pode forjar). Mantido como wrapper local
    (nome já usado por todo o módulo) para não tocar nenhum outro ponto de
    chamada."""
    return ip_confiavel_do_cliente(request)


def _user_agent(request: Request) -> str | None:
    return request.headers.get("user-agent")


def _identificador_tenant(x_tenant: str | None, corpo_tenant: str | None = None) -> str:
    """Precedencia: cabecalho > campo do corpo > tenant ja resolvido pelo middleware."""
    return (x_tenant or corpo_tenant or contexto.tenant_atual() or "").strip()


def _resposta_login(
    *,
    mfa_requerido: bool,
    usuario: Any | None = None,
    desafio_id: UUID | None = None,
    metodos_mfa: list[str] | None = None,
    access_token: str | None = None,
    refresh_token: str | None = None,
    expires_in: int | None = None,
    sessao_id: UUID | None = None,
) -> contrato.LoginResposta:
    """Monta `LoginResposta` via `model_validate` (nao pelo construtor por kwarg).

    Os campos do schema tem alias camelCase (`Field(alias=...)`); sem o plugin
    mypy do pydantic (nao habilitado neste projeto -- ver `pyproject.toml`),
    mypy sintetiza o `__init__` usando o ALIAS, entao `LoginResposta(mfa_requerido=...)`
    falha estaticamente com "unexpected keyword argument" mesmo sendo aceito
    em tempo de execucao (`populate_by_name=True`). `model_validate(dict)`
    aceita `Any` e contorna essa lacuna -- mesma receita de
    `app/routers/admin.py:_para_schema`.
    """
    return contrato.LoginResposta.model_validate(
        {
            "mfa_requerido": mfa_requerido,
            "desafio_id": desafio_id,
            "metodos_mfa": metodos_mfa or None,
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": TIPO_TOKEN_BEARER if access_token else None,
            "expires_in": expires_in,
            "sessao_id": sessao_id,
            "usuario": _para_schema(contrato.Usuario, usuario) if usuario is not None else None,
        }
    )


@roteador.post(
    "/v1/auth/login",
    status_code=200,
    operation_id="autenticar",
    summary="Autenticar usuario",
    responses=RESPOSTAS_PADRAO,
)
async def autenticar(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    corpo: contrato.LoginRequisicao,
    request: Request,
    x_tenant: Annotated[
        str | None,
        Header(
            alias="X-Tenant",
            description="Slug ou UUID do tenant alvo. Obrigatorio quando o host nao identifica o tenant (chamadas a api.ponto.<dominio> por cliente de integracao). Em acesso por…",
        ),
    ] = None,
    x_request_id: Annotated[
        str | None,
        Header(
            alias="X-Request-Id",
            description="Identificador de correlacao gerado pelo cliente. Quando ausente o servidor gera um e devolve no cabecalho de resposta de mesmo nome. Aparece na trilha de…",
        ),
    ] = None,
) -> contrato.LoginResposta:
    """Autenticar usuario."""
    if not corpo.email or not corpo.senha:
        # Corpo sem e-mail/senha: mesma resposta de credencial invalida, nunca
        # um 400 que distinguiria "formato errado" de "credencial errada".
        raise ErroDeAplicacao("PONTO-AUTH-001")
    identificador = _identificador_tenant(x_tenant, corpo.tenant)
    async with sessao_com_tenant_resolvido(identificador) as (sessao_db, tenant_resolvido):
        resultado = await auth_servico.login(
            sessao_db,
            tenant_id=tenant_resolvido.id,
            email=str(corpo.email),
            senha=corpo.senha.get_secret_value(),
            ip=_ip_do_cliente(request),
            user_agent=_user_agent(request),
            fingerprint=corpo.fingerprint,
            dispositivo_identificador=corpo.dispositivo_identificador,
        )
    return _resposta_login(
        mfa_requerido=resultado.mfa_requerido,
        desafio_id=resultado.desafio_id,
        metodos_mfa=resultado.metodos_mfa,
        access_token=resultado.access_token,
        refresh_token=resultado.refresh_token,
        expires_in=resultado.expires_in,
        sessao_id=resultado.sessao_id,
        usuario=resultado.usuario,
    )


@roteador.post(
    "/v1/auth/mfa/verificar",
    status_code=200,
    operation_id="verificarSegundoFator",
    summary="Verificar segundo fator",
    responses=RESPOSTAS_PADRAO,
)
async def verificar_segundo_fator(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    corpo: contrato.MfaVerificacaoRequisicao,
    request: Request,
    x_tenant: Annotated[
        str | None,
        Header(
            alias="X-Tenant",
            description="Slug ou UUID do tenant alvo. Obrigatorio quando o host nao identifica o tenant (chamadas a api.ponto.<dominio> por cliente de integracao). Em acesso por…",
        ),
    ] = None,
    x_request_id: Annotated[
        str | None,
        Header(
            alias="X-Request-Id",
            description="Identificador de correlacao gerado pelo cliente. Quando ausente o servidor gera um e devolve no cabecalho de resposta de mesmo nome. Aparece na trilha de…",
        ),
    ] = None,
) -> contrato.LoginResposta:
    """Verificar segundo fator."""
    if corpo.desafio_id is None or not corpo.codigo:
        raise ErroDeAplicacao("PONTO-AUTH-008")
    identificador = _identificador_tenant(x_tenant)
    async with sessao_com_tenant_resolvido(identificador) as (sessao_db, tenant_resolvido):
        resultado = await auth_servico.verificar_segundo_fator(
            sessao_db,
            tenant_id=tenant_resolvido.id,
            desafio_id=corpo.desafio_id,
            codigo=corpo.codigo,
            metodo=corpo.metodo.value if corpo.metodo else None,
            ip=_ip_do_cliente(request),
            user_agent=_user_agent(request),
        )
    return _resposta_login(
        mfa_requerido=False,
        access_token=resultado.access_token,
        refresh_token=resultado.refresh_token,
        expires_in=resultado.expires_in,
        sessao_id=resultado.sessao_id,
        usuario=resultado.usuario,
    )


@roteador.post(
    "/v1/auth/refresh",
    status_code=200,
    operation_id="renovarSessao",
    summary="Renovar sessao",
    responses=RESPOSTAS_PADRAO,
)
async def renovar_sessao(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    corpo: contrato.RefreshRequisicao,
    request: Request,
    x_tenant: Annotated[
        str | None,
        Header(
            alias="X-Tenant",
            description="Slug ou UUID do tenant alvo. Obrigatorio quando o host nao identifica o tenant (chamadas a api.ponto.<dominio> por cliente de integracao). Em acesso por…",
        ),
    ] = None,
    x_request_id: Annotated[
        str | None,
        Header(
            alias="X-Request-Id",
            description="Identificador de correlacao gerado pelo cliente. Quando ausente o servidor gera um e devolve no cabecalho de resposta de mesmo nome. Aparece na trilha de…",
        ),
    ] = None,
) -> contrato.LoginResposta:
    """Renovar sessao."""
    if not corpo.refresh_token:
        raise ErroDeAplicacao("PONTO-AUTH-006")
    identificador = _identificador_tenant(x_tenant)
    async with sessao_com_tenant_resolvido(identificador) as (sessao_db, tenant_resolvido):
        (
            usuario,
            access_token,
            novo_refresh,
            expires_in,
            sessao_id,
        ) = await auth_servico.renovar_sessao(
            sessao_db,
            tenant_id=tenant_resolvido.id,
            refresh_token_bruto=corpo.refresh_token,
            ip=_ip_do_cliente(request),
            user_agent=_user_agent(request),
        )
    return _resposta_login(
        mfa_requerido=False,
        access_token=access_token,
        refresh_token=novo_refresh,
        expires_in=expires_in,
        sessao_id=sessao_id,
        usuario=usuario,
    )


@roteador.post(
    "/v1/auth/logout",
    status_code=204,
    operation_id="encerrarSessao",
    summary="Encerrar sessao",
    responses=RESPOSTAS_PADRAO,
    response_class=Response,
)
async def encerrar_sessao(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    corpo: contrato.LogoutRequisicao,
    sujeito: Annotated[SujeitoAutenticado, Depends(obter_sujeito_autenticado)],
    x_tenant: Annotated[
        str | None,
        Header(
            alias="X-Tenant",
            description="Slug ou UUID do tenant alvo. Obrigatorio quando o host nao identifica o tenant (chamadas a api.ponto.<dominio> por cliente de integracao). Em acesso por…",
        ),
    ] = None,
    x_request_id: Annotated[
        str | None,
        Header(
            alias="X-Request-Id",
            description="Identificador de correlacao gerado pelo cliente. Quando ausente o servidor gera um e devolve no cabecalho de resposta de mesmo nome. Aparece na trilha de…",
        ),
    ] = None,
) -> Response:
    """Encerrar sessao."""
    async with sessao_com_tenant_id(sujeito.tenant_id) as sessao_db:
        if corpo.refresh_token:
            # Permite encerrar uma sessao diferente da do access token corrente,
            # quando o cliente apresenta o refresh token dela (contrato:
            # `LogoutRequisicao.refreshToken` -- "Refresh token da sessao a
            # encerrar"). O `logout` abaixo continua fechando a sessao do
            # token de acesso apresentado, que e o caso comum.
            await refresh_mod.revogar_por_valor(
                sessao_db,
                tenant_id=sujeito.tenant_id,
                token_bruto=corpo.refresh_token,
                motivo="logout",
            )
        await auth_servico.logout(
            sessao_db,
            tenant_id=sujeito.tenant_id,
            usuario_id=sujeito.usuario_id,
            sessao_id=sujeito.sessao_id,
            todas_as_sessoes=bool(corpo.todas_as_sessoes),
        )
    return Response(status_code=204)


@roteador.post(
    "/v1/auth/reautenticar",
    status_code=200,
    operation_id="reautenticar",
    summary="Reautenticar para operacao sensivel",
    responses=RESPOSTAS_PADRAO,
)
async def reautenticar(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    corpo: contrato.ReautenticacaoRequisicao,
    sujeito: Annotated[SujeitoAutenticado, Depends(obter_sujeito_autenticado)],
    x_tenant: Annotated[
        str | None,
        Header(
            alias="X-Tenant",
            description="Slug ou UUID do tenant alvo. Obrigatorio quando o host nao identifica o tenant (chamadas a api.ponto.<dominio> por cliente de integracao). Em acesso por…",
        ),
    ] = None,
    x_request_id: Annotated[
        str | None,
        Header(
            alias="X-Request-Id",
            description="Identificador de correlacao gerado pelo cliente. Quando ausente o servidor gera um e devolve no cabecalho de resposta de mesmo nome. Aparece na trilha de…",
        ),
    ] = None,
) -> contrato.ReautenticacaoResposta:
    """Reautenticar para operacao sensivel."""
    async with sessao_com_tenant_id(sujeito.tenant_id) as sessao_db:
        resultado = await auth_servico.reautenticar(
            sessao_db,
            tenant_id=sujeito.tenant_id,
            usuario_id=sujeito.usuario_id,
            sessao_id=sujeito.sessao_id,
            senha=corpo.senha.get_secret_value() if corpo.senha else "",
            codigo_mfa=corpo.codigo_mfa,
        )
    return contrato.ReautenticacaoResposta.model_validate(
        {
            "reautenticado_em": resultado.reautenticado_em,
            "valido_ate": resultado.valido_ate,
            "token_operacao": resultado.token_operacao,
        }
    )


@roteador.post(
    "/v1/auth/senha/recuperar",
    status_code=202,
    operation_id="solicitarRecuperacaoSenha",
    summary="Solicitar recuperacao de senha",
    responses=RESPOSTAS_PADRAO,
    response_class=Response,
)
async def solicitar_recuperacao_senha(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    corpo: contrato.RecuperacaoSenhaRequisicao,
    x_tenant: Annotated[
        str | None,
        Header(
            alias="X-Tenant",
            description="Slug ou UUID do tenant alvo. Obrigatorio quando o host nao identifica o tenant (chamadas a api.ponto.<dominio> por cliente de integracao). Em acesso por…",
        ),
    ] = None,
    x_request_id: Annotated[
        str | None,
        Header(
            alias="X-Request-Id",
            description="Identificador de correlacao gerado pelo cliente. Quando ausente o servidor gera um e devolve no cabecalho de resposta de mesmo nome. Aparece na trilha de…",
        ),
    ] = None,
) -> Response:
    """Solicitar recuperacao de senha.

    Resposta sempre 202: identificador de tenant ausente e o unico caso que
    vira erro (`PONTO-VAL-011`, documentado no contrato); tenant informado que
    nao resolve para nenhum tenant real, ou e-mail que nao existe naquele
    tenant, produzem a MESMA resposta 202 vazia -- ver docstring do modulo.
    """
    identificador = _identificador_tenant(x_tenant, corpo.tenant)
    if not identificador:
        raise ErroDeAplicacao("PONTO-VAL-011", detalhe="X-Tenant")

    fabrica = fabrica_de_sessoes()
    async with fabrica() as sessao_db:
        tenant_id: UUID | None = None
        try:
            resolvido = await _resolver_tenant(sessao_db, identificador)
        except ErroDeAplicacao:
            tenant_id = None
        else:
            tenant_id = resolvido.id
        await auth_servico.solicitar_recuperacao_senha(
            sessao_db, tenant_id=tenant_id, email=str(corpo.email or "")
        )
        await sessao_db.commit()
    return Response(status_code=202)


@roteador.post(
    "/v1/auth/senha/redefinir",
    status_code=204,
    operation_id="redefinirSenha",
    summary="Redefinir senha",
    responses=RESPOSTAS_PADRAO,
    response_class=Response,
)
async def redefinir_senha(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    corpo: contrato.RedefinicaoSenhaRequisicao,
    x_tenant: Annotated[
        str | None,
        Header(
            alias="X-Tenant",
            description="Slug ou UUID do tenant alvo. Obrigatorio quando o host nao identifica o tenant (chamadas a api.ponto.<dominio> por cliente de integracao). Em acesso por…",
        ),
    ] = None,
    x_request_id: Annotated[
        str | None,
        Header(
            alias="X-Request-Id",
            description="Identificador de correlacao gerado pelo cliente. Quando ausente o servidor gera um e devolve no cabecalho de resposta de mesmo nome. Aparece na trilha de…",
        ),
    ] = None,
) -> Response:
    """Redefinir senha."""
    if not corpo.token or not corpo.nova_senha:
        raise ErroDeAplicacao("PONTO-AUTH-004")
    identificador = _identificador_tenant(x_tenant)
    async with sessao_com_tenant_resolvido(identificador) as (sessao_db, tenant_resolvido):
        await auth_servico.redefinir_senha(
            sessao_db,
            tenant_id=tenant_resolvido.id,
            token_bruto=corpo.token,
            nova_senha=corpo.nova_senha.get_secret_value(),
        )
    return Response(status_code=204)


@roteador.post(
    "/v1/auth/token",
    status_code=200,
    operation_id="emitirTokenOAuth",
    summary="Emitir token OAuth 2.0",
    responses=RESPOSTAS_PADRAO,
)
async def emitir_token_o_auth(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    corpo: contrato.TokenOAuthRequisicao,
    request: Request,
    x_tenant: Annotated[
        str | None,
        Header(
            alias="X-Tenant",
            description="Slug ou UUID do tenant alvo. Obrigatorio quando o host nao identifica o tenant (chamadas a api.ponto.<dominio> por cliente de integracao). Em acesso por…",
        ),
    ] = None,
    x_request_id: Annotated[
        str | None,
        Header(
            alias="X-Request-Id",
            description="Identificador de correlacao gerado pelo cliente. Quando ausente o servidor gera um e devolve no cabecalho de resposta de mesmo nome. Aparece na trilha de…",
        ),
    ] = None,
    authorization: Annotated[
        str | None,
        Header(
            description="`Basic <client_id:client_secret em base64>`, alternativa ao corpo (RFC 6749 2.3.1)."
        ),
    ] = None,
) -> contrato.TokenOAuthResposta:
    """Emitir token OAuth 2.0 (client credentials)."""
    identificador = _identificador_tenant(x_tenant)
    async with sessao_com_tenant_resolvido(identificador) as (sessao_db, tenant_resolvido):
        credenciais = oauth_mod.extrair_credenciais(
            client_id_corpo=corpo.client_id,
            client_secret_corpo=(
                corpo.client_secret.get_secret_value() if corpo.client_secret else None
            ),
            cabecalho_authorization=authorization,
        )
        cliente = await oauth_mod.autenticar_client(
            sessao_db, tenant_id=tenant_resolvido.id, credenciais=credenciais
        )
        oauth_mod.verificar_origem_permitida(cliente, _ip_do_cliente(request))
        escopos = oauth_mod.calcular_escopo_efetivo(corpo.scope, list(cliente.escopos or []))
        token, expires_in = await oauth_mod.emitir_token(
            sessao_db,
            tenant_id=tenant_resolvido.id,
            cliente=cliente,
            escopos=escopos,
            ip=_ip_do_cliente(request),
        )
    return contrato.TokenOAuthResposta.model_validate(
        {
            "access_token": token,
            "token_type": TIPO_TOKEN_BEARER,
            "expires_in": expires_in,
            "scope": " ".join(escopos) if escopos else None,
        }
    )


@roteador.get(
    "/v1/auth/sessoes",
    status_code=200,
    operation_id="listarSessoes",
    summary="Listar sessoes ativas",
    responses=RESPOSTAS_PADRAO,
)
async def listar_sessoes(
    sessao: SessaoDb,
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("sessoes.ler"))],
    x_tenant: Annotated[
        str | None,
        Header(
            alias="X-Tenant",
            description="Slug ou UUID do tenant alvo. Obrigatorio quando o host nao identifica o tenant (chamadas a api.ponto.<dominio> por cliente de integracao). Em acesso por…",
        ),
    ] = None,
    x_request_id: Annotated[
        str | None,
        Header(
            alias="X-Request-Id",
            description="Identificador de correlacao gerado pelo cliente. Quando ausente o servidor gera um e devolve no cabecalho de resposta de mesmo nome. Aparece na trilha de…",
        ),
    ] = None,
    cursor: Annotated[
        str | None,
        Query(
            alias="cursor",
            description="Cursor opaco devolvido em paginacao.proximoCursor da pagina anterior. Ausente retorna a primeira pagina. O cursor codifica a ordenacao usada: trocar o…",
        ),
    ] = None,
    limite: Annotated[
        int | None, Query(alias="limite", description="Quantidade de itens por pagina.")
    ] = None,
    ordenar: Annotated[
        str | None,
        Query(
            alias="ordenar",
            description="Ordenacao no formato campo:direcao, separando multiplos criterios por virgula. Direcoes aceitas: asc e desc. Campos aceitos sao os documentados em cada…",
        ),
    ] = None,
    incluir_encerradas: Annotated[
        bool | None,
        Query(alias="incluirEncerradas", description="Inclui sessoes ja encerradas no resultado."),
    ] = None,
    usuario_id: Annotated[
        UUID | None,
        Query(
            alias="usuarioId",
            description="Consulta as sessoes de outro usuario. Exige permissao administrativa.",
        ),
    ] = None,
) -> contrato.ListaSessao:
    """Listar sessoes ativas."""
    tenant_id = tenant_id_ou_erro(sujeito)
    alvo = usuario_id or sujeito.usuario_id
    consulta = sa.select(SessaoOrm).where(
        SessaoOrm.tenant_id == tenant_id, SessaoOrm.usuario_id == alvo
    )
    if not incluir_encerradas:
        consulta = consulta.where(SessaoOrm.encerrada_em.is_(None))
    linhas, paginacao = await paginar(
        sessao,
        consulta,
        coluna_criado_em=SessaoOrm.criado_em,
        coluna_id=SessaoOrm.id,
        cursor=cursor,
        limite=limite,
    )
    dados = [_para_schema(contrato.Sessao, linha) for linha in linhas]
    return contrato.ListaSessao(dados=dados, paginacao=contrato.Paginacao.model_validate(paginacao))


@roteador.delete(
    "/v1/auth/sessoes/{sessaoId}",
    status_code=204,
    operation_id="revogarSessao",
    summary="Revogar sessao",
    responses=RESPOSTAS_PADRAO,
    response_class=Response,
)
async def revogar_sessao(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    sessao_id: Annotated[UUID, Path(alias="sessaoId", description="Identificador da sessao.")],
    sessao: SessaoDb,
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("sessoes.excluir"))],
    x_tenant: Annotated[
        str | None,
        Header(
            alias="X-Tenant",
            description="Slug ou UUID do tenant alvo. Obrigatorio quando o host nao identifica o tenant (chamadas a api.ponto.<dominio> por cliente de integracao). Em acesso por…",
        ),
    ] = None,
    x_request_id: Annotated[
        str | None,
        Header(
            alias="X-Request-Id",
            description="Identificador de correlacao gerado pelo cliente. Quando ausente o servidor gera um e devolve no cabecalho de resposta de mesmo nome. Aparece na trilha de…",
        ),
    ] = None,
) -> Response:
    """Revogar sessao."""
    tenant_id = tenant_id_ou_erro(sujeito)
    alvo = await sessao_mod.obter_sessao(sessao, tenant_id=tenant_id, sessao_id=sessao_id)
    if alvo is None:
        raise ErroDeAplicacao("PONTO-REC-001")
    await sessao_mod.encerrar_sessao(
        sessao, tenant_id=tenant_id, sessao_id=sessao_id, motivo="revogacao_admin"
    )
    await sessao_mod.revogar_tokens_da_sessao(
        sessao, tenant_id=tenant_id, sessao_id=sessao_id, motivo="revogacao_admin"
    )
    return Response(status_code=204)


@roteador.get(
    "/v1/auth/sessao",
    status_code=200,
    operation_id="obterSessaoAtual",
    summary="Obter contexto da sessao",
    responses=RESPOSTAS_PADRAO,
)
async def obter_sessao_atual(
    sujeito: Annotated[SujeitoAutenticado, Depends(obter_sujeito_autenticado)],
    x_tenant: Annotated[
        str | None,
        Header(
            alias="X-Tenant",
            description="Slug ou UUID do tenant alvo. Obrigatorio quando o host nao identifica o tenant (chamadas a api.ponto.<dominio> por cliente de integracao). Em acesso por…",
        ),
    ] = None,
    x_request_id: Annotated[
        str | None,
        Header(
            alias="X-Request-Id",
            description="Identificador de correlacao gerado pelo cliente. Quando ausente o servidor gera um e devolve no cabecalho de resposta de mesmo nome. Aparece na trilha de…",
        ),
    ] = None,
) -> contrato.SessaoAtual:
    """Obter contexto da sessao.

    `escopos` e `empresasVisiveis` ficam de fora aqui: o primeiro so se aplica
    a identidade de cliente de integracao (OAuth), nao a sessao humana desta
    rota; o segundo exige enumerar `empresas`, tabela da F2. Registrado em
    `docs/backlog.md`.
    """
    async with sessao_com_tenant_id(sujeito.tenant_id) as sessao_db:
        rbac = await resolver_sujeito(
            sessao_db, tenant_id=sujeito.tenant_id, usuario_id=sujeito.usuario_id
        )
        usuario = (
            await sessao_db.execute(
                sa.select(UsuarioOrm).where(UsuarioOrm.id == sujeito.usuario_id)
            )
        ).scalar_one_or_none()
        tenant_row = (
            await sessao_db.execute(sa.select(TenantOrm).where(TenantOrm.id == sujeito.tenant_id))
        ).scalar_one_or_none()
    return contrato.SessaoAtual.model_validate(
        {
            "usuario": _para_schema(contrato.Usuario, usuario) if usuario else None,
            "tenant": _para_schema(contrato.Tenant, tenant_row) if tenant_row else None,
            "sessao_id": sujeito.sessao_id,
            "perfis": list(rbac.perfis),
            "permissoes": sorted(rbac.permissoes),
            "colaborador_id": usuario.colaborador_id if usuario else None,
        }
    )
