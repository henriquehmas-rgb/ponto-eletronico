"""Rotas da tag `solicitacoes` do contrato.

Pedidos abertos pelo colaborador ou pelo gestor, com cadeia de aprovação configurável, prazos e escalonamento.
Aprovados, materializam tratamento ou afastamento; nunca alteram marcação diretamente.

Regra de negócio implementada na fase F10 (agente A1, ownership deste
arquivo -- ver `docs/fases/F10-workflows-aprovacoes-fechamento.md`, seção
5). A regra em si vive em `app.workflow.solicitacoes.tipos`/`servico`
(que também publicam `ajuste.solicitado`); este módulo só traduz
HTTP <-> serviço, mesmo padrão de `app/routers/tratamentos.py` (F4).

Autenticação dupla (retrofit de 2026-08-08, decisão do dono do produto): o
contrato já declarava os três esquemas alternativos por operação
(`bearerAuth`/`oauth2`/`apiKeyAuth`), mas só sessão humana era aceita até
agora. `Depends(exigir_permissao(...))` trocado por
`Depends(exigir_permissao_ou_escopo(...))` (mesmo combinador já provado em
`app/routers/empresas.py`/`webhooks.py`) -- sessão humana É tentada primeiro
(comportamento humano preservado byte a byte), cliente de integração (OAuth/
API key) só entra quando não há sessão humana autenticada. Note que o filtro
`minhas` de `listarSolicitacoes` é um no-op para cliente de integração: o
serviço só o aplica quando há `usuario_atual_id`, e um cliente não tem
usuário humano a quem atribuir "minhas".
"""

from __future__ import annotations

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Path, Query, Response

from app.comum.autenticacao_cliente import (
    ContextoAcesso,
    aplicar_limite_taxa_se_cliente,
    exigir_permissao_ou_escopo,
    usuario_id_do_acesso,
)
from app.comum.limitador_taxa import exigir_limite_taxa_sessao
from app.core.erros import RESPOSTAS_PADRAO
from app.db.sessao import SessaoDb
from app.schemas import contrato
from app.workflow.solicitacoes import servico, tipos
from app.workflow.solicitacoes.servico import listar_aprovacoes_da_solicitacao

roteador = APIRouter(tags=["solicitacoes"])

# Uma instancia por par (permissao, escopo) unico deste arquivo -- nunca
# `exigir_permissao_ou_escopo(...)` chamado de novo dentro de um handler
# (identidade estavel do *callable* pro cache de dependencia do FastAPI).
_ACESSO_LER = exigir_permissao_ou_escopo(permissao="solicitacoes.ler", escopo="solicitacoes:ler")
_ACESSO_CRIAR = exigir_permissao_ou_escopo(
    permissao="solicitacoes.criar", escopo="solicitacoes:escrever"
)
_ACESSO_EDITAR = exigir_permissao_ou_escopo(
    permissao="solicitacoes.editar", escopo="solicitacoes:escrever"
)
_ACESSO_TIPOS_LER = exigir_permissao_ou_escopo(
    permissao="tipos_solicitacao.ler", escopo="solicitacoes:ler"
)
_ACESSO_TIPOS_CRIAR = exigir_permissao_ou_escopo(
    permissao="tipos_solicitacao.criar", escopo="solicitacoes:escrever"
)


@roteador.get(
    "/v1/solicitacoes",
    status_code=200,
    operation_id="listarSolicitacoes",
    summary="Listar solicitacoes",
    responses=RESPOSTAS_PADRAO,
)
async def listar_solicitacoes(
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_LER)],
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
    await aplicar_limite_taxa_se_cliente(response, acesso)
    linhas, paginacao = await servico.listar_solicitacoes(
        sessao,
        acesso.tenant_id,
        colaborador_id=colaborador_id,
        empresa_id=empresa_id,
        tipo_solicitacao_id=tipo_solicitacao_id,
        categoria=categoria,
        status=status,
        minhas=minhas,
        usuario_atual_id=usuario_id_do_acesso(acesso),
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
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_CRIAR)],
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
) -> contrato.Solicitacao:
    """Criar solicitacao"""
    await aplicar_limite_taxa_se_cliente(response, acesso)
    nova = await servico.criar_solicitacao(
        sessao, acesso.tenant_id, corpo, usuario_id=usuario_id_do_acesso(acesso)
    )
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
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_LER)],
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
) -> contrato.Solicitacao:
    """Obter solicitacao

    Devolve o historico completo das etapas (`aprovacoes`), conforme a
    descricao da operacao no contrato -- prova de quem autorizou cada
    correcao de jornada.
    """
    await aplicar_limite_taxa_se_cliente(response, acesso)
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
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_EDITAR)],
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
) -> contrato.Solicitacao:
    """Cancelar solicitacao"""
    await aplicar_limite_taxa_se_cliente(response, acesso)
    cancelada = await servico.cancelar_solicitacao(
        sessao, acesso.tenant_id, solicitacao_id, corpo, usuario_id=usuario_id_do_acesso(acesso)
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
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_TIPOS_LER)],
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
    categoria: Annotated[
        str | None, Query(alias="categoria", description="Filtra pela categoria.")
    ] = None,
    ativo: Annotated[
        bool | None, Query(alias="ativo", description="Filtra por tipos ativos.")
    ] = None,
) -> contrato.ListaTipoSolicitacao:
    """Listar tipos de solicitacao"""
    await aplicar_limite_taxa_se_cliente(response, acesso)
    linhas, paginacao = await tipos.listar_tipos_solicitacao(
        sessao,
        acesso.tenant_id,
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
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_TIPOS_CRIAR)],
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
) -> contrato.TipoSolicitacao:
    """Criar tipo de solicitacao"""
    await aplicar_limite_taxa_se_cliente(response, acesso)
    novo = await tipos.criar_tipo_solicitacao(
        sessao, acesso.tenant_id, corpo, usuario_id=usuario_id_do_acesso(acesso)
    )
    return tipos.tipo_para_schema(novo)
