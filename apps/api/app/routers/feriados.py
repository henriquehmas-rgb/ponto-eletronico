"""Rotas da tag `feriados` do contrato. GERADO -- nao editar.

Calendario de feriados por abrangencia nacional, estadual, municipal, de empresa e de unidade.
Feriados moveis nao guardam data: sao calculados por regra a partir da Pascoa do ano de referencia.

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

roteador = APIRouter(tags=["feriados"])


@roteador.get(
    "/v1/feriado-conjuntos",
    status_code=200,
    operation_id="listarFeriadoConjuntos",
    summary="Listar conjuntos de feriados",
    responses=RESPOSTAS_PADRAO,
)
async def listar_feriado_conjuntos(
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
    abrangencia: Annotated[
        str | None, Query(alias="abrangencia", description="Filtra pela abrangencia.")
    ] = None,
    uf: Annotated[
        str | None, Query(alias="uf", description="Filtra pelos conjuntos estaduais de uma UF.")
    ] = None,
    unidade_id: Annotated[
        UUID | None,
        Query(alias="unidadeId", description="Lista os conjuntos aplicados a uma unidade."),
    ] = None,
    ativo: Annotated[
        bool | None, Query(alias="ativo", description="Filtra por conjuntos ativos.")
    ] = None,
) -> contrato.ListaFeriadoConjunto:
    """Listar conjuntos de feriados

    Fase 0 entrega andaime: a implementacao entra na fase F3.
    """
    raise NaoImplementado("listarFeriadoConjuntos", fase="F3")


@roteador.post(
    "/v1/feriado-conjuntos",
    status_code=201,
    operation_id="criarFeriadoConjunto",
    summary="Criar conjunto de feriados",
    responses=RESPOSTAS_PADRAO,
)
async def criar_feriado_conjunto(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    corpo: contrato.FeriadoConjuntoCriar,
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
) -> contrato.FeriadoConjunto:
    """Criar conjunto de feriados

    Fase 0 entrega andaime: a implementacao entra na fase F3.
    """
    raise NaoImplementado("criarFeriadoConjunto", fase="F3")


@roteador.patch(
    "/v1/feriado-conjuntos/{conjuntoId}",
    status_code=200,
    operation_id="atualizarFeriadoConjunto",
    summary="Atualizar conjunto de feriados",
    responses=RESPOSTAS_PADRAO,
)
async def atualizar_feriado_conjunto(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    conjunto_id: Annotated[
        UUID, Path(alias="conjuntoId", description="Identificador do conjunto.")
    ],
    corpo: contrato.FeriadoConjuntoAtualizar,
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
) -> contrato.FeriadoConjunto:
    """Atualizar conjunto de feriados

    Fase 0 entrega andaime: a implementacao entra na fase F3.
    """
    raise NaoImplementado("atualizarFeriadoConjunto", fase="F3")


@roteador.delete(
    "/v1/feriado-conjuntos/{conjuntoId}",
    status_code=204,
    operation_id="excluirFeriadoConjunto",
    summary="Excluir conjunto de feriados",
    responses=RESPOSTAS_PADRAO,
    response_class=Response,
)
async def excluir_feriado_conjunto(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    conjunto_id: Annotated[
        UUID, Path(alias="conjuntoId", description="Identificador do conjunto.")
    ],
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
    """Excluir conjunto de feriados

    Fase 0 entrega andaime: a implementacao entra na fase F3.
    """
    raise NaoImplementado("excluirFeriadoConjunto", fase="F3")


@roteador.get(
    "/v1/feriados",
    status_code=200,
    operation_id="listarFeriados",
    summary="Listar feriados",
    responses=RESPOSTAS_PADRAO,
)
async def listar_feriados(
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
    feriado_conjunto_id: Annotated[
        UUID | None,
        Query(alias="feriadoConjuntoId", description="Filtra pelos feriados de um conjunto."),
    ] = None,
    unidade_id: Annotated[
        UUID | None,
        Query(
            alias="unidadeId",
            description="Resolve os feriados efetivos de uma unidade, somando os conjuntos aplicados.",
        ),
    ] = None,
    ano: Annotated[
        int | None,
        Query(alias="ano", description="Ano de referencia para resolver os feriados moveis."),
    ] = None,
    de: Annotated[
        date | None, Query(alias="de", description="Considera feriados a partir desta data.")
    ] = None,
    ate: Annotated[
        date | None, Query(alias="ate", description="Considera feriados ate esta data.")
    ] = None,
    tipo: Annotated[str | None, Query(alias="tipo", description="Filtra pelo tipo.")] = None,
) -> contrato.ListaFeriado:
    """Listar feriados

    Fase 0 entrega andaime: a implementacao entra na fase F3.
    """
    raise NaoImplementado("listarFeriados", fase="F3")


@roteador.post(
    "/v1/feriados",
    status_code=201,
    operation_id="criarFeriado",
    summary="Criar feriado",
    responses=RESPOSTAS_PADRAO,
)
async def criar_feriado(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    corpo: contrato.FeriadoCriar,
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
) -> contrato.Feriado:
    """Criar feriado

    Fase 0 entrega andaime: a implementacao entra na fase F3.
    """
    raise NaoImplementado("criarFeriado", fase="F3")


@roteador.delete(
    "/v1/feriados/{feriadoId}",
    status_code=204,
    operation_id="excluirFeriado",
    summary="Excluir feriado",
    responses=RESPOSTAS_PADRAO,
    response_class=Response,
)
async def excluir_feriado(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    feriado_id: Annotated[UUID, Path(alias="feriadoId", description="Identificador do feriado.")],
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
    """Excluir feriado

    Fase 0 entrega andaime: a implementacao entra na fase F3.
    """
    raise NaoImplementado("excluirFeriado", fase="F3")
