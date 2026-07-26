"""Rotas da tag `jornadas` do contrato. GERADO -- nao editar.

Horarios e jornadas: cargas, tolerancias, tratamento do periodo noturno, limites de hora extra e politica de intervalo.
A jornada e versionada por vigencia, o que permite trocar a regra no meio do mes sem reescrever o passado apurado.

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

roteador = APIRouter(tags=["jornadas"])


@roteador.get(
    "/v1/horarios",
    status_code=200,
    operation_id="listarHorarios",
    summary="Listar horarios",
    responses=RESPOSTAS_PADRAO,
)
async def listar_horarios(
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
    empresa_id: Annotated[
        UUID | None, Query(alias="empresaId", description="Filtra pelos horarios de uma empresa.")
    ] = None,
    cruza_meia_noite: Annotated[
        bool | None, Query(alias="cruzaMeiaNoite", description="Filtra horarios que viram o dia.")
    ] = None,
    ativo: Annotated[
        bool | None, Query(alias="ativo", description="Filtra por horarios ativos.")
    ] = None,
) -> contrato.ListaHorario:
    """Listar horarios

    Fase 0 entrega andaime: a implementacao entra na fase F3.
    """
    raise NaoImplementado("listarHorarios", fase="F3")


@roteador.post(
    "/v1/horarios",
    status_code=201,
    operation_id="criarHorario",
    summary="Criar horario",
    responses=RESPOSTAS_PADRAO,
)
async def criar_horario(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    corpo: contrato.HorarioCriar,
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
) -> contrato.Horario:
    """Criar horario

    Fase 0 entrega andaime: a implementacao entra na fase F3.
    """
    raise NaoImplementado("criarHorario", fase="F3")


@roteador.patch(
    "/v1/horarios/{horarioId}",
    status_code=200,
    operation_id="atualizarHorario",
    summary="Atualizar horario",
    responses=RESPOSTAS_PADRAO,
)
async def atualizar_horario(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    horario_id: Annotated[UUID, Path(alias="horarioId", description="Identificador do horario.")],
    corpo: contrato.HorarioAtualizar,
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
) -> contrato.Horario:
    """Atualizar horario

    Fase 0 entrega andaime: a implementacao entra na fase F3.
    """
    raise NaoImplementado("atualizarHorario", fase="F3")


@roteador.get(
    "/v1/jornadas",
    status_code=200,
    operation_id="listarJornadas",
    summary="Listar jornadas",
    responses=RESPOSTAS_PADRAO,
)
async def listar_jornadas(
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
    empresa_id: Annotated[
        UUID | None, Query(alias="empresaId", description="Filtra pelas jornadas de uma empresa.")
    ] = None,
    tipo: Annotated[
        str | None, Query(alias="tipo", description="Filtra pelo tipo de jornada.")
    ] = None,
    vigente_em: Annotated[
        date | None,
        Query(
            alias="vigenteEm", description="Considera apenas jornadas vigentes na data informada."
        ),
    ] = None,
    ativo: Annotated[
        bool | None, Query(alias="ativo", description="Filtra por jornadas ativas.")
    ] = None,
) -> contrato.ListaJornada:
    """Listar jornadas

    Fase 0 entrega andaime: a implementacao entra na fase F3.
    """
    raise NaoImplementado("listarJornadas", fase="F3")


@roteador.post(
    "/v1/jornadas",
    status_code=201,
    operation_id="criarJornada",
    summary="Criar jornada",
    responses=RESPOSTAS_PADRAO,
)
async def criar_jornada(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    corpo: contrato.JornadaCriar,
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
) -> contrato.Jornada:
    """Criar jornada

    Fase 0 entrega andaime: a implementacao entra na fase F3.
    """
    raise NaoImplementado("criarJornada", fase="F3")


@roteador.get(
    "/v1/jornadas/{jornadaId}",
    status_code=200,
    operation_id="obterJornada",
    summary="Obter jornada",
    responses=RESPOSTAS_PADRAO,
)
async def obter_jornada(
    jornada_id: Annotated[UUID, Path(alias="jornadaId", description="Identificador da jornada.")],
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
) -> contrato.Jornada:
    """Obter jornada

    Fase 0 entrega andaime: a implementacao entra na fase F3.
    """
    raise NaoImplementado("obterJornada", fase="F3")


@roteador.patch(
    "/v1/jornadas/{jornadaId}",
    status_code=200,
    operation_id="atualizarJornada",
    summary="Atualizar jornada",
    responses=RESPOSTAS_PADRAO,
)
async def atualizar_jornada(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    jornada_id: Annotated[UUID, Path(alias="jornadaId", description="Identificador da jornada.")],
    corpo: contrato.JornadaAtualizar,
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
) -> contrato.Jornada:
    """Atualizar jornada

    Fase 0 entrega andaime: a implementacao entra na fase F3.
    """
    raise NaoImplementado("atualizarJornada", fase="F3")


@roteador.delete(
    "/v1/jornadas/{jornadaId}",
    status_code=204,
    operation_id="excluirJornada",
    summary="Excluir jornada",
    responses=RESPOSTAS_PADRAO,
    response_class=Response,
)
async def excluir_jornada(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    jornada_id: Annotated[UUID, Path(alias="jornadaId", description="Identificador da jornada.")],
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
    """Excluir jornada

    Fase 0 entrega andaime: a implementacao entra na fase F3.
    """
    raise NaoImplementado("excluirJornada", fase="F3")


@roteador.get(
    "/v1/vinculos/{vinculoId}/jornadas",
    status_code=200,
    operation_id="listarJornadasVinculo",
    summary="Listar jornadas do vinculo",
    responses=RESPOSTAS_PADRAO,
)
async def listar_jornadas_vinculo(
    vinculo_id: Annotated[UUID, Path(alias="vinculoId", description="Identificador do vinculo.")],
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
    vigente_em: Annotated[
        date | None,
        Query(
            alias="vigenteEm",
            description="Considera apenas a atribuicao vigente na data informada.",
        ),
    ] = None,
) -> contrato.ListaVinculoJornada:
    """Listar jornadas do vinculo

    Fase 0 entrega andaime: a implementacao entra na fase F3.
    """
    raise NaoImplementado("listarJornadasVinculo", fase="F3")


@roteador.post(
    "/v1/vinculos/{vinculoId}/jornadas",
    status_code=201,
    operation_id="atribuirJornadaVinculo",
    summary="Atribuir jornada ao vinculo",
    responses=RESPOSTAS_PADRAO,
)
async def atribuir_jornada_vinculo(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    vinculo_id: Annotated[UUID, Path(alias="vinculoId", description="Identificador do vinculo.")],
    corpo: contrato.VinculoJornadaCriar,
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
) -> contrato.VinculoJornada:
    """Atribuir jornada ao vinculo

    Fase 0 entrega andaime: a implementacao entra na fase F3.
    """
    raise NaoImplementado("atribuirJornadaVinculo", fase="F3")


@roteador.get(
    "/v1/jornadas/resolver",
    status_code=200,
    operation_id="resolverJornadaDoDia",
    summary="Resolver jornada de um dia",
    responses=RESPOSTAS_PADRAO,
)
async def resolver_jornada_do_dia(
    vinculo_id: Annotated[UUID, Query(alias="vinculoId", description="Vinculo a resolver.")],
    data: Annotated[date, Query(alias="data", description="Data a resolver.")],
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
) -> contrato.ResolucaoJornada:
    """Resolver jornada de um dia

    Fase 0 entrega andaime: a implementacao entra na fase F3.
    """
    raise NaoImplementado("resolverJornadaDoDia", fase="F3")
