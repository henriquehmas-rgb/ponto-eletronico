"""Rotas da tag `admin` do contrato. GERADO -- nao editar.

Administracao do tenant: usuarios, perfis, catalogo de permissoes, clientes de API e healthcheck da instancia.

Regra de negocio destas operacoes entra na fase F1. Ate la toda chamada
responde 501 com PONTO-INT-005. Regerar com
`python tools/gerar_do_contrato.py`.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Path, Query

from app.core.erros import RESPOSTAS_PADRAO, NaoImplementado
from app.schemas import contrato

roteador = APIRouter(tags=["admin"])


@roteador.get(
    "/v1/admin/usuarios",
    status_code=200,
    operation_id="listarUsuarios",
    summary="Listar usuarios",
    responses=RESPOSTAS_PADRAO,
)
async def listar_usuarios(
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
    status: Annotated[
        str | None, Query(alias="status", description="Filtra pela situacao.")
    ] = None,
    tipo: Annotated[
        str | None, Query(alias="tipo", description="Filtra pelo tipo de identidade.")
    ] = None,
    perfil_codigo: Annotated[
        str | None,
        Query(
            alias="perfilCodigo", description="Lista os usuarios que possuem um perfil especifico."
        ),
    ] = None,
    empresa_id: Annotated[
        UUID | None,
        Query(alias="empresaId", description="Filtra pelos usuarios com escopo em uma empresa."),
    ] = None,
    com_colaborador: Annotated[
        bool | None,
        Query(
            alias="comColaborador", description="Filtra usuarios com ou sem colaborador associado."
        ),
    ] = None,
    busca: Annotated[
        str | None,
        Query(
            alias="busca", description="Busca textual livre sobre os campos indexados do recurso."
        ),
    ] = None,
) -> contrato.ListaUsuario:
    """Listar usuarios

    Fase 0 entrega andaime: a implementacao entra na fase F1.
    """
    raise NaoImplementado("listarUsuarios", fase="F1")


@roteador.post(
    "/v1/admin/usuarios",
    status_code=201,
    operation_id="criarUsuario",
    summary="Criar usuario",
    responses=RESPOSTAS_PADRAO,
)
async def criar_usuario(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo devo...",
        ),
    ],
    corpo: contrato.UsuarioCriar,
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
) -> contrato.Usuario:
    """Criar usuario

    Fase 0 entrega andaime: a implementacao entra na fase F1.
    """
    raise NaoImplementado("criarUsuario", fase="F1")


@roteador.patch(
    "/v1/admin/usuarios/{usuarioId}",
    status_code=200,
    operation_id="atualizarUsuario",
    summary="Atualizar usuario",
    responses=RESPOSTAS_PADRAO,
)
async def atualizar_usuario(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo devo...",
        ),
    ],
    usuario_id: Annotated[UUID, Path(alias="usuarioId", description="Identificador do usuario.")],
    corpo: contrato.UsuarioAtualizar,
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
) -> contrato.Usuario:
    """Atualizar usuario

    Fase 0 entrega andaime: a implementacao entra na fase F1.
    """
    raise NaoImplementado("atualizarUsuario", fase="F1")


@roteador.get(
    "/v1/admin/perfis",
    status_code=200,
    operation_id="listarPerfis",
    summary="Listar perfis",
    responses=RESPOSTAS_PADRAO,
)
async def listar_perfis(
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
    sistema: Annotated[
        bool | None,
        Query(alias="sistema", description="Filtra perfis de fabrica ou criados pelo tenant."),
    ] = None,
    somente_leitura: Annotated[
        bool | None,
        Query(
            alias="somenteLeitura",
            description="Filtra perfis que nunca recebem permissao de escrita.",
        ),
    ] = None,
    ativo: Annotated[
        bool | None, Query(alias="ativo", description="Filtra por perfis ativos.")
    ] = None,
) -> contrato.ListaPerfil:
    """Listar perfis

    Fase 0 entrega andaime: a implementacao entra na fase F1.
    """
    raise NaoImplementado("listarPerfis", fase="F1")


@roteador.post(
    "/v1/admin/perfis",
    status_code=201,
    operation_id="criarPerfil",
    summary="Criar perfil",
    responses=RESPOSTAS_PADRAO,
)
async def criar_perfil(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo devo...",
        ),
    ],
    corpo: contrato.PerfilCriar,
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
) -> contrato.Perfil:
    """Criar perfil

    Fase 0 entrega andaime: a implementacao entra na fase F1.
    """
    raise NaoImplementado("criarPerfil", fase="F1")


@roteador.get(
    "/v1/admin/permissoes",
    status_code=200,
    operation_id="listarPermissoes",
    summary="Listar catalogo de permissoes",
    responses=RESPOSTAS_PADRAO,
)
async def listar_permissoes(
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
    modulo: Annotated[
        str | None, Query(alias="modulo", description="Filtra pelo modulo funcional.")
    ] = None,
    recurso: Annotated[
        str | None, Query(alias="recurso", description="Filtra pelo recurso.")
    ] = None,
    sensivel: Annotated[
        bool | None,
        Query(
            alias="sensivel",
            description="Filtra permissoes que exigem registro de acesso sensivel.",
        ),
    ] = None,
) -> contrato.ListaPermissao:
    """Listar catalogo de permissoes

    Fase 0 entrega andaime: a implementacao entra na fase F1.
    """
    raise NaoImplementado("listarPermissoes", fase="F1")


@roteador.get(
    "/v1/admin/api-clients",
    status_code=200,
    operation_id="listarApiClients",
    summary="Listar clientes de API",
    responses=RESPOSTAS_PADRAO,
)
async def listar_api_clients(
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
    ambiente: Annotated[
        str | None, Query(alias="ambiente", description="Filtra pelo ambiente do cliente.")
    ] = None,
    status: Annotated[
        str | None, Query(alias="status", description="Filtra pela situacao.")
    ] = None,
    tipo: Annotated[
        str | None, Query(alias="tipo", description="Filtra pelo tipo de cliente.")
    ] = None,
) -> contrato.ListaApiClient:
    """Listar clientes de API

    Fase 0 entrega andaime: a implementacao entra na fase F1.
    """
    raise NaoImplementado("listarApiClients", fase="F1")


@roteador.post(
    "/v1/admin/api-clients",
    status_code=201,
    operation_id="criarApiClient",
    summary="Criar cliente de API",
    responses=RESPOSTAS_PADRAO,
)
async def criar_api_client(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo devo...",
        ),
    ],
    corpo: contrato.ApiClientCriar,
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
) -> contrato.ApiClientCriado:
    """Criar cliente de API

    Fase 0 entrega andaime: a implementacao entra na fase F1.
    """
    raise NaoImplementado("criarApiClient", fase="F1")
