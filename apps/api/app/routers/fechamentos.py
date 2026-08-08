"""Rotas da tag `fechamentos` do contrato (T5/T6, F10/A2).

Períodos de apuração, conferência prévia, trava do período e reabertura.
Fechado, o dia não recalcula; a reabertura é sempre nominal e justificada.

Regra de negócio implementada na fase F10 (agente A2, ownership deste
arquivo -- ver `docs/fases/F10-workflows-aprovacoes-fechamento.md`, seção
5). A regra em si vive em `app.workflow.fechamento.periodos`/`servico`/
`conferencia`; este módulo só traduz HTTP <-> serviço, mesmo padrão de
`app/routers/tratamentos.py` (F4).

Autenticacao dupla (retrofit de 2026-08-08, decisao do dono do produto --
ver `docs/backlog.md` e a docstring de `app.comum.autenticacao_cliente`): o
contrato ja declarava os tres esquemas alternativos por operacao
(`bearerAuth`/`oauth2`/`apiKeyAuth`), mas so sessao humana era aceita ate
agora. `Depends(exigir_permissao(...))` trocado por
`Depends(exigir_permissao_ou_escopo(...))` -- sessao humana E' tentada
primeiro (comportamento humano preservado byte a byte), cliente de
integracao (OAuth/API key) so entra quando nao ha sessao humana autenticada.
"""

from __future__ import annotations

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
from app.core.config import obter_configuracao
from app.core.erros import RESPOSTAS_PADRAO
from app.db.sessao import SessaoDb
from app.schemas import contrato
from app.workflow.fechamento import conferencia, periodos, servico

roteador = APIRouter(tags=["fechamentos"])

# Uma instancia por par (permissao, escopo) unico do arquivo, criada no nivel
# de modulo (nunca chamada de novo dentro do handler): identidade estavel do
# *callable* pro cache de dependencia do FastAPI, mesmo motivo documentado em
# `app.comum.limitador_taxa`.
_ACESSO_PERIODOS_LER = exigir_permissao_ou_escopo(
    permissao="periodos.ler", escopo="fechamentos:ler"
)
_ACESSO_PERIODOS_CRIAR = exigir_permissao_ou_escopo(
    permissao="periodos.criar", escopo="fechamentos:escrever"
)
_ACESSO_LER = exigir_permissao_ou_escopo(permissao="fechamentos.ler", escopo="fechamentos:ler")
_ACESSO_CRIAR = exigir_permissao_ou_escopo(
    permissao="fechamentos.criar", escopo="fechamentos:escrever"
)
_ACESSO_CONFERIR = exigir_permissao_ou_escopo(
    permissao="fechamentos.executar", escopo="fechamentos:escrever"
)
_ACESSO_REABRIR = exigir_permissao_ou_escopo(
    permissao="fechamentos.reabrir", escopo="fechamentos:escrever"
)


@roteador.get(
    "/v1/periodos",
    status_code=200,
    operation_id="listarPeriodos",
    summary="Listar periodos",
    responses=RESPOSTAS_PADRAO,
)
async def listar_periodos(
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_PERIODOS_LER)],
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
        UUID | None, Query(alias="empresaId", description="Filtra pelos periodos de uma empresa.")
    ] = None,
    tipo: Annotated[str | None, Query(alias="tipo", description="Filtra pelo tipo.")] = None,
    status: Annotated[
        str | None, Query(alias="status", description="Filtra pela situacao.")
    ] = None,
    competencia_folha: Annotated[
        str | None,
        Query(
            alias="competenciaFolha",
            description="Filtra pela competencia de folha, no formato AAAA-MM.",
        ),
    ] = None,
) -> contrato.ListaPeriodo:
    """Listar periodos"""
    await aplicar_limite_taxa_se_cliente(response, acesso)
    linhas, paginacao = await periodos.listar_periodos(
        sessao,
        acesso.tenant_id,
        empresa_id=empresa_id,
        tipo=tipo,
        status=status,
        competencia_folha=competencia_folha,
        cursor=cursor,
        limite=limite,
        ordenar=ordenar,
    )
    dados = [contrato.Periodo.model_validate(linha, from_attributes=True) for linha in linhas]
    return contrato.ListaPeriodo(dados=dados, paginacao=paginacao)


@roteador.post(
    "/v1/periodos",
    status_code=201,
    operation_id="criarPeriodo",
    summary="Criar periodo",
    responses=RESPOSTAS_PADRAO,
    dependencies=[Depends(exigir_limite_taxa_sessao())],
)
async def criar_periodo(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    corpo: contrato.PeriodoCriar,
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_PERIODOS_CRIAR)],
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
) -> contrato.Periodo:
    """Criar periodo"""
    await aplicar_limite_taxa_se_cliente(response, acesso)
    novo = await periodos.criar_periodo(
        sessao, acesso.tenant_id, corpo, usuario_id=usuario_id_do_acesso(acesso)
    )
    return contrato.Periodo.model_validate(novo, from_attributes=True)


