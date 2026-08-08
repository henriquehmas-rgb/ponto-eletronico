"""Rotas da tag `afastamentos` do contrato.

Tipos e periodos de ausencia legitima.
O afastamento entra na apuracao como insumo, NUNCA como marcacao, e e exportado no bloco de ausencias do AEJ.

Regra de negocio implementada na fase F3 (agente A2, ownership deste arquivo --
ver `docs/fases/F03-motor-de-jornada.md`, secao 5). A regra em si vive em
`app.jornada.calendario.afastamentos`; este modulo so traduz HTTP <-> servico.

Autenticacao dupla (retrofit de 2026-08-08, decisao do dono do produto): o
contrato ja declarava os tres esquemas alternativos por operacao
(`bearerAuth`/`oauth2`/`apiKeyAuth`), mas so sessao humana era aceita ate
agora. `Depends(exigir_permissao(...))` trocado por
`Depends(exigir_permissao_ou_escopo(...))` (mesmo combinador ja provado em
`app/routers/empresas.py`/`webhooks.py`) -- sessao humana E' tentada primeiro
(comportamento humano preservado byte a byte), cliente de integracao (OAuth/
API key) so entra quando nao ha sessao humana autenticada.
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
)
from app.comum.limitador_taxa import exigir_limite_taxa_sessao
from app.core.erros import RESPOSTAS_PADRAO
from app.db.sessao import SessaoDb
from app.jornada.calendario import afastamentos as servico
from app.schemas import contrato

roteador = APIRouter(tags=["afastamentos"])

# Uma instancia por par (permissao, escopo) unico deste arquivo -- nunca
# `exigir_permissao_ou_escopo(...)` chamado de novo dentro de um handler
# (identidade estavel do *callable* pro cache de dependencia do FastAPI).
_ACESSO_TIPOS_LER = exigir_permissao_ou_escopo(
    permissao="tipos_afastamento.ler", escopo="jornadas:ler"
)
_ACESSO_TIPOS_CRIAR = exigir_permissao_ou_escopo(
    permissao="tipos_afastamento.criar", escopo="jornadas:escrever"
)
_ACESSO_TIPOS_EDITAR = exigir_permissao_ou_escopo(
    permissao="tipos_afastamento.editar", escopo="jornadas:escrever"
)
_ACESSO_LER = exigir_permissao_ou_escopo(permissao="afastamentos.ler", escopo="jornadas:ler")
_ACESSO_CRIAR = exigir_permissao_ou_escopo(
    permissao="afastamentos.criar", escopo="jornadas:escrever"
)
_ACESSO_EDITAR = exigir_permissao_ou_escopo(
    permissao="afastamentos.editar", escopo="jornadas:escrever"
)
_ACESSO_EXCLUIR = exigir_permissao_ou_escopo(
    permissao="afastamentos.excluir", escopo="jornadas:escrever"
)


@roteador.get(
    "/v1/tipos-afastamento",
    status_code=200,
    operation_id="listarTiposAfastamento",
    summary="Listar tipos de afastamento",
    responses=RESPOSTAS_PADRAO,
)
async def listar_tipos_afastamento(
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
        str | None, Query(alias="categoria", description="Filtra pela categoria legal.")
    ] = None,
    ativo: Annotated[
        bool | None, Query(alias="ativo", description="Filtra por tipos ativos.")
    ] = None,
) -> contrato.ListaTipoAfastamento:
    """Listar tipos de afastamento"""
    await aplicar_limite_taxa_se_cliente(response, acesso)
    linhas, paginacao = await servico.listar_tipos_afastamento(
        sessao,
        acesso.tenant_id,
        categoria=categoria,
        ativo=ativo,
        cursor=cursor,
        limite=limite,
        ordenar=ordenar,
    )
    dados = [
        contrato.TipoAfastamento.model_validate(linha, from_attributes=True) for linha in linhas
    ]
    return contrato.ListaTipoAfastamento(dados=dados, paginacao=paginacao)


@roteador.post(
    "/v1/tipos-afastamento",
    status_code=201,
    operation_id="criarTipoAfastamento",
    summary="Criar tipo de afastamento",
    responses=RESPOSTAS_PADRAO,
    dependencies=[Depends(exigir_limite_taxa_sessao())],
)
async def criar_tipo_afastamento(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    corpo: contrato.TipoAfastamentoCriar,
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
) -> contrato.TipoAfastamento:
    """Criar tipo de afastamento"""
    await aplicar_limite_taxa_se_cliente(response, acesso)
    novo = await servico.criar_tipo_afastamento(sessao, acesso.tenant_id, corpo)
    return contrato.TipoAfastamento.model_validate(novo, from_attributes=True)


@roteador.patch(
    "/v1/tipos-afastamento/{tipoId}",
    status_code=200,
    operation_id="atualizarTipoAfastamento",
    summary="Atualizar tipo de afastamento",
    responses=RESPOSTAS_PADRAO,
    dependencies=[Depends(exigir_limite_taxa_sessao())],
)
async def atualizar_tipo_afastamento(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    tipo_id: Annotated[UUID, Path(alias="tipoId", description="Identificador do tipo.")],
    corpo: contrato.TipoAfastamentoAtualizar,
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_TIPOS_EDITAR)],
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
) -> contrato.TipoAfastamento:
    """Atualizar tipo de afastamento"""
    await aplicar_limite_taxa_se_cliente(response, acesso)
    atualizado = await servico.atualizar_tipo_afastamento(sessao, acesso.tenant_id, tipo_id, corpo)
    return contrato.TipoAfastamento.model_validate(atualizado, from_attributes=True)


@roteador.get(
    "/v1/afastamentos",
    status_code=200,
    operation_id="listarAfastamentos",
    summary="Listar afastamentos",
    responses=RESPOSTAS_PADRAO,
)
async def listar_afastamentos(
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
        Query(alias="colaboradorId", description="Filtra pelos afastamentos de um colaborador."),
    ] = None,
    vinculo_id: Annotated[
        UUID | None,
        Query(alias="vinculoId", description="Filtra pelos afastamentos de um vinculo."),
    ] = None,
    empresa_id: Annotated[
        UUID | None,
        Query(alias="empresaId", description="Filtra pelos afastamentos de uma empresa."),
    ] = None,
    tipo_afastamento_id: Annotated[
        UUID | None,
        Query(alias="tipoAfastamentoId", description="Filtra pelo tipo de afastamento."),
    ] = None,
    status: Annotated[
        str | None, Query(alias="status", description="Filtra pela situacao.")
    ] = None,
    de: Annotated[
        date | None, Query(alias="de", description="Afastamentos que alcancam esta data ou depois.")
    ] = None,
    ate: Annotated[
        date | None, Query(alias="ate", description="Afastamentos que alcancam esta data ou antes.")
    ] = None,
) -> contrato.ListaAfastamento:
    """Listar afastamentos"""
    await aplicar_limite_taxa_se_cliente(response, acesso)
    linhas, paginacao = await servico.listar_afastamentos(
        sessao,
        acesso.tenant_id,
        colaborador_id=colaborador_id,
        vinculo_id=vinculo_id,
        empresa_id=empresa_id,
        tipo_afastamento_id=tipo_afastamento_id,
        status=status,
        de=de,
        ate=ate,
        cursor=cursor,
        limite=limite,
        ordenar=ordenar,
    )
    dados = [contrato.Afastamento.model_validate(linha, from_attributes=True) for linha in linhas]
    return contrato.ListaAfastamento(dados=dados, paginacao=paginacao)


@roteador.post(
    "/v1/afastamentos",
    status_code=201,
    operation_id="criarAfastamento",
    summary="Criar afastamento",
    responses=RESPOSTAS_PADRAO,
    dependencies=[Depends(exigir_limite_taxa_sessao())],
)
async def criar_afastamento(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    corpo: contrato.AfastamentoCriar,
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
) -> contrato.Afastamento:
    """Criar afastamento"""
    await aplicar_limite_taxa_se_cliente(response, acesso)
    novo = await servico.criar_afastamento(sessao, acesso.tenant_id, corpo)
    return contrato.Afastamento.model_validate(novo, from_attributes=True)


@roteador.get(
    "/v1/afastamentos/{afastamentoId}",
    status_code=200,
    operation_id="obterAfastamento",
    summary="Obter afastamento",
    responses=RESPOSTAS_PADRAO,
)
async def obter_afastamento(
    afastamento_id: Annotated[
        UUID, Path(alias="afastamentoId", description="Identificador do afastamento.")
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
) -> contrato.Afastamento:
    """Obter afastamento"""
    await aplicar_limite_taxa_se_cliente(response, acesso)
    encontrado = await servico.obter_afastamento(sessao, acesso.tenant_id, afastamento_id)
    return contrato.Afastamento.model_validate(encontrado, from_attributes=True)


@roteador.patch(
    "/v1/afastamentos/{afastamentoId}",
    status_code=200,
    operation_id="atualizarAfastamento",
    summary="Atualizar afastamento",
    responses=RESPOSTAS_PADRAO,
    dependencies=[Depends(exigir_limite_taxa_sessao())],
)
async def atualizar_afastamento(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    afastamento_id: Annotated[
        UUID, Path(alias="afastamentoId", description="Identificador do afastamento.")
    ],
    corpo: contrato.AfastamentoAtualizar,
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
) -> contrato.Afastamento:
    """Atualizar afastamento"""
    await aplicar_limite_taxa_se_cliente(response, acesso)
    atualizado = await servico.atualizar_afastamento(
        sessao, acesso.tenant_id, afastamento_id, corpo
    )
    return contrato.Afastamento.model_validate(atualizado, from_attributes=True)


@roteador.delete(
    "/v1/afastamentos/{afastamentoId}",
    status_code=204,
    operation_id="excluirAfastamento",
    summary="Excluir afastamento",
    responses=RESPOSTAS_PADRAO,
    response_class=Response,
    dependencies=[Depends(exigir_limite_taxa_sessao())],
)
async def excluir_afastamento(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    afastamento_id: Annotated[
        UUID, Path(alias="afastamentoId", description="Identificador do afastamento.")
    ],
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_EXCLUIR)],
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
    """Excluir afastamento"""
    await aplicar_limite_taxa_se_cliente(response, acesso)
    await servico.excluir_afastamento(sessao, acesso.tenant_id, afastamento_id)
    # Reaproveita o `response` injetado (ja carrega os cabecalhos `RateLimit-*`
    # setados acima, quando o acesso e de cliente de integracao) em vez de
    # construir um `Response` novo, que perderia esses cabecalhos.
    response.status_code = 204
    return response
