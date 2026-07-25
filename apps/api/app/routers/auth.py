"""Rotas da tag `auth` do contrato. GERADO -- nao editar.

Autenticacao de usuarios e de clientes de integracao: login, segundo fator, rotacao de refresh token com deteccao de reuso, reautenticacao para operacao sensivel, recuperacao de senha e emissao de token OAuth 2.0 client credentials.

Regra de negocio destas operacoes entra na fase F1. Ate la toda chamada
responde 501 com PONTO-INT-005. Regerar com
`python tools/gerar_do_contrato.py`.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Path, Query, Response

from app.core.erros import RESPOSTAS_PADRAO, NaoImplementado
from app.schemas import contrato

roteador = APIRouter(tags=["auth"])


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
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo devo...",
        ),
    ],
    corpo: contrato.LoginRequisicao,
    x_tenant: Annotated[
        str | None,
        Header(
            alias="X-Tenant",
            description="Slug ou UUID do tenant alvo. Obrigatorio quando o host nao identifica o tenant (chamadas a api.ponto.<dominio> por cliente de integracao). Em acesso por subd...",
        ),
    ] = None,
    x_request_id: Annotated[
        str | None,
        Header(
            alias="X-Request-Id",
            description="Identificador de correlacao gerado pelo cliente. Quando ausente o servidor gera um e devolve no cabecalho de resposta de mesmo nome. Aparece na trilha de aud...",
        ),
    ] = None,
) -> contrato.LoginResposta:
    """Autenticar usuario

    Fase 0 entrega andaime: a implementacao entra na fase F1.
    """
    raise NaoImplementado("autenticar", fase="F1")


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
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo devo...",
        ),
    ],
    corpo: contrato.MfaVerificacaoRequisicao,
    x_tenant: Annotated[
        str | None,
        Header(
            alias="X-Tenant",
            description="Slug ou UUID do tenant alvo. Obrigatorio quando o host nao identifica o tenant (chamadas a api.ponto.<dominio> por cliente de integracao). Em acesso por subd...",
        ),
    ] = None,
    x_request_id: Annotated[
        str | None,
        Header(
            alias="X-Request-Id",
            description="Identificador de correlacao gerado pelo cliente. Quando ausente o servidor gera um e devolve no cabecalho de resposta de mesmo nome. Aparece na trilha de aud...",
        ),
    ] = None,
) -> contrato.LoginResposta:
    """Verificar segundo fator

    Fase 0 entrega andaime: a implementacao entra na fase F1.
    """
    raise NaoImplementado("verificarSegundoFator", fase="F1")


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
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo devo...",
        ),
    ],
    corpo: contrato.RefreshRequisicao,
    x_tenant: Annotated[
        str | None,
        Header(
            alias="X-Tenant",
            description="Slug ou UUID do tenant alvo. Obrigatorio quando o host nao identifica o tenant (chamadas a api.ponto.<dominio> por cliente de integracao). Em acesso por subd...",
        ),
    ] = None,
    x_request_id: Annotated[
        str | None,
        Header(
            alias="X-Request-Id",
            description="Identificador de correlacao gerado pelo cliente. Quando ausente o servidor gera um e devolve no cabecalho de resposta de mesmo nome. Aparece na trilha de aud...",
        ),
    ] = None,
) -> contrato.LoginResposta:
    """Renovar sessao

    Fase 0 entrega andaime: a implementacao entra na fase F1.
    """
    raise NaoImplementado("renovarSessao", fase="F1")


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
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo devo...",
        ),
    ],
    corpo: contrato.LogoutRequisicao,
    x_tenant: Annotated[
        str | None,
        Header(
            alias="X-Tenant",
            description="Slug ou UUID do tenant alvo. Obrigatorio quando o host nao identifica o tenant (chamadas a api.ponto.<dominio> por cliente de integracao). Em acesso por subd...",
        ),
    ] = None,
    x_request_id: Annotated[
        str | None,
        Header(
            alias="X-Request-Id",
            description="Identificador de correlacao gerado pelo cliente. Quando ausente o servidor gera um e devolve no cabecalho de resposta de mesmo nome. Aparece na trilha de aud...",
        ),
    ] = None,
) -> Response:
    """Encerrar sessao

    Fase 0 entrega andaime: a implementacao entra na fase F1.
    """
    raise NaoImplementado("encerrarSessao", fase="F1")


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
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo devo...",
        ),
    ],
    corpo: contrato.ReautenticacaoRequisicao,
    x_tenant: Annotated[
        str | None,
        Header(
            alias="X-Tenant",
            description="Slug ou UUID do tenant alvo. Obrigatorio quando o host nao identifica o tenant (chamadas a api.ponto.<dominio> por cliente de integracao). Em acesso por subd...",
        ),
    ] = None,
    x_request_id: Annotated[
        str | None,
        Header(
            alias="X-Request-Id",
            description="Identificador de correlacao gerado pelo cliente. Quando ausente o servidor gera um e devolve no cabecalho de resposta de mesmo nome. Aparece na trilha de aud...",
        ),
    ] = None,
) -> contrato.ReautenticacaoResposta:
    """Reautenticar para operacao sensivel

    Fase 0 entrega andaime: a implementacao entra na fase F1.
    """
    raise NaoImplementado("reautenticar", fase="F1")


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
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo devo...",
        ),
    ],
    corpo: contrato.RecuperacaoSenhaRequisicao,
    x_tenant: Annotated[
        str | None,
        Header(
            alias="X-Tenant",
            description="Slug ou UUID do tenant alvo. Obrigatorio quando o host nao identifica o tenant (chamadas a api.ponto.<dominio> por cliente de integracao). Em acesso por subd...",
        ),
    ] = None,
    x_request_id: Annotated[
        str | None,
        Header(
            alias="X-Request-Id",
            description="Identificador de correlacao gerado pelo cliente. Quando ausente o servidor gera um e devolve no cabecalho de resposta de mesmo nome. Aparece na trilha de aud...",
        ),
    ] = None,
) -> Response:
    """Solicitar recuperacao de senha

    Fase 0 entrega andaime: a implementacao entra na fase F1.
    """
    raise NaoImplementado("solicitarRecuperacaoSenha", fase="F1")


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
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo devo...",
        ),
    ],
    corpo: contrato.RedefinicaoSenhaRequisicao,
    x_tenant: Annotated[
        str | None,
        Header(
            alias="X-Tenant",
            description="Slug ou UUID do tenant alvo. Obrigatorio quando o host nao identifica o tenant (chamadas a api.ponto.<dominio> por cliente de integracao). Em acesso por subd...",
        ),
    ] = None,
    x_request_id: Annotated[
        str | None,
        Header(
            alias="X-Request-Id",
            description="Identificador de correlacao gerado pelo cliente. Quando ausente o servidor gera um e devolve no cabecalho de resposta de mesmo nome. Aparece na trilha de aud...",
        ),
    ] = None,
) -> Response:
    """Redefinir senha

    Fase 0 entrega andaime: a implementacao entra na fase F1.
    """
    raise NaoImplementado("redefinirSenha", fase="F1")


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
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo devo...",
        ),
    ],
    corpo: contrato.TokenOAuthRequisicao,
    x_tenant: Annotated[
        str | None,
        Header(
            alias="X-Tenant",
            description="Slug ou UUID do tenant alvo. Obrigatorio quando o host nao identifica o tenant (chamadas a api.ponto.<dominio> por cliente de integracao). Em acesso por subd...",
        ),
    ] = None,
    x_request_id: Annotated[
        str | None,
        Header(
            alias="X-Request-Id",
            description="Identificador de correlacao gerado pelo cliente. Quando ausente o servidor gera um e devolve no cabecalho de resposta de mesmo nome. Aparece na trilha de aud...",
        ),
    ] = None,
) -> contrato.TokenOAuthResposta:
    """Emitir token OAuth 2.0

    Fase 0 entrega andaime: a implementacao entra na fase F1.
    """
    raise NaoImplementado("emitirTokenOAuth", fase="F1")


@roteador.get(
    "/v1/auth/sessoes",
    status_code=200,
    operation_id="listarSessoes",
    summary="Listar sessoes ativas",
    responses=RESPOSTAS_PADRAO,
)
async def listar_sessoes(
    x_tenant: Annotated[
        str | None,
        Header(
            alias="X-Tenant",
            description="Slug ou UUID do tenant alvo. Obrigatorio quando o host nao identifica o tenant (chamadas a api.ponto.<dominio> por cliente de integracao). Em acesso por subd...",
        ),
    ] = None,
    x_request_id: Annotated[
        str | None,
        Header(
            alias="X-Request-Id",
            description="Identificador de correlacao gerado pelo cliente. Quando ausente o servidor gera um e devolve no cabecalho de resposta de mesmo nome. Aparece na trilha de aud...",
        ),
    ] = None,
    cursor: Annotated[
        str | None,
        Query(
            alias="cursor",
            description="Cursor opaco devolvido em paginacao.proximoCursor da pagina anterior. Ausente retorna a primeira pagina. O cursor codifica a ordenacao usada: trocar o parame...",
        ),
    ] = None,
    limite: Annotated[
        int | None, Query(alias="limite", description="Quantidade de itens por pagina.")
    ] = None,
    ordenar: Annotated[
        str | None,
        Query(
            alias="ordenar",
            description="Ordenacao no formato campo:direcao, separando multiplos criterios por virgula. Direcoes aceitas: asc e desc. Campos aceitos sao os documentados em cada opera...",
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
    """Listar sessoes ativas

    Fase 0 entrega andaime: a implementacao entra na fase F1.
    """
    raise NaoImplementado("listarSessoes", fase="F1")


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
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo devo...",
        ),
    ],
    sessao_id: Annotated[UUID, Path(alias="sessaoId", description="Identificador da sessao.")],
    x_tenant: Annotated[
        str | None,
        Header(
            alias="X-Tenant",
            description="Slug ou UUID do tenant alvo. Obrigatorio quando o host nao identifica o tenant (chamadas a api.ponto.<dominio> por cliente de integracao). Em acesso por subd...",
        ),
    ] = None,
    x_request_id: Annotated[
        str | None,
        Header(
            alias="X-Request-Id",
            description="Identificador de correlacao gerado pelo cliente. Quando ausente o servidor gera um e devolve no cabecalho de resposta de mesmo nome. Aparece na trilha de aud...",
        ),
    ] = None,
) -> Response:
    """Revogar sessao

    Fase 0 entrega andaime: a implementacao entra na fase F1.
    """
    raise NaoImplementado("revogarSessao", fase="F1")


@roteador.get(
    "/v1/auth/sessao",
    status_code=200,
    operation_id="obterSessaoAtual",
    summary="Obter contexto da sessao",
    responses=RESPOSTAS_PADRAO,
)
async def obter_sessao_atual(
    x_tenant: Annotated[
        str | None,
        Header(
            alias="X-Tenant",
            description="Slug ou UUID do tenant alvo. Obrigatorio quando o host nao identifica o tenant (chamadas a api.ponto.<dominio> por cliente de integracao). Em acesso por subd...",
        ),
    ] = None,
    x_request_id: Annotated[
        str | None,
        Header(
            alias="X-Request-Id",
            description="Identificador de correlacao gerado pelo cliente. Quando ausente o servidor gera um e devolve no cabecalho de resposta de mesmo nome. Aparece na trilha de aud...",
        ),
    ] = None,
) -> contrato.SessaoAtual:
    """Obter contexto da sessao

    Fase 0 entrega andaime: a implementacao entra na fase F1.
    """
    raise NaoImplementado("obterSessaoAtual", fase="F1")
