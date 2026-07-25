"""Rotas da tag `afastamentos` do contrato. GERADO -- nao editar.

Tipos e periodos de ausencia legitima.
O afastamento entra na apuracao como insumo, NUNCA como marcacao, e e exportado no bloco de ausencias do AEJ.

Regra de negocio destas operacoes entra na fase F3. Ate la toda chamada
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

roteador = APIRouter(tags=["afastamentos"])


@roteador.get(
    "/v1/tipos-afastamento",
    status_code=200,
    operation_id="listarTiposAfastamento",
    summary="Listar tipos de afastamento",
    responses=RESPOSTAS_PADRAO,
)
async def listar_tipos_afastamento(
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
        str | None, Query(alias="categoria", description="Filtra pela categoria legal.")
    ] = None,
    ativo: Annotated[
        bool | None, Query(alias="ativo", description="Filtra por tipos ativos.")
    ] = None,
) -> contrato.ListaTipoAfastamento:
    """Listar tipos de afastamento

    Fase 0 entrega andaime: a implementacao entra na fase F3.
    """
    raise NaoImplementado("listarTiposAfastamento", fase="F3")


@roteador.post(
    "/v1/tipos-afastamento",
    status_code=201,
    operation_id="criarTipoAfastamento",
    summary="Criar tipo de afastamento",
    responses=RESPOSTAS_PADRAO,
)
async def criar_tipo_afastamento(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo devo...",
        ),
    ],
    corpo: contrato.TipoAfastamentoCriar,
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
) -> contrato.TipoAfastamento:
    """Criar tipo de afastamento

    Fase 0 entrega andaime: a implementacao entra na fase F3.
    """
    raise NaoImplementado("criarTipoAfastamento", fase="F3")


@roteador.patch(
    "/v1/tipos-afastamento/{tipoId}",
    status_code=200,
    operation_id="atualizarTipoAfastamento",
    summary="Atualizar tipo de afastamento",
    responses=RESPOSTAS_PADRAO,
)
async def atualizar_tipo_afastamento(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo devo...",
        ),
    ],
    tipo_id: Annotated[UUID, Path(alias="tipoId", description="Identificador do tipo.")],
    corpo: contrato.TipoAfastamentoAtualizar,
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
) -> contrato.TipoAfastamento:
    """Atualizar tipo de afastamento

    Fase 0 entrega andaime: a implementacao entra na fase F3.
    """
    raise NaoImplementado("atualizarTipoAfastamento", fase="F3")


@roteador.get(
    "/v1/afastamentos",
    status_code=200,
    operation_id="listarAfastamentos",
    summary="Listar afastamentos",
    responses=RESPOSTAS_PADRAO,
)
async def listar_afastamentos(
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
        Query(alias="colaboradorId", description="Filtra pelos afastamentos de um colaborador."),
    ] = None,
    vinculo_id: Annotated[
        UUID | None,
        Query(alias="vinculoId", description="Filtra pelos afastamentos de um vinculo."),
    ] = None,
    empresa_id: Annotated[
        UUID | None,
        Query(alias="empresaId", description="Filtra pelos afastamentos de uma empresa."),
    ] = None,
    tipo_afastamento_id: Annotated[
        UUID | None,
        Query(alias="tipoAfastamentoId", description="Filtra pelo tipo de afastamento."),
    ] = None,
    status: Annotated[
        str | None, Query(alias="status", description="Filtra pela situacao.")
    ] = None,
    de: Annotated[
        date | None, Query(alias="de", description="Afastamentos que alcancam esta data ou depois.")
    ] = None,
    ate: Annotated[
        date | None, Query(alias="ate", description="Afastamentos que alcancam esta data ou antes.")
    ] = None,
) -> contrato.ListaAfastamento:
    """Listar afastamentos

    Fase 0 entrega andaime: a implementacao entra na fase F3.
    """
    raise NaoImplementado("listarAfastamentos", fase="F3")


@roteador.post(
    "/v1/afastamentos",
    status_code=201,
    operation_id="criarAfastamento",
    summary="Criar afastamento",
    responses=RESPOSTAS_PADRAO,
)
async def criar_afastamento(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo devo...",
        ),
    ],
    corpo: contrato.AfastamentoCriar,
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
) -> contrato.Afastamento:
    """Criar afastamento

    Fase 0 entrega andaime: a implementacao entra na fase F3.
    """
    raise NaoImplementado("criarAfastamento", fase="F3")


@roteador.get(
    "/v1/afastamentos/{afastamentoId}",
    status_code=200,
    operation_id="obterAfastamento",
    summary="Obter afastamento",
    responses=RESPOSTAS_PADRAO,
)
async def obter_afastamento(
    afastamento_id: Annotated[
        UUID, Path(alias="afastamentoId", description="Identificador do afastamento.")
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
) -> contrato.Afastamento:
    """Obter afastamento

    Fase 0 entrega andaime: a implementacao entra na fase F3.
    """
    raise NaoImplementado("obterAfastamento", fase="F3")


@roteador.patch(
    "/v1/afastamentos/{afastamentoId}",
    status_code=200,
    operation_id="atualizarAfastamento",
    summary="Atualizar afastamento",
    responses=RESPOSTAS_PADRAO,
)
async def atualizar_afastamento(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo devo...",
        ),
    ],
    afastamento_id: Annotated[
        UUID, Path(alias="afastamentoId", description="Identificador do afastamento.")
    ],
    corpo: contrato.AfastamentoAtualizar,
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
) -> contrato.Afastamento:
    """Atualizar afastamento

    Fase 0 entrega andaime: a implementacao entra na fase F3.
    """
    raise NaoImplementado("atualizarAfastamento", fase="F3")


@roteador.delete(
    "/v1/afastamentos/{afastamentoId}",
    status_code=204,
    operation_id="excluirAfastamento",
    summary="Excluir afastamento",
    responses=RESPOSTAS_PADRAO,
    response_class=Response,
)
async def excluir_afastamento(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo devo...",
        ),
    ],
    afastamento_id: Annotated[
        UUID, Path(alias="afastamentoId", description="Identificador do afastamento.")
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
    """Excluir afastamento

    Fase 0 entrega andaime: a implementacao entra na fase F3.
    """
    raise NaoImplementado("excluirAfastamento", fase="F3")
