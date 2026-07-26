"""Rotas da tag `aprovacoes` do contrato. GERADO -- nao editar.

Fila de decisao do aprovador e delegacoes temporarias.
Toda acao exercida por delegacao fica marcada como tal na trilha de auditoria.

Regra de negocio destas operacoes entra na fase F10. Ate la toda chamada
responde 501 com PONTO-INT-005. Regerar com
`python tools/gerar_do_contrato.py`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Path, Query

from app.core.erros import RESPOSTAS_PADRAO, NaoImplementado
from app.schemas import contrato

roteador = APIRouter(tags=["aprovacoes"])


@roteador.get(
    "/v1/aprovacoes",
    status_code=200,
    operation_id="listarAprovacoesPendentes",
    summary="Listar aprovacoes",
    responses=RESPOSTAS_PADRAO,
)
async def listar_aprovacoes_pendentes(
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
    decisao: Annotated[
        str | None,
        Query(
            alias="decisao", description="Filtra pela decisao. O padrao lista apenas as pendentes."
        ),
    ] = None,
    papel: Annotated[
        str | None, Query(alias="papel", description="Filtra pelo papel responsavel.")
    ] = None,
    solicitacao_id: Annotated[
        UUID | None,
        Query(alias="solicitacaoId", description="Filtra pelas etapas de uma solicitacao."),
    ] = None,
    atrasadas: Annotated[
        bool | None,
        Query(alias="atrasadas", description="Lista apenas as etapas com prazo vencido."),
    ] = None,
    incluir_delegadas: Annotated[
        bool | None,
        Query(
            alias="incluirDelegadas",
            description="Inclui as etapas que o usuario responde por delegacao. O padrao e verdadeiro.",
        ),
    ] = None,
) -> contrato.ListaAprovacao:
    """Listar aprovacoes

    Fase 0 entrega andaime: a implementacao entra na fase F10.
    """
    raise NaoImplementado("listarAprovacoesPendentes", fase="F10")


@roteador.post(
    "/v1/aprovacoes/{aprovacaoId}/decidir",
    status_code=200,
    operation_id="decidirAprovacao",
    summary="Decidir etapa de aprovacao",
    responses=RESPOSTAS_PADRAO,
)
async def decidir_aprovacao(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    aprovacao_id: Annotated[
        UUID, Path(alias="aprovacaoId", description="Identificador da etapa de aprovacao.")
    ],
    corpo: contrato.DecisaoRequisicao,
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
) -> contrato.Aprovacao:
    """Decidir etapa de aprovacao

    Fase 0 entrega andaime: a implementacao entra na fase F10.
    """
    raise NaoImplementado("decidirAprovacao", fase="F10")


@roteador.get(
    "/v1/delegacoes",
    status_code=200,
    operation_id="listarDelegacoes",
    summary="Listar delegacoes",
    responses=RESPOSTAS_PADRAO,
)
async def listar_delegacoes(
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
    delegante_usuario_id: Annotated[
        UUID | None,
        Query(
            alias="deleganteUsuarioId",
            description="Filtra pelas delegacoes concedidas por um usuario.",
        ),
    ] = None,
    delegado_usuario_id: Annotated[
        UUID | None,
        Query(
            alias="delegadoUsuarioId",
            description="Filtra pelas delegacoes recebidas por um usuario.",
        ),
    ] = None,
    status: Annotated[
        str | None, Query(alias="status", description="Filtra pela situacao.")
    ] = None,
    vigente_em: Annotated[
        datetime | None,
        Query(
            alias="vigenteEm",
            description="Considera apenas delegacoes vigentes no instante informado.",
        ),
    ] = None,
) -> contrato.ListaDelegacao:
    """Listar delegacoes

    Fase 0 entrega andaime: a implementacao entra na fase F10.
    """
    raise NaoImplementado("listarDelegacoes", fase="F10")


@roteador.post(
    "/v1/delegacoes",
    status_code=201,
    operation_id="criarDelegacao",
    summary="Criar delegacao",
    responses=RESPOSTAS_PADRAO,
)
async def criar_delegacao(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    corpo: contrato.DelegacaoCriar,
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
) -> contrato.Delegacao:
    """Criar delegacao

    Fase 0 entrega andaime: a implementacao entra na fase F10.
    """
    raise NaoImplementado("criarDelegacao", fase="F10")
