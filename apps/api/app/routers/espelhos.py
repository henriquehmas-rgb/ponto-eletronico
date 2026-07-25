"""Rotas da tag `espelhos` do contrato. GERADO -- nao editar.

Espelho de ponto previo e oficial, com assinatura eletronica do colaborador.
A assinatura vincula o hash da versao exata que foi lida: se o espelho mudar, ela deixa de conferir, que e o comportamento desejado.

Regra de negocio destas operacoes entra na fase F10. Ate la toda chamada
responde 501 com PONTO-INT-005. Regerar com
`python tools/gerar_do_contrato.py`.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Path, Query, Response

from app.core.erros import RESPOSTAS_PADRAO, NaoImplementado
from app.schemas import contrato

roteador = APIRouter(tags=["espelhos"])


@roteador.get(
    "/v1/espelhos",
    status_code=200,
    operation_id="listarEspelhos",
    summary="Listar espelhos de ponto",
    responses=RESPOSTAS_PADRAO,
)
async def listar_espelhos(
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
    periodo_id: Annotated[
        UUID | None, Query(alias="periodoId", description="Filtra pelos espelhos de um periodo.")
    ] = None,
    colaborador_id: Annotated[
        UUID | None,
        Query(alias="colaboradorId", description="Filtra pelos espelhos de um colaborador."),
    ] = None,
    vinculo_id: Annotated[
        UUID | None, Query(alias="vinculoId", description="Filtra pelos espelhos de um vinculo.")
    ] = None,
    fechamento_id: Annotated[
        UUID | None,
        Query(alias="fechamentoId", description="Filtra pelos espelhos de um fechamento."),
    ] = None,
    tipo: Annotated[
        str | None, Query(alias="tipo", description="Filtra pela natureza do espelho.")
    ] = None,
    assinado: Annotated[
        bool | None,
        Query(
            alias="assinado",
            description="Filtra por espelhos com ou sem assinatura do colaborador.",
        ),
    ] = None,
) -> contrato.ListaEspelho:
    """Listar espelhos de ponto

    Fase 0 entrega andaime: a implementacao entra na fase F10.
    """
    raise NaoImplementado("listarEspelhos", fase="F10")


@roteador.post(
    "/v1/espelhos",
    status_code=202,
    operation_id="gerarEspelhos",
    summary="Gerar espelhos de ponto",
    responses=RESPOSTAS_PADRAO,
)
async def gerar_espelhos(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo devo...",
        ),
    ],
    corpo: contrato.EspelhoCriar,
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
) -> contrato.ProcessamentoAssincrono:
    """Gerar espelhos de ponto

    Fase 0 entrega andaime: a implementacao entra na fase F10.
    """
    raise NaoImplementado("gerarEspelhos", fase="F10")


@roteador.get(
    "/v1/espelhos/{espelhoId}",
    status_code=200,
    operation_id="obterEspelho",
    summary="Obter espelho de ponto",
    responses=RESPOSTAS_PADRAO,
)
async def obter_espelho(
    espelho_id: Annotated[UUID, Path(alias="espelhoId", description="Identificador do espelho.")],
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
) -> contrato.Espelho:
    """Obter espelho de ponto

    Fase 0 entrega andaime: a implementacao entra na fase F10.
    """
    raise NaoImplementado("obterEspelho", fase="F10")


@roteador.post(
    "/v1/espelhos/{espelhoId}/assinar",
    status_code=201,
    operation_id="assinarEspelho",
    summary="Assinar espelho de ponto",
    responses=RESPOSTAS_PADRAO,
)
async def assinar_espelho(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo devo...",
        ),
    ],
    espelho_id: Annotated[UUID, Path(alias="espelhoId", description="Identificador do espelho.")],
    corpo: contrato.AssinaturaEspelhoRequisicao,
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
) -> contrato.AssinaturaEspelho:
    """Assinar espelho de ponto

    Fase 0 entrega andaime: a implementacao entra na fase F10.
    """
    raise NaoImplementado("assinarEspelho", fase="F10")


@roteador.get(
    "/v1/espelhos/{espelhoId}/pdf",
    status_code=200,
    operation_id="baixarEspelhoPdf",
    summary="Baixar espelho em PDF",
    responses=RESPOSTAS_PADRAO,
    response_class=Response,
)
async def baixar_espelho_pdf(
    espelho_id: Annotated[UUID, Path(alias="espelhoId", description="Identificador do espelho.")],
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
    """Baixar espelho em PDF

    Fase 0 entrega andaime: a implementacao entra na fase F10.
    """
    raise NaoImplementado("baixarEspelhoPdf", fase="F10")
