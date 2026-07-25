"""Rotas da tag `escalas` do contrato. GERADO -- nao editar.

Escalas ciclicas e turnos: 5x2, 6x1, 4x2, 12x36, espanhola e rotativas de N dias.
O ciclo se repete a partir de uma data ancora e qualquer data e resolvida por aritmetica modular, sem materializar calendario.

Regra de negocio destas operacoes entra na fase F3. Ate la toda chamada
responde 501 com PONTO-INT-005. Regerar com
`python tools/gerar_do_contrato.py`.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Path, Query, Response

from app.core.erros import RESPOSTAS_PADRAO, NaoImplementado
from app.schemas import contrato

roteador = APIRouter(tags=["escalas"])


@roteador.get(
    "/v1/escalas",
    status_code=200,
    operation_id="listarEscalas",
    summary="Listar escalas",
    responses=RESPOSTAS_PADRAO,
)
async def listar_escalas(
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
        UUID | None, Query(alias="empresaId", description="Filtra pelas escalas de uma empresa.")
    ] = None,
    tipo: Annotated[str | None, Query(alias="tipo", description="Filtra pelo padrao.")] = None,
    ativo: Annotated[
        bool | None, Query(alias="ativo", description="Filtra por escalas ativas.")
    ] = None,
) -> contrato.ListaEscala:
    """Listar escalas

    Fase 0 entrega andaime: a implementacao entra na fase F3.
    """
    raise NaoImplementado("listarEscalas", fase="F3")


@roteador.post(
    "/v1/escalas",
    status_code=201,
    operation_id="criarEscala",
    summary="Criar escala",
    responses=RESPOSTAS_PADRAO,
)
async def criar_escala(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo devo...",
        ),
    ],
    corpo: contrato.EscalaCriar,
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
) -> contrato.Escala:
    """Criar escala

    Fase 0 entrega andaime: a implementacao entra na fase F3.
    """
    raise NaoImplementado("criarEscala", fase="F3")


@roteador.get(
    "/v1/escalas/{escalaId}",
    status_code=200,
    operation_id="obterEscala",
    summary="Obter escala",
    responses=RESPOSTAS_PADRAO,
)
async def obter_escala(
    escala_id: Annotated[UUID, Path(alias="escalaId", description="Identificador da escala.")],
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
) -> contrato.Escala:
    """Obter escala

    Fase 0 entrega andaime: a implementacao entra na fase F3.
    """
    raise NaoImplementado("obterEscala", fase="F3")


@roteador.patch(
    "/v1/escalas/{escalaId}",
    status_code=200,
    operation_id="atualizarEscala",
    summary="Atualizar escala",
    responses=RESPOSTAS_PADRAO,
)
async def atualizar_escala(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo devo...",
        ),
    ],
    escala_id: Annotated[UUID, Path(alias="escalaId", description="Identificador da escala.")],
    corpo: contrato.EscalaAtualizar,
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
) -> contrato.Escala:
    """Atualizar escala

    Fase 0 entrega andaime: a implementacao entra na fase F3.
    """
    raise NaoImplementado("atualizarEscala", fase="F3")


@roteador.delete(
    "/v1/escalas/{escalaId}",
    status_code=204,
    operation_id="excluirEscala",
    summary="Excluir escala",
    responses=RESPOSTAS_PADRAO,
    response_class=Response,
)
async def excluir_escala(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo devo...",
        ),
    ],
    escala_id: Annotated[UUID, Path(alias="escalaId", description="Identificador da escala.")],
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
    """Excluir escala

    Fase 0 entrega andaime: a implementacao entra na fase F3.
    """
    raise NaoImplementado("excluirEscala", fase="F3")


@roteador.post(
    "/v1/escalas/{escalaId}/atribuicoes",
    status_code=201,
    operation_id="atribuirEscalaVinculo",
    summary="Atribuir escala a vinculo",
    responses=RESPOSTAS_PADRAO,
)
async def atribuir_escala_vinculo(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo devo...",
        ),
    ],
    escala_id: Annotated[UUID, Path(alias="escalaId", description="Identificador da escala.")],
    corpo: contrato.EscalaAtribuicaoCriar,
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
) -> contrato.EscalaAtribuicao:
    """Atribuir escala a vinculo

    Fase 0 entrega andaime: a implementacao entra na fase F3.
    """
    raise NaoImplementado("atribuirEscalaVinculo", fase="F3")


@roteador.get(
    "/v1/turnos",
    status_code=200,
    operation_id="listarTurnos",
    summary="Listar turnos",
    responses=RESPOSTAS_PADRAO,
)
async def listar_turnos(
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
        UUID | None, Query(alias="empresaId", description="Filtra pelos turnos de uma empresa.")
    ] = None,
    tipo: Annotated[str | None, Query(alias="tipo", description="Filtra pela natureza.")] = None,
    ativo: Annotated[
        bool | None, Query(alias="ativo", description="Filtra por turnos ativos.")
    ] = None,
) -> contrato.ListaTurno:
    """Listar turnos

    Fase 0 entrega andaime: a implementacao entra na fase F3.
    """
    raise NaoImplementado("listarTurnos", fase="F3")


@roteador.post(
    "/v1/turnos",
    status_code=201,
    operation_id="criarTurno",
    summary="Criar turno",
    responses=RESPOSTAS_PADRAO,
)
async def criar_turno(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo devo...",
        ),
    ],
    corpo: contrato.TurnoCriar,
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
) -> contrato.Turno:
    """Criar turno

    Fase 0 entrega andaime: a implementacao entra na fase F3.
    """
    raise NaoImplementado("criarTurno", fase="F3")


@roteador.patch(
    "/v1/turnos/{turnoId}",
    status_code=200,
    operation_id="atualizarTurno",
    summary="Atualizar turno",
    responses=RESPOSTAS_PADRAO,
)
async def atualizar_turno(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo devo...",
        ),
    ],
    turno_id: Annotated[UUID, Path(alias="turnoId", description="Identificador do turno.")],
    corpo: contrato.TurnoAtualizar,
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
) -> contrato.Turno:
    """Atualizar turno

    Fase 0 entrega andaime: a implementacao entra na fase F3.
    """
    raise NaoImplementado("atualizarTurno", fase="F3")
