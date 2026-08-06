"""Rotas da tag `solicitacoes` do contrato.

Pedidos abertos pelo colaborador ou pelo gestor, com cadeia de aprovação configurável, prazos e escalonamento.
Aprovados, materializam tratamento ou afastamento; nunca alteram marcação diretamente.

Regra de negócio implementada na fase F10 (agente A1, ownership deste
arquivo -- ver `docs/fases/F10-workflows-aprovacoes-fechamento.md`, seção
5). A regra em si vive em `app.workflow.solicitacoes.tipos`/`servico`
(que também publicam `ajuste.solicitado`); este módulo só traduz
HTTP <-> serviço, mesmo padrão de `app/routers/tratamentos.py` (F4).
"""

from __future__ import annotations

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Path, Query

from app.comum.limitador_taxa import exigir_limite_taxa_sessao
from app.core.erros import RESPOSTAS_PADRAO
from app.core.seguranca import Sujeito, exigir_permissao, tenant_id_ou_erro
from app.db.sessao import SessaoDb
from app.schemas import contrato
from app.workflow.solicitacoes import servico, tipos
from app.workflow.solicitacoes.servico import listar_aprovacoes_da_solicitacao

roteador = APIRouter(tags=["solicitacoes"])


@roteador.get(
    "/v1/solicitacoes",
    status_code=200,
    operation_id="listarSolicitacoes",
    summary="Listar solicitacoes",
    responses=RESPOSTAS_PADRAO,
)
async def listar_solicitacoes(
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("solicitacoes.ler"))],
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
    colaborador_id: Annotated[
        UUID | None,
        Query(alias="colaboradorId", description="Filtra pelas solicitacoes de um colaborador."),
    ] = None,
    empresa_id: Annotated[
        UUID | None,
        Query(alias="empresaId", description="Filtra pelas solicitacoes de uma empresa."),
    ] = None,
    tipo_solicitacao_id: Annotated[
        UUID | None,
        Query(alias="tipoSolicitacaoId", description="Filtra pelo tipo de solicitacao."),
    ] = None,
    categoria: Annotated[
        str | None, Query(alias="categoria", description="Filtra pela categoria do tipo.")
    ] = None,
    status: Annotated[
        str | None, Query(alias="status", description="Filtra pela situacao.")
    ] = None,
    minhas: Annotated[
        bool | None,
        Query(
            alias="minhas", description="Lista apenas as solicitacoes abertas pelo proprio usuario."
        ),
    ] = None,
    de: Annotated[
        date | None, Query(alias="de", description="Data de referencia a partir de.")
    ] = None,
    ate: Annotated[date | None, Query(alias="ate", description="Data de referencia ate.")] = None,
) -> contrato.ListaSolicitacao:
    """Listar solicitacoes"""
    tenant_id = tenant_id_ou_erro(sujeito)
    linhas, paginacao = await servico.listar_solicitacoes(
        sessao,
        tenant_id,
        colaborador_id=colaborador_id,
        empresa_id=empresa_id,
        tipo_solicitacao_id=tipo_solicitacao_id,
        categoria=categoria,
        status=status,
        minhas=minhas,
        usuario_atual_id=sujeito.usuario_id,
        de=de,
        ate=ate,
        cursor=cursor,
        limite=limite,
        ordenar=ordenar,
    )
    dados = [contrato.Solicitacao.model_validate(linha, from_attributes=True) for linha in linhas]
    return contrato.ListaSolicitacao(dados=dados, paginacao=paginacao)


@roteador.post(
    "/v1/solicitacoes",
    status_code=201,
    operation_id="criarSolicitacao",
    summary="Criar solicitacao",
    responses=RESPOSTAS_PADRAO,
    dependencies=[Depends(exigir_limite_taxa_sessao())],
)
async def criar_solicitacao(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    corpo: contrato.SolicitacaoCriar,
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("solicitacoes.criar"))],
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
) -> contrato.Solicitacao:
    """Criar solicitacao"""
    tenant_id = tenant_id_ou_erro(sujeito)
    nova = await servico.criar_solicitacao(sessao, tenant_id, corpo, usuario_id=sujeito.usuario_id)
    return contrato.Solicitacao.model_validate(nova, from_attributes=True)


