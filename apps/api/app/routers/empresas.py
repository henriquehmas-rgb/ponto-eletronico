"""Rotas da tag `empresas` do contrato. GERADO -- nao editar.

Pessoas juridicas empregadoras.
Matriz e filiais sao registros distintos, cada um com CNPJ proprio, REP-P proprio e arquivos fiscais proprios.

Regra de negocio destas operacoes entra na fase F2. Ate la toda chamada
responde 501 com PONTO-INT-005. Regerar com
`python tools/gerar_do_contrato.py`.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Path, Query, Response

from app.core.erros import RESPOSTAS_PADRAO, NaoImplementado
from app.schemas import contrato

roteador = APIRouter(tags=["empresas"])


@roteador.get(
    "/v1/empresas",
    status_code=200,
    operation_id="listarEmpresas",
    summary="Listar empresas",
    responses=RESPOSTAS_PADRAO,
)
async def listar_empresas(
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
    empresa_id: Annotated[
        UUID | None, Query(alias="empresaId", description="Filtra por identificador exato.")
    ] = None,
    cnpj: Annotated[
        str | None, Query(alias="cnpj", description="Filtra por CNPJ, somente digitos.")
    ] = None,
    tipo: Annotated[
        str | None, Query(alias="tipo", description="Filtra por matriz ou filial.")
    ] = None,
    matriz_id: Annotated[
        UUID | None, Query(alias="matrizId", description="Lista as filiais de uma matriz.")
    ] = None,
    ativo: Annotated[
        bool | None, Query(alias="ativo", description="Filtra por empresas ativas ou inativas.")
    ] = None,
    busca: Annotated[
        str | None,
        Query(
            alias="busca", description="Busca textual livre sobre os campos indexados do recurso."
        ),
    ] = None,
    incluir_excluidos: Annotated[
        bool | None,
        Query(
            alias="incluirExcluidos",
            description="Inclui registros com exclusao logica (excluidoEm preenchido) no resultado.",
        ),
    ] = None,
) -> contrato.ListaEmpresa:
    """Listar empresas

    Fase 0 entrega andaime: a implementacao entra na fase F2.
    """
    raise NaoImplementado("listarEmpresas", fase="F2")


@roteador.post(
    "/v1/empresas",
    status_code=201,
    operation_id="criarEmpresa",
    summary="Criar empresa",
    responses=RESPOSTAS_PADRAO,
)
async def criar_empresa(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo devo...",
        ),
    ],
    corpo: contrato.EmpresaCriar,
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
) -> contrato.Empresa:
    """Criar empresa

    Fase 0 entrega andaime: a implementacao entra na fase F2.
    """
    raise NaoImplementado("criarEmpresa", fase="F2")


@roteador.get(
    "/v1/empresas/{empresaId}",
    status_code=200,
    operation_id="obterEmpresa",
    summary="Obter empresa",
    responses=RESPOSTAS_PADRAO,
)
async def obter_empresa(
    empresa_id: Annotated[UUID, Path(alias="empresaId", description="Identificador da empresa.")],
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
) -> contrato.Empresa:
    """Obter empresa

    Fase 0 entrega andaime: a implementacao entra na fase F2.
    """
    raise NaoImplementado("obterEmpresa", fase="F2")


@roteador.patch(
    "/v1/empresas/{empresaId}",
    status_code=200,
    operation_id="atualizarEmpresa",
    summary="Atualizar empresa",
    responses=RESPOSTAS_PADRAO,
)
async def atualizar_empresa(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo devo...",
        ),
    ],
    empresa_id: Annotated[UUID, Path(alias="empresaId", description="Identificador da empresa.")],
    corpo: contrato.EmpresaAtualizar,
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
) -> contrato.Empresa:
    """Atualizar empresa

    Fase 0 entrega andaime: a implementacao entra na fase F2.
    """
    raise NaoImplementado("atualizarEmpresa", fase="F2")


@roteador.delete(
    "/v1/empresas/{empresaId}",
    status_code=204,
    operation_id="excluirEmpresa",
    summary="Excluir empresa",
    responses=RESPOSTAS_PADRAO,
    response_class=Response,
)
async def excluir_empresa(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo devo...",
        ),
    ],
    empresa_id: Annotated[UUID, Path(alias="empresaId", description="Identificador da empresa.")],
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
    """Excluir empresa

    Fase 0 entrega andaime: a implementacao entra na fase F2.
    """
    raise NaoImplementado("excluirEmpresa", fase="F2")
