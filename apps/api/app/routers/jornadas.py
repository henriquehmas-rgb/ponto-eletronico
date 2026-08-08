"""Rotas da tag `jornadas` do contrato.

Horarios e jornadas: cargas, tolerancias, tratamento do periodo noturno, limites de hora extra e politica de intervalo.
A jornada e versionada por vigencia, o que permite trocar a regra no meio do mes sem reescrever o passado apurado.

Arquivo COMPARTILHADO entre A1 e A3 (F3, PCF secao 5): A1 implementa as 10
operacoes de horarios/jornadas/vinculo-jornada (`listarHorarios` ate
`atribuirJornadaVinculo`), reuso de `app.jornada.modelagem.*`. `resolverJornadaDoDia`
fica como stub `501` ate A3 preencher (T7, chamando
`app.jornada.resolvedor.servico.resolver_jornada_do_dia`) -- ninguem edita a
parte do outro depois de entregue.

Autenticacao dupla (retrofit de 2026-08-08, decisao do dono do produto
apesar de F14/A2 ter deixado como "sem valor de produto validado ainda",
ver `docs/backlog.md`): contrato ja declarava os tres esquemas alternativos
por operacao (`bearerAuth`/`oauth2`/`apiKeyAuth`), mas so sessao humana era
aceita ate agora. `Depends(exigir_permissao(...))` trocado por
`Depends(exigir_permissao_ou_escopo(...))` (mesmo combinador ja provado em
`app/routers/webhooks.py`/F13) -- sessao humana E' tentada primeiro
(comportamento humano preservado byte a byte), cliente de integracao (OAuth/
API key) so entra quando nao ha sessao humana autenticada.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Path, Query, Response
from ponto_contracts import Jornada
from sqlalchemy.ext.asyncio import AsyncSession

from app.comum.autenticacao_cliente import (
    ContextoAcesso,
    aplicar_limite_taxa_se_cliente,
    exigir_permissao_ou_escopo,
)
from app.comum.limitador_taxa import exigir_limite_taxa_sessao
from app.core.erros import RESPOSTAS_PADRAO
from app.db.sessao import SessaoDb
from app.jornada.modelagem import horarios as servico_horarios
from app.jornada.modelagem import jornadas as servico_jornadas
from app.jornada.modelagem import vinculo_jornadas as servico_vinculo_jornadas
from app.jornada.resolvedor import servico as servico_resolvedor
from app.schemas import contrato

roteador = APIRouter(tags=["jornadas"])

# Uma instancia por par (permissao, escopo) -- nao uma fabrica chamada de novo
# dentro do handler: mesmo motivo documentado em `app.comum.limitador_taxa`
# (identidade estavel do *callable* pro cache de dependencia do FastAPI).
_ACESSO_HORARIOS_LER = exigir_permissao_ou_escopo(permissao="horarios.ler", escopo="jornadas:ler")
_ACESSO_HORARIOS_CRIAR = exigir_permissao_ou_escopo(
    permissao="horarios.criar", escopo="jornadas:escrever"
)
_ACESSO_HORARIOS_EDITAR = exigir_permissao_ou_escopo(
    permissao="horarios.editar", escopo="jornadas:escrever"
)
_ACESSO_JORNADAS_LER = exigir_permissao_ou_escopo(permissao="jornadas.ler", escopo="jornadas:ler")
_ACESSO_JORNADAS_CRIAR = exigir_permissao_ou_escopo(
    permissao="jornadas.criar", escopo="jornadas:escrever"
)
_ACESSO_JORNADAS_EDITAR = exigir_permissao_ou_escopo(
    permissao="jornadas.editar", escopo="jornadas:escrever"
)
_ACESSO_JORNADAS_EXCLUIR = exigir_permissao_ou_escopo(
    permissao="jornadas.excluir", escopo="jornadas:escrever"
)


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
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_HORARIOS_LER)],
    sessao: SessaoDb,
    response: Response,
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
    await aplicar_limite_taxa_se_cliente(response, acesso)
    linhas, paginacao = await servico_horarios.listar_horarios(
        sessao,
        acesso.tenant_id,
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
    dependencies=[Depends(exigir_limite_taxa_sessao())],
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
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_HORARIOS_CRIAR)],
    sessao: SessaoDb,
    response: Response,
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
    await aplicar_limite_taxa_se_cliente(response, acesso)
    novo = await servico_horarios.criar_horario(sessao, acesso.tenant_id, corpo)
    return contrato.Horario.model_validate(novo, from_attributes=True)


@roteador.patch(
    "/v1/horarios/{horarioId}",
    status_code=200,
    operation_id="atualizarHorario",
    summary="Atualizar horario",
    responses=RESPOSTAS_PADRAO,
    dependencies=[Depends(exigir_limite_taxa_sessao())],
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
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_HORARIOS_EDITAR)],
    sessao: SessaoDb,
    response: Response,
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
    await aplicar_limite_taxa_se_cliente(response, acesso)
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
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_JORNADAS_LER)],
    sessao: SessaoDb,
    response: Response,
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
    await aplicar_limite_taxa_se_cliente(response, acesso)
    linhas, paginacao = await servico_jornadas.listar_jornadas(
        sessao,
        acesso.tenant_id,
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
    dependencies=[Depends(exigir_limite_taxa_sessao())],
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
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_JORNADAS_CRIAR)],
    sessao: SessaoDb,
    response: Response,
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
    await aplicar_limite_taxa_se_cliente(response, acesso)
    nova = await servico_jornadas.criar_jornada(sessao, acesso.tenant_id, corpo)
    return await _montar_jornada(sessao, nova)


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
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_JORNADAS_LER)],
    sessao: SessaoDb,
    response: Response,
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

    Registrada ANTES de `/v1/jornadas/{jornadaId}` de proposito: o FastAPI
    casa rota por ordem de registro, nao por especificidade, e um path
    literal (`/resolver`) registrado depois de um path parametrizado
    (`/{jornadaId}`) no mesmo roteador nunca e alcancado -- toda chamada cai
    no `{jornadaId}="resolver"` do handler anterior e falha com
    `PONTO-VAL-005` (UUID invalido). Achado real da F9b/A4 (verificacao
    contra API real), corrigido pelo orquestrador reordenando so a posicao
    deste bloco no arquivo -- nenhuma linha de logica mudou.
    """
    await aplicar_limite_taxa_se_cliente(response, acesso)
    return await servico_resolvedor.resolver_jornada_do_dia(
        sessao, acesso.tenant_id, vinculo_id, data
    )


