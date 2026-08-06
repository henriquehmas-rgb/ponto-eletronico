"""Rotas da tag `organizacao` do contrato.

Estrutura interna da empresa: departamentos, centros de custo, cargos e equipes.
Sustenta escopo de perfil, agrupamento de relatorio e roteamento de aprovacao.

Implementado na Fase F2 (agente A1). Regra de negocio em `app/organizacao/estrutura.py`.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Path, Query, Response

from app.comum.limitador_taxa import exigir_limite_taxa_sessao
from app.core.erros import RESPOSTAS_PADRAO
from app.core.seguranca import Sujeito, exigir_permissao, tenant_id_ou_erro
from app.db.sessao import SessaoDb
from app.organizacao import estrutura as servico
from app.organizacao.paginacao import paginar, resolver_pedido
from app.schemas import contrato

roteador = APIRouter(tags=["organizacao"])

_ORDENACAO_PADRAO = "criado_em:desc"


# --------------------------------------------------------------------------
# Departamentos
# --------------------------------------------------------------------------


@roteador.get(
    "/v1/departamentos",
    status_code=200,
    operation_id="listarDepartamentos",
    summary="Listar departamentos",
    responses=RESPOSTAS_PADRAO,
)
async def listar_departamentos(
    sessao: SessaoDb,
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("departamentos.ler"))],
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
        UUID | None,
        Query(alias="empresaId", description="Filtra pelos departamentos de uma empresa."),
    ] = None,
    departamento_pai_id: Annotated[
        UUID | None,
        Query(alias="departamentoPaiId", description="Lista os filhos diretos de um departamento."),
    ] = None,
    raiz: Annotated[
        bool | None,
        Query(
            alias="raiz", description="Quando verdadeiro, lista apenas os departamentos sem pai."
        ),
    ] = None,
    ativo: Annotated[
        bool | None, Query(alias="ativo", description="Filtra por departamentos ativos.")
    ] = None,
    busca: Annotated[
        str | None,
        Query(
            alias="busca", description="Busca textual livre sobre os campos indexados do recurso."
        ),
    ] = None,
) -> contrato.ListaDepartamento:
    """Listar departamentos"""
    tenant_id = tenant_id_ou_erro(sujeito)
    pedido = resolver_pedido(
        cursor=cursor, limite=limite, ordenar=ordenar, ordenacao_padrao=_ORDENACAO_PADRAO
    )
    linhas = await servico.listar_departamentos(
        sessao,
        tenant_id=tenant_id,
        pedido=pedido,
        empresa_id=empresa_id,
        departamento_pai_id=departamento_pai_id,
        raiz=raiz,
        ativo=ativo,
        busca=busca,
    )
    dados, paginacao = paginar(pedido=pedido, linhas=linhas)
    return contrato.ListaDepartamento(
        dados=[
            contrato.Departamento.model_validate(linha, from_attributes=True) for linha in dados
        ],
        paginacao=contrato.Paginacao.model_validate(paginacao),
    )


@roteador.post(
    "/v1/departamentos",
    status_code=201,
    operation_id="criarDepartamento",
    summary="Criar departamento",
    responses=RESPOSTAS_PADRAO,
    dependencies=[Depends(exigir_limite_taxa_sessao())],
)
async def criar_departamento(
    sessao: SessaoDb,
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("departamentos.criar"))],
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    corpo: contrato.DepartamentoCriar,
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
) -> contrato.Departamento:
    """Criar departamento"""
    tenant_id = tenant_id_ou_erro(sujeito)
    departamento = await servico.criar_departamento(
        sessao,
        tenant_id=tenant_id,
        usuario_id=sujeito.usuario_id,
        empresa_id=corpo.empresa_id,
        codigo=corpo.codigo,
        nome=corpo.nome,
        departamento_pai_id=corpo.departamento_pai_id,
        responsavel_colaborador_id=corpo.responsavel_colaborador_id,
        descricao=corpo.descricao,
        ativo=corpo.ativo,
    )
    return contrato.Departamento.model_validate(departamento, from_attributes=True)


@roteador.get(
    "/v1/departamentos/{departamentoId}",
    status_code=200,
    operation_id="obterDepartamento",
    summary="Obter departamento",
    responses=RESPOSTAS_PADRAO,
)
async def obter_departamento(
    sessao: SessaoDb,
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("departamentos.ler"))],
    departamento_id: Annotated[
        UUID, Path(alias="departamentoId", description="Identificador do departamento.")
    ],
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
) -> contrato.Departamento:
    """Obter departamento"""
    tenant_id = tenant_id_ou_erro(sujeito)
    departamento = await servico.obter_departamento(
        sessao, tenant_id=tenant_id, departamento_id=departamento_id
    )
    return contrato.Departamento.model_validate(departamento, from_attributes=True)


@roteador.patch(
    "/v1/departamentos/{departamentoId}",
    status_code=200,
    operation_id="atualizarDepartamento",
    summary="Atualizar departamento",
    responses=RESPOSTAS_PADRAO,
    dependencies=[Depends(exigir_limite_taxa_sessao())],
)
async def atualizar_departamento(
    sessao: SessaoDb,
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("departamentos.editar"))],
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    departamento_id: Annotated[
        UUID, Path(alias="departamentoId", description="Identificador do departamento.")
    ],
    corpo: contrato.DepartamentoAtualizar,
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
) -> contrato.Departamento:
    """Atualizar departamento"""
    tenant_id = tenant_id_ou_erro(sujeito)
    dados = corpo.model_dump(exclude_unset=True)
    departamento = await servico.atualizar_departamento(
        sessao,
        tenant_id=tenant_id,
        departamento_id=departamento_id,
        usuario_id=sujeito.usuario_id,
        dados=dados,
    )
    return contrato.Departamento.model_validate(departamento, from_attributes=True)


@roteador.delete(
    "/v1/departamentos/{departamentoId}",
    status_code=204,
    operation_id="excluirDepartamento",
    summary="Excluir departamento",
    responses=RESPOSTAS_PADRAO,
    response_class=Response,
    dependencies=[Depends(exigir_limite_taxa_sessao())],
)
async def excluir_departamento(
    sessao: SessaoDb,
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("departamentos.excluir"))],
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    departamento_id: Annotated[
        UUID, Path(alias="departamentoId", description="Identificador do departamento.")
    ],
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
    """Excluir departamento"""
    tenant_id = tenant_id_ou_erro(sujeito)
    await servico.excluir_departamento(
        sessao, tenant_id=tenant_id, departamento_id=departamento_id, usuario_id=sujeito.usuario_id
    )
    return Response(status_code=204)


# --------------------------------------------------------------------------
# Centros de custo
# --------------------------------------------------------------------------


@roteador.get(
    "/v1/centros-custo",
    status_code=200,
    operation_id="listarCentrosCusto",
    summary="Listar centros de custo",
    responses=RESPOSTAS_PADRAO,
)
async def listar_centros_custo(
    sessao: SessaoDb,
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("centros_custo.ler"))],
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
        UUID | None,
        Query(alias="empresaId", description="Filtra pelos centros de custo de uma empresa."),
    ] = None,
    centro_custo_pai_id: Annotated[
        UUID | None, Query(alias="centroCustoPaiId", description="Lista os filhos diretos.")
    ] = None,
    ativo: Annotated[
        bool | None, Query(alias="ativo", description="Filtra por centros de custo ativos.")
    ] = None,
    busca: Annotated[
        str | None,
        Query(
            alias="busca", description="Busca textual livre sobre os campos indexados do recurso."
        ),
    ] = None,
) -> contrato.ListaCentroCusto:
    """Listar centros de custo"""
    tenant_id = tenant_id_ou_erro(sujeito)
    pedido = resolver_pedido(
        cursor=cursor, limite=limite, ordenar=ordenar, ordenacao_padrao=_ORDENACAO_PADRAO
    )
    linhas = await servico.listar_centros_custo(
        sessao,
        tenant_id=tenant_id,
        pedido=pedido,
        empresa_id=empresa_id,
        centro_custo_pai_id=centro_custo_pai_id,
        ativo=ativo,
        busca=busca,
    )
    dados, paginacao = paginar(pedido=pedido, linhas=linhas)
    return contrato.ListaCentroCusto(
        dados=[contrato.CentroCusto.model_validate(linha, from_attributes=True) for linha in dados],
        paginacao=contrato.Paginacao.model_validate(paginacao),
    )


@roteador.post(
    "/v1/centros-custo",
    status_code=201,
    operation_id="criarCentroCusto",
    summary="Criar centro de custo",
    responses=RESPOSTAS_PADRAO,
    dependencies=[Depends(exigir_limite_taxa_sessao())],
)
async def criar_centro_custo(
    sessao: SessaoDb,
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("centros_custo.criar"))],
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    corpo: contrato.CentroCustoCriar,
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
) -> contrato.CentroCusto:
    """Criar centro de custo"""
    tenant_id = tenant_id_ou_erro(sujeito)
    centro = await servico.criar_centro_custo(
        sessao,
        tenant_id=tenant_id,
        usuario_id=sujeito.usuario_id,
        empresa_id=corpo.empresa_id,
        codigo=corpo.codigo,
        nome=corpo.nome,
        centro_custo_pai_id=corpo.centro_custo_pai_id,
        descricao=corpo.descricao,
        codigo_externo=corpo.codigo_externo,
        ativo=corpo.ativo,
    )
    return contrato.CentroCusto.model_validate(centro, from_attributes=True)


@roteador.get(
    "/v1/centros-custo/{centroCustoId}",
    status_code=200,
    operation_id="obterCentroCusto",
    summary="Obter centro de custo",
    responses=RESPOSTAS_PADRAO,
)
async def obter_centro_custo(
    sessao: SessaoDb,
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("centros_custo.ler"))],
    centro_custo_id: Annotated[
        UUID, Path(alias="centroCustoId", description="Identificador do centro de custo.")
    ],
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
) -> contrato.CentroCusto:
    """Obter centro de custo"""
    tenant_id = tenant_id_ou_erro(sujeito)
    centro = await servico.obter_centro_custo(
        sessao, tenant_id=tenant_id, centro_custo_id=centro_custo_id
    )
    return contrato.CentroCusto.model_validate(centro, from_attributes=True)


@roteador.patch(
    "/v1/centros-custo/{centroCustoId}",
    status_code=200,
    operation_id="atualizarCentroCusto",
    summary="Atualizar centro de custo",
    responses=RESPOSTAS_PADRAO,
    dependencies=[Depends(exigir_limite_taxa_sessao())],
)
async def atualizar_centro_custo(
    sessao: SessaoDb,
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("centros_custo.editar"))],
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    centro_custo_id: Annotated[
        UUID, Path(alias="centroCustoId", description="Identificador do centro de custo.")
    ],
    corpo: contrato.CentroCustoAtualizar,
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
) -> contrato.CentroCusto:
    """Atualizar centro de custo"""
    tenant_id = tenant_id_ou_erro(sujeito)
    dados = corpo.model_dump(exclude_unset=True)
    centro = await servico.atualizar_centro_custo(
        sessao,
        tenant_id=tenant_id,
        centro_custo_id=centro_custo_id,
        usuario_id=sujeito.usuario_id,
        dados=dados,
    )
    return contrato.CentroCusto.model_validate(centro, from_attributes=True)


# --------------------------------------------------------------------------
# Cargos
# --------------------------------------------------------------------------


@roteador.get(
    "/v1/cargos",
    status_code=200,
    operation_id="listarCargos",
    summary="Listar cargos",
    responses=RESPOSTAS_PADRAO,
)
async def listar_cargos(
    sessao: SessaoDb,
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("cargos.ler"))],
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
        UUID | None, Query(alias="empresaId", description="Filtra pelos cargos de uma empresa.")
    ] = None,
    cbo: Annotated[str | None, Query(alias="cbo", description="Filtra pelo codigo CBO.")] = None,
    nivel: Annotated[
        str | None, Query(alias="nivel", description="Filtra pelo nivel hierarquico.")
    ] = None,
    ativo: Annotated[
        bool | None, Query(alias="ativo", description="Filtra por cargos ativos.")
    ] = None,
    busca: Annotated[
        str | None,
        Query(
            alias="busca", description="Busca textual livre sobre os campos indexados do recurso."
        ),
    ] = None,
) -> contrato.ListaCargo:
    """Listar cargos"""
    tenant_id = tenant_id_ou_erro(sujeito)
    pedido = resolver_pedido(
        cursor=cursor, limite=limite, ordenar=ordenar, ordenacao_padrao=_ORDENACAO_PADRAO
    )
    linhas = await servico.listar_cargos(
        sessao,
        tenant_id=tenant_id,
        pedido=pedido,
        empresa_id=empresa_id,
        cbo=cbo,
        nivel=nivel,
        ativo=ativo,
        busca=busca,
    )
    dados, paginacao = paginar(pedido=pedido, linhas=linhas)
    return contrato.ListaCargo(
        dados=[contrato.Cargo.model_validate(linha, from_attributes=True) for linha in dados],
        paginacao=contrato.Paginacao.model_validate(paginacao),
    )


@roteador.post(
    "/v1/cargos",
    status_code=201,
    operation_id="criarCargo",
    summary="Criar cargo",
    responses=RESPOSTAS_PADRAO,
    dependencies=[Depends(exigir_limite_taxa_sessao())],
)
async def criar_cargo(
    sessao: SessaoDb,
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("cargos.criar"))],
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    corpo: contrato.CargoCriar,
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
) -> contrato.Cargo:
    """Criar cargo"""
    tenant_id = tenant_id_ou_erro(sujeito)
    cargo = await servico.criar_cargo(
        sessao,
        tenant_id=tenant_id,
        usuario_id=sujeito.usuario_id,
        empresa_id=corpo.empresa_id,
        codigo=corpo.codigo,
        nome=corpo.nome,
        cbo=corpo.cbo,
        descricao=corpo.descricao,
        nivel=corpo.nivel,
        salario_base=float(corpo.salario_base) if corpo.salario_base is not None else None,
        cargo_confianca=corpo.cargo_confianca,
        ativo=corpo.ativo,
    )
    return contrato.Cargo.model_validate(cargo, from_attributes=True)


@roteador.get(
    "/v1/cargos/{cargoId}",
    status_code=200,
    operation_id="obterCargo",
    summary="Obter cargo",
    responses=RESPOSTAS_PADRAO,
)
async def obter_cargo(
    sessao: SessaoDb,
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("cargos.ler"))],
    cargo_id: Annotated[UUID, Path(alias="cargoId", description="Identificador do cargo.")],
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
) -> contrato.Cargo:
    """Obter cargo"""
    tenant_id = tenant_id_ou_erro(sujeito)
    cargo = await servico.obter_cargo(sessao, tenant_id=tenant_id, cargo_id=cargo_id)
    return contrato.Cargo.model_validate(cargo, from_attributes=True)


@roteador.patch(
    "/v1/cargos/{cargoId}",
    status_code=200,
    operation_id="atualizarCargo",
    summary="Atualizar cargo",
    responses=RESPOSTAS_PADRAO,
    dependencies=[Depends(exigir_limite_taxa_sessao())],
)
async def atualizar_cargo(
    sessao: SessaoDb,
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("cargos.editar"))],
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    cargo_id: Annotated[UUID, Path(alias="cargoId", description="Identificador do cargo.")],
    corpo: contrato.CargoAtualizar,
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
) -> contrato.Cargo:
    """Atualizar cargo"""
    tenant_id = tenant_id_ou_erro(sujeito)
    dados = corpo.model_dump(exclude_unset=True)
    if "salario_base" in dados and dados["salario_base"] is not None:
        dados["salario_base"] = float(dados["salario_base"])
    cargo = await servico.atualizar_cargo(
        sessao,
        tenant_id=tenant_id,
        cargo_id=cargo_id,
        usuario_id=sujeito.usuario_id,
        dados=dados,
    )
    return contrato.Cargo.model_validate(cargo, from_attributes=True)


# --------------------------------------------------------------------------
# Equipes e membros
# --------------------------------------------------------------------------


@roteador.get(
    "/v1/equipes",
    status_code=200,
    operation_id="listarEquipes",
    summary="Listar equipes",
    responses=RESPOSTAS_PADRAO,
)
async def listar_equipes(
    sessao: SessaoDb,
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("equipes.ler"))],
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
        UUID | None, Query(alias="empresaId", description="Filtra pelas equipes de uma empresa.")
    ] = None,
    unidade_id: Annotated[
        UUID | None, Query(alias="unidadeId", description="Filtra pelas equipes de uma unidade.")
    ] = None,
    gestor_colaborador_id: Annotated[
        UUID | None,
        Query(alias="gestorColaboradorId", description="Lista as equipes de um gestor."),
    ] = None,
    ativo: Annotated[
        bool | None, Query(alias="ativo", description="Filtra por equipes ativas.")
    ] = None,
    busca: Annotated[
        str | None,
        Query(
            alias="busca", description="Busca textual livre sobre os campos indexados do recurso."
        ),
    ] = None,
) -> contrato.ListaEquipe:
    """Listar equipes"""
    tenant_id = tenant_id_ou_erro(sujeito)
    pedido = resolver_pedido(
        cursor=cursor, limite=limite, ordenar=ordenar, ordenacao_padrao=_ORDENACAO_PADRAO
    )
    linhas = await servico.listar_equipes(
        sessao,
        tenant_id=tenant_id,
        pedido=pedido,
        empresa_id=empresa_id,
        unidade_id=unidade_id,
        gestor_colaborador_id=gestor_colaborador_id,
        ativo=ativo,
        busca=busca,
    )
    dados, paginacao = paginar(pedido=pedido, linhas=linhas)
    return contrato.ListaEquipe(
        dados=[contrato.Equipe.model_validate(linha, from_attributes=True) for linha in dados],
        paginacao=contrato.Paginacao.model_validate(paginacao),
    )


@roteador.post(
    "/v1/equipes",
    status_code=201,
    operation_id="criarEquipe",
    summary="Criar equipe",
    responses=RESPOSTAS_PADRAO,
    dependencies=[Depends(exigir_limite_taxa_sessao())],
)
async def criar_equipe(
    sessao: SessaoDb,
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("equipes.criar"))],
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    corpo: contrato.EquipeCriar,
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
) -> contrato.Equipe:
    """Criar equipe"""
    tenant_id = tenant_id_ou_erro(sujeito)
    equipe = await servico.criar_equipe(
        sessao,
        tenant_id=tenant_id,
        usuario_id=sujeito.usuario_id,
        empresa_id=corpo.empresa_id,
        codigo=corpo.codigo,
        nome=corpo.nome,
        unidade_id=corpo.unidade_id,
        departamento_id=corpo.departamento_id,
        gestor_colaborador_id=corpo.gestor_colaborador_id,
        descricao=corpo.descricao,
        cor=corpo.cor,
        ativo=corpo.ativo,
    )
    return contrato.Equipe.model_validate(equipe, from_attributes=True)


@roteador.get(
    "/v1/equipes/{equipeId}",
    status_code=200,
    operation_id="obterEquipe",
    summary="Obter equipe",
    responses=RESPOSTAS_PADRAO,
)
async def obter_equipe(
    sessao: SessaoDb,
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("equipes.ler"))],
    equipe_id: Annotated[UUID, Path(alias="equipeId", description="Identificador da equipe.")],
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
) -> contrato.Equipe:
    """Obter equipe"""
    tenant_id = tenant_id_ou_erro(sujeito)
    equipe = await servico.obter_equipe(sessao, tenant_id=tenant_id, equipe_id=equipe_id)
    return contrato.Equipe.model_validate(equipe, from_attributes=True)


@roteador.patch(
    "/v1/equipes/{equipeId}",
    status_code=200,
    operation_id="atualizarEquipe",
    summary="Atualizar equipe",
    responses=RESPOSTAS_PADRAO,
    dependencies=[Depends(exigir_limite_taxa_sessao())],
)
async def atualizar_equipe(
    sessao: SessaoDb,
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("equipes.editar"))],
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    equipe_id: Annotated[UUID, Path(alias="equipeId", description="Identificador da equipe.")],
    corpo: contrato.EquipeAtualizar,
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
) -> contrato.Equipe:
    """Atualizar equipe"""
    tenant_id = tenant_id_ou_erro(sujeito)
    dados = corpo.model_dump(exclude_unset=True)
    equipe = await servico.atualizar_equipe(
        sessao,
        tenant_id=tenant_id,
        equipe_id=equipe_id,
        usuario_id=sujeito.usuario_id,
        dados=dados,
    )
    return contrato.Equipe.model_validate(equipe, from_attributes=True)


@roteador.post(
    "/v1/equipes/{equipeId}/membros",
    status_code=201,
    operation_id="adicionarMembroEquipe",
    summary="Adicionar membro a equipe",
    responses=RESPOSTAS_PADRAO,
    dependencies=[Depends(exigir_limite_taxa_sessao())],
)
async def adicionar_membro_equipe(
    sessao: SessaoDb,
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("equipes.editar"))],
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    equipe_id: Annotated[UUID, Path(alias="equipeId", description="Identificador da equipe.")],
    corpo: contrato.EquipeMembroCriar,
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
) -> contrato.EquipeMembro:
    """Adicionar membro a equipe"""
    tenant_id = tenant_id_ou_erro(sujeito)
    membro = await servico.adicionar_membro_equipe(
        sessao,
        tenant_id=tenant_id,
        equipe_id=equipe_id,
        usuario_id=sujeito.usuario_id,
        colaborador_id=corpo.colaborador_id,
        papel=corpo.papel,
        vigencia_inicio=corpo.vigencia_inicio,
        vigencia_fim=corpo.vigencia_fim,
    )
    return contrato.EquipeMembro.model_validate(membro, from_attributes=True)
