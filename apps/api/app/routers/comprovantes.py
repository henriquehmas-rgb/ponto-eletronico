"""Rotas da tag `comprovantes` do contrato. GERADO -- nao editar.

Comprovantes de registro.
A impressao no momento da marcacao e dispensada porque o sistema garante acesso eletronico permanente e a extracao das ultimas 48 horas em aplicativo e navegador, conforme a Portaria MTP 671/2021.

Regra de negocio destas operacoes entra na fase F5. Ate la toda chamada
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

roteador = APIRouter(tags=["comprovantes"])


@roteador.get(
    "/v1/comprovantes",
    status_code=200,
    operation_id="listarComprovantes",
    summary="Listar comprovantes",
    responses=RESPOSTAS_PADRAO,
)
async def listar_comprovantes(
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
    colaborador_id: Annotated[
        UUID | None,
        Query(alias="colaboradorId", description="Filtra pelos comprovantes de um colaborador."),
    ] = None,
    marcacao_id: Annotated[
        UUID | None,
        Query(alias="marcacaoId", description="Filtra pelo comprovante de uma marcacao."),
    ] = None,
    cpf: Annotated[
        str | None, Query(alias="cpf", description="Filtra por CPF, somente digitos.")
    ] = None,
    de: Annotated[
        datetime | None,
        Query(alias="de", description="Comprovantes emitidos a partir deste instante."),
    ] = None,
    ate: Annotated[
        datetime | None, Query(alias="ate", description="Comprovantes emitidos ate este instante.")
    ] = None,
) -> contrato.ListaComprovante:
    """Listar comprovantes

    Fase 0 entrega andaime: a implementacao entra na fase F5.
    """
    raise NaoImplementado("listarComprovantes", fase="F5")


@roteador.get(
    "/v1/comprovantes/{comprovanteId}",
    status_code=200,
    operation_id="obterComprovante",
    summary="Obter comprovante",
    responses=RESPOSTAS_PADRAO,
)
async def obter_comprovante(
    comprovante_id: Annotated[
        UUID, Path(alias="comprovanteId", description="Identificador do comprovante.")
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
) -> contrato.Comprovante:
    """Obter comprovante

    Fase 0 entrega andaime: a implementacao entra na fase F5.
    """
    raise NaoImplementado("obterComprovante", fase="F5")


@roteador.get(
    "/v1/colaboradores/{colaboradorId}/comprovantes/recentes",
    status_code=200,
    operation_id="listarComprovantesRecentes",
    summary="Listar comprovantes das ultimas 48 horas",
    responses=RESPOSTAS_PADRAO,
)
async def listar_comprovantes_recentes(
    colaborador_id: Annotated[
        UUID, Path(alias="colaboradorId", description="Identificador do colaborador.")
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
    horas: Annotated[
        int | None,
        Query(
            alias="horas",
            description="Janela em horas. O padrao e 48, que e o minimo legal; valores maiores sao aceitos porque o produto mantem os comprovantes disponiveis de forma permanente.",
        ),
    ] = None,
) -> contrato.ListaComprovante:
    """Listar comprovantes das ultimas 48 horas

    Fase 0 entrega andaime: a implementacao entra na fase F5.
    """
    raise NaoImplementado("listarComprovantesRecentes", fase="F5")