@roteador.get(
    "/v1/jornadas/{jornadaId}",
    status_code=200,
    operation_id="obterJornada",
    summary="Obter jornada",
    responses=RESPOSTAS_PADRAO,
)
async def obter_jornada(
    jornada_id: Annotated[UUID, Path(alias="jornadaId", description="Identificador da jornada.")],
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_JORNADAS_LER)],
    sessao: SessaoDb,
    response: Response,
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
    await aplicar_limite_taxa_se_cliente(response, acesso)
    encontrada = await servico_jornadas.obter_jornada(sessao, jornada_id)
    return await _montar_jornada(sessao, encontrada)


@roteador.patch(
    "/v1/jornadas/{jornadaId}",
    status_code=200,
    operation_id="atualizarJornada",
    summary="Atualizar jornada",
    responses=RESPOSTAS_PADRAO,
    dependencies=[Depends(exigir_limite_taxa_sessao())],
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
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_JORNADAS_EDITAR)],
    sessao: SessaoDb,
    response: Response,
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
    await aplicar_limite_taxa_se_cliente(response, acesso)
    atualizada = await servico_jornadas.atualizar_jornada(sessao, jornada_id, corpo)
    return await _montar_jornada(sessao, atualizada)


@roteador.delete(
    "/v1/jornadas/{jornadaId}",
    status_code=204,
    operation_id="excluirJornada",
    summary="Excluir jornada",
    responses=RESPOSTAS_PADRAO,
    response_class=Response,
    dependencies=[Depends(exigir_limite_taxa_sessao())],
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
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_JORNADAS_EXCLUIR)],
    sessao: SessaoDb,
    response: Response,
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
    await aplicar_limite_taxa_se_cliente(response, acesso)
    await servico_jornadas.excluir_jornada(sessao, acesso.tenant_id, jornada_id)
    # Reaproveita o `response` injetado (ja carrega os cabecalhos `RateLimit-*`
    # setados acima, quando o acesso e de cliente de integracao) em vez de
    # construir um `Response` novo, que perderia esses cabecalhos.
    response.status_code = 204
    return response


@roteador.get(
    "/v1/vinculos/{vinculoId}/jornadas",
    status_code=200,
    operation_id="listarJornadasVinculo",
    summary="Listar jornadas do vinculo",
    responses=RESPOSTAS_PADRAO,
)
async def listar_jornadas_vinculo(
    vinculo_id: Annotated[UUID, Path(alias="vinculoId", description="Identificador do vinculo.")],
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_JORNADAS_LER)],
    sessao: SessaoDb,
    response: Response,
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
    await aplicar_limite_taxa_se_cliente(response, acesso)
    linhas, paginacao = await servico_vinculo_jornadas.listar_jornadas_vinculo(
        sessao,
        acesso.tenant_id,
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
    dependencies=[Depends(exigir_limite_taxa_sessao())],
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
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_JORNADAS_EDITAR)],
    sessao: SessaoDb,
    response: Response,
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
    await aplicar_limite_taxa_se_cliente(response, acesso)
    nova = await servico_vinculo_jornadas.atribuir_jornada_vinculo(
        sessao, acesso.tenant_id, vinculo_id, corpo
    )
    return contrato.VinculoJornada.model_validate(nova, from_attributes=True)
