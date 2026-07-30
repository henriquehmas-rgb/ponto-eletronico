"""Rotas da tag `aprovacoes` do contrato (inclui as operações da tag
`delegacoes`, mesmo arquivo -- convenção herdada da Fase 0).

Fila de decisao do aprovador e delegacoes temporarias.
Toda acao exercida por delegacao fica marcada como tal na trilha de auditoria.

Regra de negócio implementada na fase F10 (agente A1, ownership deste
arquivo -- ver `docs/fases/F10-workflows-aprovacoes-fechamento.md`, seção
5). A regra em si vive em `app.workflow.aprovacoes.servico`/`delegacoes`;
este módulo só traduz HTTP <-> serviço, mesmo padrão de
`app/routers/tratamentos.py` (F4).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Path, Query, Request

from app.core.erros import RESPOSTAS_PADRAO
from app.core.seguranca import Sujeito, exigir_permissao, tenant_id_ou_erro
from app.db.sessao import SessaoDb
from app.schemas import contrato
from app.workflow.aprovacoes import delegacoes, servico

roteador = APIRouter(tags=["aprovacoes"])


@roteador.get(
    "/v1/aprovacoes",
    status_code=200,
    operation_id="listarAprovacoesPendentes",
    summary="Listar aprovacoes",
    responses=RESPOSTAS_PADRAO,
)
async def listar_aprovacoes_pendentes(
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("aprovacoes.ler"))],
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
    decisao: Annotated[
        str | None,
        Query(
            alias="decisao", description="Filtra pela decisao. O padrao lista apenas as pendentes."
        ),
    ] = None,
    papel: Annotated[
        str | None, Query(alias="papel", description="Filtra pelo papel responsavel.")
    ] = None,
    solicitacao_id: Annotated[
        UUID | None,
        Query(alias="solicitacaoId", description="Filtra pelas etapas de uma solicitacao."),
    ] = None,
    atrasadas: Annotated[
        bool | None,
        Query(alias="atrasadas", description="Lista apenas as etapas com prazo vencido."),
    ] = None,
    incluir_delegadas: Annotated[
        bool | None,
        Query(
            alias="incluirDelegadas",
            description="Inclui as etapas que o usuario responde por delegacao. O padrao e verdadeiro.",
        ),
    ] = None,
) -> contrato.ListaAprovacao:
    """Listar aprovacoes"""
    tenant_id = tenant_id_ou_erro(sujeito)
    linhas, paginacao = await servico.listar_aprovacoes_pendentes(
        sessao,
        tenant_id,
        sujeito_usuario_id=sujeito.usuario_id,
        sujeito_perfis=frozenset(sujeito.perfis),
        decisao=decisao,
        papel=papel,
        solicitacao_id=solicitacao_id,
        atrasadas=atrasadas,
        incluir_delegadas=incluir_delegadas,
        cursor=cursor,
        limite=limite,
        ordenar=ordenar,
    )
    dados = [contrato.Aprovacao.model_validate(linha, from_attributes=True) for linha in linhas]
    return contrato.ListaAprovacao(dados=dados, paginacao=paginacao)


@roteador.post(
    "/v1/aprovacoes/{aprovacaoId}/decidir",
    status_code=200,
    operation_id="decidirAprovacao",
    summary="Decidir etapa de aprovacao",
    responses=RESPOSTAS_PADRAO,
)
async def decidir_aprovacao(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    aprovacao_id: Annotated[
        UUID, Path(alias="aprovacaoId", description="Identificador da etapa de aprovacao.")
    ],
    corpo: contrato.DecisaoRequisicao,
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("aprovacoes.aprovar"))],
    sessao: SessaoDb,
    requisicao: Request,
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
) -> contrato.Aprovacao:
    """Aprovar ou reprovar etapa de aprovacao"""
    tenant_id = tenant_id_ou_erro(sujeito)
    ip = requisicao.client.host if requisicao.client else None
    user_agent = requisicao.headers.get("user-agent")
    decidida = await servico.decidir_aprovacao(
        sessao,
        tenant_id,
        aprovacao_id,
        corpo,
        usuario_id=sujeito.usuario_id,
        ip=ip,
        user_agent=user_agent,
    )
    return contrato.Aprovacao.model_validate(decidida, from_attributes=True)


@roteador.get(
    "/v1/delegacoes",
    status_code=200,
    operation_id="listarDelegacoes",
    summary="Listar delegacoes",
    responses=RESPOSTAS_PADRAO,
)
async def listar_delegacoes(
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("delegacoes.ler"))],
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
    delegante_usuario_id: Annotated[
        UUID | None,
        Query(
            alias="deleganteUsuarioId",
            description="Filtra pelas delegacoes concedidas por um usuario.",
        ),
    ] = None,
    delegado_usuario_id: Annotated[
        UUID | None,
        Query(
            alias="delegadoUsuarioId",
            description="Filtra pelas delegacoes recebidas por um usuario.",
        ),
    ] = None,
    status: Annotated[
        str | None, Query(alias="status", description="Filtra pela situacao.")
    ] = None,
    vigente_em: Annotated[
        datetime | None,
        Query(
            alias="vigenteEm",
            description="Considera apenas delegacoes vigentes no instante informado.",
        ),
    ] = None,
) -> contrato.ListaDelegacao:
    """Listar delegacoes"""
    tenant_id = tenant_id_ou_erro(sujeito)
    linhas, paginacao = await delegacoes.listar_delegacoes(
        sessao,
        tenant_id,
        delegante_usuario_id=delegante_usuario_id,
        delegado_usuario_id=delegado_usuario_id,
        status=status,
        vigente_em=vigente_em,
        cursor=cursor,
        limite=limite,
        ordenar=ordenar,
    )
    dados = [contrato.Delegacao.model_validate(linha, from_attributes=True) for linha in linhas]
    return contrato.ListaDelegacao(dados=dados, paginacao=paginacao)


@roteador.post(
    "/v1/delegacoes",
    status_code=201,
    operation_id="criarDelegacao",
    summary="Criar delegacao",
    responses=RESPOSTAS_PADRAO,
)
async def criar_delegacao(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    corpo: contrato.DelegacaoCriar,
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("delegacoes.criar"))],
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
) -> contrato.Delegacao:
    """Criar delegacao"""
    tenant_id = tenant_id_ou_erro(sujeito)
    nova = await delegacoes.criar_delegacao(sessao, tenant_id, corpo, usuario_id=sujeito.usuario_id)
    return contrato.Delegacao.model_validate(nova, from_attributes=True)
