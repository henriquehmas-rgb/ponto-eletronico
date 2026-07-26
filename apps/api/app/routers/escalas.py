"""Rotas da tag `escalas` do contrato.

Escalas ciclicas e turnos: 5x2, 6x1, 4x2, 12x36, espanhola e rotativas de N dias.
O ciclo se repete a partir de uma data ancora e qualquer data e resolvida por aritmetica modular, sem materializar calendario.

Regra de negocio implementada na fase F3 (agente A1, ownership deste arquivo
-- ver `docs/fases/F03-motor-de-jornada.md`, secao 5). A regra em si vive em
`app.jornada.modelagem.escalas` e `app.jornada.modelagem.turnos`; este
modulo so traduz HTTP <-> servico.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Path, Query, Response
from ponto_contracts import Escala
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.erros import RESPOSTAS_PADRAO
from app.core.seguranca import Sujeito, exigir_permissao, tenant_id_ou_erro
from app.db.sessao import SessaoDb
from app.jornada.modelagem import (
    escala_atribuicoes,
)
from app.jornada.modelagem import (
    escalas as servico_escalas,
)
from app.jornada.modelagem import (
    turnos as servico_turnos,
)
from app.schemas import contrato

roteador = APIRouter(tags=["escalas"])


async def _montar_escala(sessao: AsyncSession, escala: Escala) -> contrato.Escala:
    ciclos = await servico_escalas.listar_ciclos_da_escala(sessao, escala.id)
    resposta = contrato.Escala.model_validate(escala, from_attributes=True)
    resposta.ciclos = [contrato.EscalaCiclo.model_validate(c, from_attributes=True) for c in ciclos]
    return resposta


@roteador.get(
    "/v1/escalas",
    status_code=200,
    operation_id="listarEscalas",
    summary="Listar escalas",
    responses=RESPOSTAS_PADRAO,
)
async def listar_escalas(
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("escalas.ler"))],
    sessao: SessaoDb,
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
        UUID | None, Query(alias="empresaId", description="Filtra pelas escalas de uma empresa.")
    ] = None,
    tipo: Annotated[str | None, Query(alias="tipo", description="Filtra pelo padrao.")] = None,
    ativo: Annotated[
        bool | None, Query(alias="ativo", description="Filtra por escalas ativas.")
    ] = None,
) -> contrato.ListaEscala:
    """Listar escalas"""
    tenant_id = tenant_id_ou_erro(sujeito)
    linhas, paginacao = await servico_escalas.listar_escalas(
        sessao,
        tenant_id,
        empresa_id=empresa_id,
        tipo=tipo,
        ativo=ativo,
        cursor=cursor,
        limite=limite,
        ordenar=ordenar,
    )
    dados = [await _montar_escala(sessao, linha) for linha in linhas]
    return contrato.ListaEscala(dados=dados, paginacao=paginacao)


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
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    corpo: contrato.EscalaCriar,
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("escalas.criar"))],
    sessao: SessaoDb,
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
) -> contrato.Escala:
    """Criar escala"""
    tenant_id = tenant_id_ou_erro(sujeito)
    nova = await servico_escalas.criar_escala(sessao, tenant_id, corpo)
    return await _montar_escala(sessao, nova)


@roteador.get(
    "/v1/escalas/{escalaId}",
    status_code=200,
    operation_id="obterEscala",
    summary="Obter escala",
    responses=RESPOSTAS_PADRAO,
)
async def obter_escala(
    escala_id: Annotated[UUID, Path(alias="escalaId", description="Identificador da escala.")],
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("escalas.ler"))],
    sessao: SessaoDb,
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
) -> contrato.Escala:
    """Obter escala"""
    tenant_id_ou_erro(sujeito)
    encontrada = await servico_escalas.obter_escala(sessao, escala_id)
    return await _montar_escala(sessao, encontrada)


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
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    escala_id: Annotated[UUID, Path(alias="escalaId", description="Identificador da escala.")],
    corpo: contrato.EscalaAtualizar,
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("escalas.editar"))],
    sessao: SessaoDb,
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
) -> contrato.Escala:
    """Atualizar escala"""
    tenant_id_ou_erro(sujeito)
    atualizada = await servico_escalas.atualizar_escala(sessao, escala_id, corpo)
    return await _montar_escala(sessao, atualizada)


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
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    escala_id: Annotated[UUID, Path(alias="escalaId", description="Identificador da escala.")],
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("escalas.excluir"))],
    sessao: SessaoDb,
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
    """Excluir escala"""
    tenant_id = tenant_id_ou_erro(sujeito)
    await servico_escalas.excluir_escala(sessao, tenant_id, escala_id)
    return Response(status_code=204)


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
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    escala_id: Annotated[UUID, Path(alias="escalaId", description="Identificador da escala.")],
    corpo: contrato.EscalaAtribuicaoCriar,
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("escalas.editar"))],
    sessao: SessaoDb,
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
) -> contrato.EscalaAtribuicao:
    """Atribuir escala a vinculo"""
    tenant_id = tenant_id_ou_erro(sujeito)
    nova = await escala_atribuicoes.atribuir_escala_vinculo(sessao, tenant_id, escala_id, corpo)
    return contrato.EscalaAtribuicao.model_validate(nova, from_attributes=True)


@roteador.get(
    "/v1/turnos",
    status_code=200,
    operation_id="listarTurnos",
    summary="Listar turnos",
    responses=RESPOSTAS_PADRAO,
)
async def listar_turnos(
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("turnos.ler"))],
    sessao: SessaoDb,
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
        UUID | None, Query(alias="empresaId", description="Filtra pelos turnos de uma empresa.")
    ] = None,
    tipo: Annotated[str | None, Query(alias="tipo", description="Filtra pela natureza.")] = None,
    ativo: Annotated[
        bool | None, Query(alias="ativo", description="Filtra por turnos ativos.")
    ] = None,
) -> contrato.ListaTurno:
    """Listar turnos"""
    tenant_id = tenant_id_ou_erro(sujeito)
    linhas, paginacao = await servico_turnos.listar_turnos(
        sessao,
        tenant_id,
        empresa_id=empresa_id,
        tipo=tipo,
        ativo=ativo,
        cursor=cursor,
        limite=limite,
        ordenar=ordenar,
    )
    dados = [contrato.Turno.model_validate(linha, from_attributes=True) for linha in linhas]
    return contrato.ListaTurno(dados=dados, paginacao=paginacao)


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
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    corpo: contrato.TurnoCriar,
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("turnos.criar"))],
    sessao: SessaoDb,
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
) -> contrato.Turno:
    """Criar turno"""
    tenant_id = tenant_id_ou_erro(sujeito)
    novo = await servico_turnos.criar_turno(sessao, tenant_id, corpo)
    return contrato.Turno.model_validate(novo, from_attributes=True)


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
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    turno_id: Annotated[UUID, Path(alias="turnoId", description="Identificador do turno.")],
    corpo: contrato.TurnoAtualizar,
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("turnos.editar"))],
    sessao: SessaoDb,
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
) -> contrato.Turno:
    """Atualizar turno"""
    tenant_id_ou_erro(sujeito)
    atualizado = await servico_turnos.atualizar_turno(sessao, turno_id, corpo)
    return contrato.Turno.model_validate(atualizado, from_attributes=True)
