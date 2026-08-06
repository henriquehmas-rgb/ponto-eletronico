"""Rotas da tag `tratamentos` do contrato.

Camada de correcao da jornada, e a UNICA que existe.
Inclusao manual de horario, desconsideracao de batida duplicada, ajuste de intervalo, abono e justificativa vivem aqui, sempre com autor, data, motivo e anexo, e nunca modificam a marcacao original.

Regra de negocio implementada na fase F4 (agente A3, ownership deste arquivo --
ver `docs/fases/F04-calculo-banco-de-horas.md`, secao 5). A regra em si vive em
`app.apuracao.tratamento.servico`/`decisao` (que tambem publicam
`ajuste.aprovado`/`ajuste.reprovado`/`apuracao.recalculada`); este modulo so
traduz HTTP <-> servico.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Path, Query, Response

from app.apuracao.tratamento import decisao, servico
from app.comum.limitador_taxa import exigir_limite_taxa_sessao
from app.core.erros import RESPOSTAS_PADRAO
from app.core.seguranca import Sujeito, exigir_permissao, tenant_id_ou_erro
from app.db.sessao import SessaoDb
from app.schemas import contrato

roteador = APIRouter(tags=["tratamentos"])


@roteador.post(
    "/v1/tratamentos",
    status_code=201,
    operation_id="criarTratamento",
    summary="Criar tratamento",
    responses=RESPOSTAS_PADRAO,
    dependencies=[Depends(exigir_limite_taxa_sessao())],
)
async def criar_tratamento(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    corpo: contrato.TratamentoCriar,
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("tratamentos.criar"))],
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
) -> contrato.Tratamento:
    """Criar tratamento"""
    tenant_id = tenant_id_ou_erro(sujeito)
    novo = await servico.criar_tratamento(sessao, tenant_id, corpo, usuario_id=sujeito.usuario_id)
    return contrato.Tratamento.model_validate(novo, from_attributes=True)


@roteador.get(
    "/v1/tratamentos",
    status_code=200,
    operation_id="listarTratamentos",
    summary="Listar tratamentos",
    responses=RESPOSTAS_PADRAO,
)
async def listar_tratamentos(
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("tratamentos.ler"))],
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
        Query(alias="colaboradorId", description="Filtra pelos tratamentos de um colaborador."),
    ] = None,
    vinculo_id: Annotated[
        UUID | None, Query(alias="vinculoId", description="Filtra pelos tratamentos de um vinculo.")
    ] = None,
    empresa_id: Annotated[
        UUID | None,
        Query(alias="empresaId", description="Filtra pelos tratamentos de uma empresa."),
    ] = None,
    tipo_tratamento_id: Annotated[
        UUID | None, Query(alias="tipoTratamentoId", description="Filtra pelo tipo de tratamento.")
    ] = None,
    status: Annotated[
        str | None, Query(alias="status", description="Filtra pela situacao.")
    ] = None,
    origem: Annotated[str | None, Query(alias="origem", description="Filtra pela origem.")] = None,
    de: Annotated[
        date | None, Query(alias="de", description="Data de referencia a partir de.")
    ] = None,
    ate: Annotated[date | None, Query(alias="ate", description="Data de referencia ate.")] = None,
    marcacao_id: Annotated[
        UUID | None,
        Query(
            alias="marcacaoId", description="Lista os tratamentos que se referem a uma marcacao."
        ),
    ] = None,
) -> contrato.ListaTratamento:
    """Listar tratamentos"""
    tenant_id = tenant_id_ou_erro(sujeito)
    linhas, paginacao = await servico.listar_tratamentos(
        sessao,
        tenant_id,
        colaborador_id=colaborador_id,
        vinculo_id=vinculo_id,
        empresa_id=empresa_id,
        tipo_tratamento_id=tipo_tratamento_id,
        status=status,
        origem=origem,
        de=de,
        ate=ate,
        marcacao_id=marcacao_id,
        cursor=cursor,
        limite=limite,
        ordenar=ordenar,
    )
    dados = [contrato.Tratamento.model_validate(linha, from_attributes=True) for linha in linhas]
    return contrato.ListaTratamento(dados=dados, paginacao=paginacao)


@roteador.get(
    "/v1/tratamentos/{tratamentoId}",
    status_code=200,
    operation_id="obterTratamento",
    summary="Obter tratamento",
    responses=RESPOSTAS_PADRAO,
)
async def obter_tratamento(
    tratamento_id: Annotated[
        UUID, Path(alias="tratamentoId", description="Identificador do tratamento.")
    ],
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("tratamentos.ler"))],
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
) -> contrato.Tratamento:
    """Obter tratamento"""
    tenant_id_ou_erro(sujeito)
    encontrado = await servico.obter_tratamento(sessao, tratamento_id)
    return contrato.Tratamento.model_validate(encontrado, from_attributes=True)


@roteador.patch(
    "/v1/tratamentos/{tratamentoId}",
    status_code=200,
    operation_id="atualizarTratamento",
    summary="Atualizar tratamento",
    responses=RESPOSTAS_PADRAO,
    dependencies=[Depends(exigir_limite_taxa_sessao())],
)
async def atualizar_tratamento(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    tratamento_id: Annotated[
        UUID, Path(alias="tratamentoId", description="Identificador do tratamento.")
    ],
    corpo: contrato.TratamentoAtualizar,
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("tratamentos.editar"))],
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
) -> contrato.Tratamento:
    """Atualizar tratamento"""
    tenant_id = tenant_id_ou_erro(sujeito)
    atualizado = await servico.atualizar_tratamento(
        sessao, tenant_id, tratamento_id, corpo, usuario_id=sujeito.usuario_id
    )
    return contrato.Tratamento.model_validate(atualizado, from_attributes=True)


@roteador.delete(
    "/v1/tratamentos/{tratamentoId}",
    status_code=204,
    operation_id="cancelarTratamento",
    summary="Cancelar tratamento",
    responses=RESPOSTAS_PADRAO,
    response_class=Response,
    dependencies=[Depends(exigir_limite_taxa_sessao())],
)
async def cancelar_tratamento(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    tratamento_id: Annotated[
        UUID, Path(alias="tratamentoId", description="Identificador do tratamento.")
    ],
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("tratamentos.excluir"))],
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
    """Cancelar tratamento"""
    tenant_id = tenant_id_ou_erro(sujeito)
    await servico.cancelar_tratamento(
        sessao, tenant_id, tratamento_id, usuario_id=sujeito.usuario_id
    )
    return Response(status_code=204)


@roteador.post(
    "/v1/tratamentos/{tratamentoId}/decidir",
    status_code=200,
    operation_id="decidirTratamento",
    summary="Aprovar ou reprovar tratamento",
    responses=RESPOSTAS_PADRAO,
    dependencies=[Depends(exigir_limite_taxa_sessao())],
)
async def decidir_tratamento(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    tratamento_id: Annotated[
        UUID, Path(alias="tratamentoId", description="Identificador do tratamento.")
    ],
    corpo: contrato.DecisaoRequisicao,
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("tratamentos.aprovar"))],
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
) -> contrato.Tratamento:
    """Aprovar ou reprovar tratamento"""
    tenant_id = tenant_id_ou_erro(sujeito)
    decidido = await decisao.decidir_tratamento(
        sessao, tenant_id, tratamento_id, corpo, usuario_id=sujeito.usuario_id
    )
    return contrato.Tratamento.model_validate(decidido, from_attributes=True)


@roteador.get(
    "/v1/tipos-tratamento",
    status_code=200,
    operation_id="listarTiposTratamento",
    summary="Listar tipos de tratamento",
    responses=RESPOSTAS_PADRAO,
)
async def listar_tipos_tratamento(
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("tipos_tratamento.ler"))],
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
) -> contrato.ListaTipoTratamento:
    """Listar tipos de tratamento"""
    tenant_id = tenant_id_ou_erro(sujeito)
    linhas, paginacao = await servico.listar_tipos_tratamento(
        sessao,
        tenant_id,
        categoria=categoria,
        ativo=ativo,
        cursor=cursor,
        limite=limite,
        ordenar=ordenar,
    )
    dados = [
        contrato.TipoTratamento.model_validate(linha, from_attributes=True) for linha in linhas
    ]
    return contrato.ListaTipoTratamento(dados=dados, paginacao=paginacao)