@roteador.get(
    "/v1/solicitacoes/{solicitacaoId}",
    status_code=200,
    operation_id="obterSolicitacao",
    summary="Obter solicitacao",
    responses=RESPOSTAS_PADRAO,
)
async def obter_solicitacao(
    solicitacao_id: Annotated[
        UUID, Path(alias="solicitacaoId", description="Identificador da solicitacao.")
    ],
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("solicitacoes.ler"))],
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
) -> contrato.Solicitacao:
    """Obter solicitacao

    Devolve o historico completo das etapas (`aprovacoes`), conforme a
    descricao da operacao no contrato -- prova de quem autorizou cada
    correcao de jornada.
    """
    tenant_id_ou_erro(sujeito)
    encontrada = await servico.obter_solicitacao(sessao, solicitacao_id)
    etapas = await listar_aprovacoes_da_solicitacao(sessao, encontrada.tenant_id, encontrada.id)
    schema = contrato.Solicitacao.model_validate(encontrada, from_attributes=True)
    schema.aprovacoes = [
        contrato.Aprovacao.model_validate(etapa, from_attributes=True) for etapa in etapas
    ]
    return schema


@roteador.post(
    "/v1/solicitacoes/{solicitacaoId}/cancelar",
    status_code=200,
    operation_id="cancelarSolicitacao",
    summary="Cancelar solicitacao",
    responses=RESPOSTAS_PADRAO,
    dependencies=[Depends(exigir_limite_taxa_sessao())],
)
async def cancelar_solicitacao(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    solicitacao_id: Annotated[
        UUID, Path(alias="solicitacaoId", description="Identificador da solicitacao.")
    ],
    corpo: contrato.CancelamentoRequisicao,
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("solicitacoes.editar"))],
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
) -> contrato.Solicitacao:
    """Cancelar solicitacao"""
    tenant_id = tenant_id_ou_erro(sujeito)
    cancelada = await servico.cancelar_solicitacao(
        sessao, tenant_id, solicitacao_id, corpo, usuario_id=sujeito.usuario_id
    )
    return contrato.Solicitacao.model_validate(cancelada, from_attributes=True)


@roteador.get(
    "/v1/tipos-solicitacao",
    status_code=200,
    operation_id="listarTiposSolicitacao",
    summary="Listar tipos de solicitacao",
    responses=RESPOSTAS_PADRAO,
)
async def listar_tipos_solicitacao(
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("tipos_solicitacao.ler"))],
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
    categoria: Annotated[
        str | None, Query(alias="categoria", description="Filtra pela categoria.")
    ] = None,
    ativo: Annotated[
        bool | None, Query(alias="ativo", description="Filtra por tipos ativos.")
    ] = None,
) -> contrato.ListaTipoSolicitacao:
    """Listar tipos de solicitacao"""
    tenant_id = tenant_id_ou_erro(sujeito)
    linhas, paginacao = await tipos.listar_tipos_solicitacao(
        sessao,
        tenant_id,
        categoria=categoria,
        ativo=ativo,
        cursor=cursor,
        limite=limite,
        ordenar=ordenar,
    )
    dados = [tipos.tipo_para_schema(linha) for linha in linhas]
    return contrato.ListaTipoSolicitacao(dados=dados, paginacao=paginacao)


@roteador.post(
    "/v1/tipos-solicitacao",
    status_code=201,
    operation_id="criarTipoSolicitacao",
    summary="Criar tipo de solicitacao",
    responses=RESPOSTAS_PADRAO,
    dependencies=[Depends(exigir_limite_taxa_sessao())],
)
async def criar_tipo_solicitacao(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    corpo: contrato.TipoSolicitacaoCriar,
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("tipos_solicitacao.criar"))],
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
) -> contrato.TipoSolicitacao:
    """Criar tipo de solicitacao"""
    tenant_id = tenant_id_ou_erro(sujeito)
    novo = await tipos.criar_tipo_solicitacao(
        sessao, tenant_id, corpo, usuario_id=sujeito.usuario_id
    )
    return tipos.tipo_para_schema(novo)
