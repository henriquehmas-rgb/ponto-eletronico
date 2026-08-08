"""Rotas da tag `escalas` do contrato.

Escalas ciclicas e turnos: 5x2, 6x1, 4x2, 12x36, espanhola e rotativas de N dias.
O ciclo se repete a partir de uma data ancora e qualquer data e resolvida por aritmetica modular, sem materializar calendario.

Regra de negocio implementada na fase F3 (agente A1, ownership deste arquivo
-- ver `docs/fases/F03-motor-de-jornada.md`, secao 5). A regra em si vive em
`app.jornada.modelagem.escalas` e `app.jornada.modelagem.turnos`; este
modulo so traduz HTTP <-> servico.

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

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Path, Query, Response
from ponto_contracts import Escala
from sqlalchemy.ext.asyncio import AsyncSession

from app.comum.autenticacao_cliente import (
    ContextoAcesso,
    aplicar_limite_taxa_se_cliente,
    exigir_permissao_ou_escopo,
)
from app.comum.limitador_taxa import exigir_limite_taxa_sessao
from app.core.erros import RESPOSTAS_PADRAO
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

# Uma instancia por par (permissao, escopo) -- nao uma fabrica chamada de novo
# dentro do handler: mesmo motivo documentado em `app.comum.limitador_taxa`
# (identidade estavel do *callable* pro cache de dependencia do FastAPI).
_ACESSO_ESCALAS_LER = exigir_permissao_ou_escopo(permissao="escalas.ler", escopo="jornadas:ler")
_ACESSO_ESCALAS_CRIAR = exigir_permissao_ou_escopo(
    permissao="escalas.criar", escopo="jornadas:escrever"
)
_ACESSO_ESCALAS_EDITAR = exigir_permissao_ou_escopo(
    permissao="escalas.editar", escopo="jornadas:escrever"
)
_ACESSO_ESCALAS_EXCLUIR = exigir_permissao_ou_escopo(
    permissao="escalas.excluir", escopo="jornadas:escrever"
)
_ACESSO_TURNOS_LER = exigir_permissao_ou_escopo(permissao="turnos.ler", escopo="jornadas:ler")
_ACESSO_TURNOS_CRIAR = exigir_permissao_ou_escopo(
    permissao="turnos.criar", escopo="jornadas:escrever"
)
_ACESSO_TURNOS_EDITAR = exigir_permissao_ou_escopo(
    permissao="turnos.editar", escopo="jornadas:escrever"
)


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
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_ESCALAS_LER)],
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
        UUID | None, Query(alias="empresaId", description="Filtra pelas escalas de uma empresa.")
    ] = None,
    tipo: Annotated[str | None, Query(alias="tipo", description="Filtra pelo padrao.")] = None,
    ativo: Annotated[
        bool | None, Query(alias="ativo", description="Filtra por escalas ativas.")
    ] = None,
) -> contrato.ListaEscala:
    """Listar escalas"""
    await aplicar_limite_taxa_se_cliente(response, acesso)
    linhas, paginacao = await servico_escalas.listar_escalas(
        sessao,
        acesso.tenant_id,
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
    dependencies=[Depends(exigir_limite_taxa_sessao())],
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
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_ESCALAS_CRIAR)],
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
) -> contrato.Escala:
    """Criar escala"""
    await aplicar_limite_taxa_se_cliente(response, acesso)
    nova = await servico_escalas.criar_escala(sessao, acesso.tenant_id, corpo)
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
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_ESCALAS_LER)],
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
) -> contrato.Escala:
    """Obter escala"""
    await aplicar_limite_taxa_se_cliente(response, acesso)
    encontrada = await servico_escalas.obter_escala(sessao, escala_id)
    return await _montar_escala(sessao, encontrada)


@roteador.patch(
    "/v1/escalas/{escalaId}",
    status_code=200,
    operation_id="atualizarEscala",
    summary="Atualizar escala",
    responses=RESPOSTAS_PADRAO,
    dependencies=[Depends(exigir_limite_taxa_sessao())],
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
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_ESCALAS_EDITAR)],
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
) -> contrato.Escala:
    """Atualizar escala"""
    await aplicar_limite_taxa_se_cliente(response, acesso)
    atualizada = await servico_escalas.atualizar_escala(sessao, escala_id, corpo)
    return await _montar_escala(sessao, atualizada)


@roteador.delete(
    "/v1/escalas/{escalaId}",
    status_code=204,
    operation_id="excluirEscala",
    summary="Excluir escala",
    responses=RESPOSTAS_PADRAO,
    response_class=Response,
    dependencies=[Depends(exigir_limite_taxa_sessao())],
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
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_ESCALAS_EXCLUIR)],
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
    """Excluir escala"""
    await aplicar_limite_taxa_se_cliente(response, acesso)
    await servico_escalas.excluir_escala(sessao, acesso.tenant_id, escala_id)
    # Reaproveita o `response` injetado (ja carrega os cabecalhos `RateLimit-*`
    # setados acima, quando o acesso e de cliente de integracao) em vez de
    # construir um `Response` novo, que perderia esses cabecalhos.
    response.status_code = 204
    return response


@roteador.post(
    "/v1/escalas/{escalaId}/atribuicoes",
    status_code=201,
    operation_id="atribuirEscalaVinculo",
    summary="Atribuir escala a vinculo",
    responses=RESPOSTAS_PADRAO,
    dependencies=[Depends(exigir_limite_taxa_sessao())],
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
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_ESCALAS_EDITAR)],
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
) -> contrato.EscalaAtribuicao:
    """Atribuir escala a vinculo"""
    await aplicar_limite_taxa_se_cliente(response, acesso)
    nova = await escala_atribuicoes.atribuir_escala_vinculo(
        sessao, acesso.tenant_id, escala_id, corpo
    )
    return contrato.EscalaAtribuicao.model_validate(nova, from_attributes=True)


@roteador.get(
    "/v1/turnos",
    status_code=200,
    operation_id="listarTurnos",
    summary="Listar turnos",
    responses=RESPOSTAS_PADRAO,
)
async def listar_turnos(
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_TURNOS_LER)],
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
        UUID | None, Query(alias="empresaId", description="Filtra pelos turnos de uma empresa.")
    ] = None,
    tipo: Annotated[str | None, Query(alias="tipo", description="Filtra pela natureza.")] = None,
    ativo: Annotated[
        bool | None, Query(alias="ativo", description="Filtra por turnos ativos.")
    ] = None,
) -> contrato.ListaTurno:
    """Listar turnos"""
    await aplicar_limite_taxa_se_cliente(response, acesso)
    linhas, paginacao = await servico_turnos.listar_turnos(
        sessao,
        acesso.tenant_id,
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
    dependencies=[Depends(exigir_limite_taxa_sessao())],
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
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_TURNOS_CRIAR)],
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
) -> contrato.Turno:
    """Criar turno"""
    await aplicar_limite_taxa_se_cliente(response, acesso)
    novo = await servico_turnos.criar_turno(sessao, acesso.tenant_id, corpo)
    return contrato.Turno.model_validate(novo, from_attributes=True)


@roteador.patch(
    "/v1/turnos/{turnoId}",
    status_code=200,
    operation_id="atualizarTurno",
    summary="Atualizar turno",
    responses=RESPOSTAS_PADRAO,
    dependencies=[Depends(exigir_limite_taxa_sessao())],
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
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_TURNOS_EDITAR)],
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
) -> contrato.Turno:
    """Atualizar turno"""
    await aplicar_limite_taxa_se_cliente(response, acesso)
    atualizado = await servico_turnos.atualizar_turno(sessao, turno_id, corpo)
    return contrato.Turno.model_validate(atualizado, from_attributes=True)
