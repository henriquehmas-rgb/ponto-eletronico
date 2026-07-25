"""Rotas da tag `tratamentos` do contrato. GERADO -- nao editar.

Camada de correcao da jornada, e a UNICA que existe.
Inclusao manual de horario, desconsideracao de batida duplicada, ajuste de intervalo, abono e justificativa vivem aqui, sempre com autor, data, motivo e anexo, e nunca modificam a marcacao original.

Regra de negocio destas operacoes entra na fase F4. Ate la toda chamada
responde 501 com PONTO-INT-005. Regerar com
`python tools/gerar_do_contrato.py`.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Path, Query, Response

from app.core.erros import RESPOSTAS_PADRAO, NaoImplementado
from app.schemas import contrato

roteador = APIRouter(tags=["tratamentos"])


@roteador.post(
    "/v1/tratamentos",
    status_code=201,
    operation_id="criarTratamento",
    summary="Criar tratamento",
    responses=RESPOSTAS_PADRAO,
)
async def criar_tratamento(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo devo...",
        ),
    ],
    corpo: contrato.TratamentoCriar,
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
) -> contrato.Tratamento:
    """Criar tratamento

    Fase 0 entrega andaime: a implementacao entra na fase F4.
    """
    raise NaoImplementado("criarTratamento", fase="F4")


@roteador.get(
    "/v1/tratamentos",
    status_code=200,
    operation_id="listarTratamentos",
    summary="Listar tratamentos",
    responses=RESPOSTAS_PADRAO,
)
async def listar_tratamentos(
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
        Query(alias="colaboradorId", description="Filtra pelos tratamentos de um colaborador."),
    ] = None,
    vinculo_id: Annotated[
        UUID | None, Query(alias="vinculoId", description="Filtra pelos tratamentos de um vinculo.")
    ] = None,
    empresa_id: Annotated[
        UUID | None,
        Query(alias="empresaId", description="Filtra pelos tratamentos de uma empresa."),
    ] = None,
    tipo_tratamento_id: Annotated[
        UUID | None, Query(alias="tipoTratamentoId", description="Filtra pelo tipo de tratamento.")
    ] = None,
    status: Annotated[
        str | None, Query(alias="status", description="Filtra pela situacao.")
    ] = None,
    origem: Annotated[str | None, Query(alias="origem", description="Filtra pela origem.")] = None,
    de: Annotated[
        date | None, Query(alias="de", description="Data de referencia a partir de.")
    ] = None,
    ate: Annotated[date | None, Query(alias="ate", description="Data de referencia ate.")] = None,
    marcacao_id: Annotated[
        UUID | None,
        Query(
            alias="marcacaoId", description="Lista os tratamentos que se referem a uma marcacao."
        ),
    ] = None,
) -> contrato.ListaTratamento:
    """Listar tratamentos

    Fase 0 entrega andaime: a implementacao entra na fase F4.
    """
    raise NaoImplementado("listarTratamentos", fase="F4")


@roteador.get(
    "/v1/tratamentos/{tratamentoId}",
    status_code=200,
    operation_id="obterTratamento",
    summary="Obter tratamento",
    responses=RESPOSTAS_PADRAO,
)
async def obter_tratamento(
    tratamento_id: Annotated[
        UUID, Path(alias="tratamentoId", description="Identificador do tratamento.")
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
) -> contrato.Tratamento:
    """Obter tratamento

    Fase 0 entrega andaime: a implementacao entra na fase F4.
    """
    raise NaoImplementado("obterTratamento", fase="F4")


@roteador.patch(
    "/v1/tratamentos/{tratamentoId}",
    status_code=200,
    operation_id="atualizarTratamento",
    summary="Atualizar tratamento",
    responses=RESPOSTAS_PADRAO,
)
async def atualizar_tratamento(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo devo...",
        ),
    ],
    tratamento_id: Annotated[
        UUID, Path(alias="tratamentoId", description="Identificador do tratamento.")
    ],
    corpo: contrato.TratamentoAtualizar,
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
) -> contrato.Tratamento:
    """Atualizar tratamento

    Fase 0 entrega andaime: a implementacao entra na fase F4.
    """
    raise NaoImplementado("atualizarTratamento", fase="F4")


@roteador.delete(
    "/v1/tratamentos/{tratamentoId}",
    status_code=204,
    operation_id="cancelarTratamento",
    summary="Cancelar tratamento",
    responses=RESPOSTAS_PADRAO,
    response_class=Response,
)
async def cancelar_tratamento(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo devo...",
        ),
    ],
    tratamento_id: Annotated[
        UUID, Path(alias="tratamentoId", description="Identificador do tratamento.")
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
) -> Response:
    """Cancelar tratamento

    Fase 0 entrega andaime: a implementacao entra na fase F4.
    """
    raise NaoImplementado("cancelarTratamento", fase="F4")


@roteador.post(
    "/v1/tratamentos/{tratamentoId}/decidir",
    status_code=200,
    operation_id="decidirTratamento",
    summary="Aprovar ou reprovar tratamento",
    responses=RESPOSTAS_PADRAO,
)
async def decidir_tratamento(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo devo...",
        ),
    ],
    tratamento_id: Annotated[
        UUID, Path(alias="tratamentoId", description="Identificador do tratamento.")
    ],
    corpo: contrato.DecisaoRequisicao,
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
) -> contrato.Tratamento:
    """Aprovar ou reprovar tratamento

    Fase 0 entrega andaime: a implementacao entra na fase F4.
    """
    raise NaoImplementado("decidirTratamento", fase="F4")


@roteador.get(
    "/v1/tipos-tratamento",
    status_code=200,
    operation_id="listarTiposTratamento",
    summary="Listar tipos de tratamento",
    responses=RESPOSTAS_PADRAO,
)
async def listar_tipos_tratamento(
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
) -> contrato.ListaTipoTratamento:
    """Listar tipos de tratamento

    Fase 0 entrega andaime: a implementacao entra na fase F4.
    """
    raise NaoImplementado("listarTiposTratamento", fase="F4")
