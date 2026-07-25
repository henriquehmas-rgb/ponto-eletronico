"""Rotas da tag `solicitacoes` do contrato. GERADO -- nao editar.

Pedidos abertos pelo colaborador ou pelo gestor, com cadeia de aprovacao configuravel, prazos e escalonamento.
Aprovados, materializam tratamento ou afastamento; nunca alteram marcacao diretamente.

Regra de negocio destas operacoes entra na fase F10. Ate la toda chamada
responde 501 com PONTO-INT-005. Regerar com
`python tools/gerar_do_contrato.py`.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Path, Query

from app.core.erros import RESPOSTAS_PADRAO, NaoImplementado
from app.schemas import contrato

roteador = APIRouter(tags=["solicitacoes"])


@roteador.get(
    "/v1/solicitacoes",
    status_code=200,
    operation_id="listarSolicitacoes",
    summary="Listar solicitacoes",
    responses=RESPOSTAS_PADRAO,
)
async def listar_solicitacoes(
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
    colaborador_id: Annotated[
        UUID | None,
        Query(alias="colaboradorId", description="Filtra pelas solicitacoes de um colaborador."),
    ] = None,
    empresa_id: Annotated[
        UUID | None,
        Query(alias="empresaId", description="Filtra pelas solicitacoes de uma empresa."),
    ] = None,
    tipo_solicitacao_id: Annotated[
        UUID | None,
        Query(alias="tipoSolicitacaoId", description="Filtra pelo tipo de solicitacao."),
    ] = None,
    categoria: Annotated[
        str | None, Query(alias="categoria", description="Filtra pela categoria do tipo.")
    ] = None,
    status: Annotated[
        str | None, Query(alias="status", description="Filtra pela situacao.")
    ] = None,
    minhas: Annotated[
        bool | None,
        Query(
            alias="minhas", description="Lista apenas as solicitacoes abertas pelo proprio usuario."
        ),
    ] = None,
    de: Annotated[
        date | None, Query(alias="de", description="Data de referencia a partir de.")
    ] = None,
    ate: Annotated[date | None, Query(alias="ate", description="Data de referencia ate.")] = None,
) -> contrato.ListaSolicitacao:
    """Listar solicitacoes

    Fase 0 entrega andaime: a implementacao entra na fase F10.
    """
    raise NaoImplementado("listarSolicitacoes", fase="F10")


@roteador.post(
    "/v1/solicitacoes",
    status_code=201,
    operation_id="criarSolicitacao",
    summary="Criar solicitacao",
    responses=RESPOSTAS_PADRAO,
)
async def criar_solicitacao(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo devo...",
        ),
    ],
    corpo: contrato.SolicitacaoCriar,
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
) -> contrato.Solicitacao:
    """Criar solicitacao

    Fase 0 entrega andaime: a implementacao entra na fase F10.
    """
    raise NaoImplementado("criarSolicitacao", fase="F10")


@roteador.get(
    "/v1/solicitacoes/{solicitacaoId}",
    status_code=200,
    operation_id="obterSolicitacao",
    summary="Obter solicitacao",
    responses=RESPOSTAS_PADRAO,
)
async def obter_solicitacao(
    solicitacao_id: Annotated[
        UUID, Path(alias="solicitacaoId", description="Identificador da solicitacao.")
    ],
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
) -> contrato.Solicitacao:
    """Obter solicitacao

    Fase 0 entrega andaime: a implementacao entra na fase F10.
    """
    raise NaoImplementado("obterSolicitacao", fase="F10")


@roteador.post(
    "/v1/solicitacoes/{solicitacaoId}/cancelar",
    status_code=200,
    operation_id="cancelarSolicitacao",
    summary="Cancelar solicitacao",
    responses=RESPOSTAS_PADRAO,
)
async def cancelar_solicitacao(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo devo...",
        ),
    ],
    solicitacao_id: Annotated[
        UUID, Path(alias="solicitacaoId", description="Identificador da solicitacao.")
    ],
    corpo: contrato.CancelamentoRequisicao,
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
) -> contrato.Solicitacao:
    """Cancelar solicitacao

    Fase 0 entrega andaime: a implementacao entra na fase F10.
    """
    raise NaoImplementado("cancelarSolicitacao", fase="F10")


@roteador.get(
    "/v1/tipos-solicitacao",
    status_code=200,
    operation_id="listarTiposSolicitacao",
    summary="Listar tipos de solicitacao",
    responses=RESPOSTAS_PADRAO,
)
async def listar_tipos_solicitacao(
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
    categoria: Annotated[
        str | None, Query(alias="categoria", description="Filtra pela categoria.")
    ] = None,
    ativo: Annotated[
        bool | None, Query(alias="ativo", description="Filtra por tipos ativos.")
    ] = None,
) -> contrato.ListaTipoSolicitacao:
    """Listar tipos de solicitacao

    Fase 0 entrega andaime: a implementacao entra na fase F10.
    """
    raise NaoImplementado("listarTiposSolicitacao", fase="F10")


@roteador.post(
    "/v1/tipos-solicitacao",
    status_code=201,
    operation_id="criarTipoSolicitacao",
    summary="Criar tipo de solicitacao",
    responses=RESPOSTAS_PADRAO,
)
async def criar_tipo_solicitacao(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo devo...",
        ),
    ],
    corpo: contrato.TipoSolicitacaoCriar,
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
) -> contrato.TipoSolicitacao:
    """Criar tipo de solicitacao

    Fase 0 entrega andaime: a implementacao entra na fase F10.
    """
    raise NaoImplementado("criarTipoSolicitacao", fase="F10")