@roteador.post(
    "/v1/fechamentos",
    status_code=202,
    operation_id="criarFechamento",
    summary="Fechar periodo",
    responses=RESPOSTAS_PADRAO,
    dependencies=[Depends(exigir_limite_taxa_sessao())],
)
async def criar_fechamento(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    corpo: contrato.FechamentoCriar,
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
) -> contrato.ProcessamentoAssincrono:
    """Fechar periodo"""
    await aplicar_limite_taxa_se_cliente(response, acesso)
    config = obter_configuracao()
    return await servico.criar_fechamento(
        sessao,
        acesso.tenant_id,
        corpo,
        usuario_id=usuario_id_do_acesso(acesso),
        redis_url=config.redis_url,
    )


@roteador.get(
    "/v1/fechamentos",
    status_code=200,
    operation_id="listarFechamentos",
    summary="Listar fechamentos",
    responses=RESPOSTAS_PADRAO,
)
async def listar_fechamentos(
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
    periodo_id: Annotated[
        UUID | None, Query(alias="periodoId", description="Filtra pelos fechamentos de um periodo.")
    ] = None,
    empresa_id: Annotated[
        UUID | None,
        Query(alias="empresaId", description="Filtra pelos fechamentos de uma empresa."),
    ] = None,
    unidade_id: Annotated[
        UUID | None,
        Query(alias="unidadeId", description="Filtra pelos fechamentos de uma unidade."),
    ] = None,
    escopo: Annotated[
        str | None, Query(alias="escopo", description="Filtra pela abrangencia.")
    ] = None,
    status: Annotated[
        str | None, Query(alias="status", description="Filtra pela situacao.")
    ] = None,
) -> contrato.ListaFechamento:
    """Listar fechamentos"""
    await aplicar_limite_taxa_se_cliente(response, acesso)
    linhas, paginacao = await servico.listar_fechamentos(
        sessao,
        acesso.tenant_id,
        periodo_id=periodo_id,
        empresa_id=empresa_id,
        unidade_id=unidade_id,
        escopo=escopo,
        status=status,
        cursor=cursor,
        limite=limite,
        ordenar=ordenar,
    )
    dados = [contrato.Fechamento.model_validate(linha, from_attributes=True) for linha in linhas]
    return contrato.ListaFechamento(dados=dados, paginacao=paginacao)


@roteador.get(
    "/v1/fechamentos/{fechamentoId}",
    status_code=200,
    operation_id="obterFechamento",
    summary="Obter fechamento",
    responses=RESPOSTAS_PADRAO,
)
async def obter_fechamento(
    fechamento_id: Annotated[
        UUID, Path(alias="fechamentoId", description="Identificador do fechamento.")
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
) -> contrato.Fechamento:
    """Obter fechamento"""
    await aplicar_limite_taxa_se_cliente(response, acesso)
    encontrado = await servico.obter_fechamento(sessao, acesso.tenant_id, fechamento_id)
    return contrato.Fechamento.model_validate(encontrado, from_attributes=True)


@roteador.post(
    "/v1/fechamentos/{fechamentoId}/conferir",
    status_code=200,
    operation_id="conferirFechamento",
    summary="Conferir periodo antes de fechar",
    responses=RESPOSTAS_PADRAO,
    dependencies=[Depends(exigir_limite_taxa_sessao())],
)
async def conferir_fechamento(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    fechamento_id: Annotated[
        UUID, Path(alias="fechamentoId", description="Identificador do fechamento.")
    ],
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_CONFERIR)],
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
) -> contrato.ConferenciaResposta:
    """Conferir periodo antes de fechar"""
    await aplicar_limite_taxa_se_cliente(response, acesso)
    return await conferencia.conferir_fechamento(
        sessao, acesso.tenant_id, fechamento_id, usuario_id=usuario_id_do_acesso(acesso)
    )


@roteador.post(
    "/v1/fechamentos/{fechamentoId}/reabrir",
    status_code=200,
    operation_id="reabrirFechamento",
    summary="Reabrir periodo fechado",
    responses=RESPOSTAS_PADRAO,
    dependencies=[Depends(exigir_limite_taxa_sessao())],
)
async def reabrir_fechamento(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    fechamento_id: Annotated[
        UUID, Path(alias="fechamentoId", description="Identificador do fechamento.")
    ],
    corpo: contrato.ReaberturaRequisicao,
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_REABRIR)],
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
) -> contrato.Fechamento:
    """Reabrir periodo fechado"""
    await aplicar_limite_taxa_se_cliente(response, acesso)
    reaberto = await servico.reabrir_fechamento(
        sessao, acesso.tenant_id, fechamento_id, corpo, usuario_id=usuario_id_do_acesso(acesso)
    )
    return contrato.Fechamento.model_validate(reaberto, from_attributes=True)
