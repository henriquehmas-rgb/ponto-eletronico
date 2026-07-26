"""Rotas da tag `jornadas` do contrato.

Horarios e jornadas: cargas, tolerancias, tratamento do periodo noturno, limites de hora extra e politica de intervalo.
A jornada e versionada por vigencia, o que permite trocar a regra no meio do mes sem reescrever o passado apurado.

Arquivo COMPARTILHADO entre A1 e A3 (F3, PCF secao 5): A1 implementa as 10
operacoes de horarios/jornadas/vinculo-jornada (`listarHorarios` ate
`atribuirJornadaVinculo`), reuso de `app.jornada.modelagem.*`. `resolverJornadaDoDia`
fica como stub `501` ate A3 preencher (T7, chamando
`app.jornada.resolvedor.servico.resolver_jornada_do_dia`) -- ninguem edita a
parte do outro depois de entregue.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Path, Query, Response
from ponto_contracts import Jornada
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.erros import RESPOSTAS_PADRAO
from app.core.seguranca import Sujeito, exigir_permissao, tenant_id_ou_erro
from app.db.sessao import SessaoDb
from app.jornada.modelagem import horarios as servico_horarios
from app.jornada.modelagem import jornadas as servico_jornadas
from app.jornada.modelagem import vinculo_jornadas as servico_vinculo_jornadas
from app.jornada.resolvedor import servico as servico_resolvedor
from app.schemas import contrato

roteador = APIRouter(tags=["jornadas"])


async def _montar_jornada(sessao: AsyncSession, jornada: Jornada) -> contrato.Jornada:
    dias = await servico_jornadas.listar_dias_da_jornada(sessao, jornada.id)
    resposta = contrato.Jornada.model_validate(jornada, from_attributes=True)
    resposta.dias = [contrato.JornadaDia.model_validate(d, from_attributes=True) for d in dias]
    return resposta


@roteador.get(
    "/v1/horarios",
    status_code=200,
    operation_id="listarHorarios",
    summary="Listar horarios",
    responses=RESPOSTAS_PADRAO,
)
async def listar_horarios(
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("horarios.ler"))],
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
        UUID | None, Query(alias="empresaId", description="Filtra pelos horarios de uma empresa.")
    ] = None,
    cruza_meia_noite: Annotated[
        bool | None, Query(alias="cruzaMeiaNoite", description="Filtra horarios que viram o dia.")
    ] = None,
    ativo: Annotated[
        bool | None, Query(alias="ativo", description="Filtra por horarios ativos.")
    ] = None,
) -> contrato.ListaHorario:
    """Listar horarios"""
    tenant_id = tenant_id_ou_erro(sujeito)
    linhas, paginacao = await servico_horarios.listar_horarios(
        sessao,
        tenant_id,
        empresa_id=empresa_id,
        cruza_meia_noite=cruza_meia_noite,
        ativo=ativo,
        cursor=cursor,
        limite=limite,
        ordenar=ordenar,
    )
    dados = [contrato.Horario.model_validate(linha, from_attributes=True) for linha in linhas]
    return contrato.ListaHorario(dados=dados, paginacao=paginacao)


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
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("horarios.criar"))],
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
) -> contrato.Horario:
    """Criar horario"""
    tenant_id = tenant_id_ou_erro(sujeito)
    novo = await servico_horarios.criar_horario(sessao, tenant_id, corpo)
    return contrato.Horario.model_validate(novo, from_attributes=True)


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
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("horarios.editar"))],
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
) -> contrato.Horario:
    """Atualizar horario"""
    tenant_id_ou_erro(sujeito)
    atualizado = await servico_horarios.atualizar_horario(sessao, horario_id, corpo)
    return contrato.Horario.model_validate(atualizado, from_attributes=True)


@roteador.get(
    "/v1/jornadas",
    status_code=200,
    operation_id="listarJornadas",
    summary="Listar jornadas",
    responses=RESPOSTAS_PADRAO,
)
async def listar_jornadas(
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("jornadas.ler"))],
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
    """Listar jornadas"""
    tenant_id = tenant_id_ou_erro(sujeito)
    linhas, paginacao = await servico_jornadas.listar_jornadas(
        sessao,
        tenant_id,
        empresa_id=empresa_id,
        tipo=tipo,
        vigente_em=vigente_em,
        ativo=ativo,
        cursor=cursor,
        limite=limite,
        ordenar=ordenar,
    )
    dados = [await _montar_jornada(sessao, linha) for linha in linhas]
    return contrato.ListaJornada(dados=dados, paginacao=paginacao)


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
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("jornadas.criar"))],
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
) -> contrato.Jornada:
    """Criar jornada"""
    tenant_id = tenant_id_ou_erro(sujeito)
    nova = await servico_jornadas.criar_jornada(sessao, tenant_id, corpo)
    return await _montar_jornada(sessao, nova)


@roteador.get(
    "/v1/jornadas/{jornadaId}",
    status_code=200,
    operation_id="obterJornada",
    summary="Obter jornada",
    responses=RESPOSTAS_PADRAO,
)
async def obter_jornada(
    jornada_id: Annotated[UUID, Path(alias="jornadaId", description="Identificador da jornada.")],
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("jornadas.ler"))],
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
) -> contrato.Jornada:
    """Obter jornada"""
    tenant_id_ou_erro(sujeito)
    encontrada = await servico_jornadas.obter_jornada(sessao, jornada_id)
    return await _montar_jornada(sessao, encontrada)


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
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("jornadas.editar"))],
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
) -> contrato.Jornada:
    """Atualizar jornada"""
    tenant_id_ou_erro(sujeito)
    atualizada = await servico_jornadas.atualizar_jornada(sessao, jornada_id, corpo)
    return await _montar_jornada(sessao, atualizada)


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
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("jornadas.excluir"))],
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
    """Excluir jornada"""
    tenant_id = tenant_id_ou_erro(sujeito)
    await servico_jornadas.excluir_jornada(sessao, tenant_id, jornada_id)
    return Response(status_code=204)


@roteador.get(
    "/v1/vinculos/{vinculoId}/jornadas",
    status_code=200,
    operation_id="listarJornadasVinculo",
    summary="Listar jornadas do vinculo",
    responses=RESPOSTAS_PADRAO,
)
async def listar_jornadas_vinculo(
    vinculo_id: Annotated[UUID, Path(alias="vinculoId", description="Identificador do vinculo.")],
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("jornadas.ler"))],
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
    vigente_em: Annotated[
        date | None,
        Query(
            alias="vigenteEm",
            description="Considera apenas a atribuicao vigente na data informada.",
        ),
    ] = None,
) -> contrato.ListaVinculoJornada:
    """Listar jornadas do vinculo"""
    tenant_id = tenant_id_ou_erro(sujeito)
    linhas, paginacao = await servico_vinculo_jornadas.listar_jornadas_vinculo(
        sessao,
        tenant_id,
        vinculo_id,
        vigente_em=vigente_em,
        cursor=cursor,
        limite=limite,
        ordenar=ordenar,
    )
    dados = [
        contrato.VinculoJornada.model_validate(linha, from_attributes=True) for linha in linhas
    ]
    return contrato.ListaVinculoJornada(dados=dados, paginacao=paginacao)


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
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("jornadas.editar"))],
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
) -> contrato.VinculoJornada:
    """Atribuir jornada ao vinculo"""
    tenant_id = tenant_id_ou_erro(sujeito)
    nova = await servico_vinculo_jornadas.atribuir_jornada_vinculo(
        sessao, tenant_id, vinculo_id, corpo
    )
    return contrato.VinculoJornada.model_validate(nova, from_attributes=True)


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
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("jornadas.ler"))],
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
) -> contrato.ResolucaoJornada:
    """Resolver jornada de um dia

    Ownership de A3 (F3, T7). A1 (dono deste arquivo para as demais 10
    operacoes) nao mexe neste handler.
    """
    tenant_id = tenant_id_ou_erro(sujeito)
    return await servico_resolvedor.resolver_jornada_do_dia(sessao, tenant_id, vinculo_id, data)
