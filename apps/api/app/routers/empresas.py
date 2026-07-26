"""Rotas da tag `empresas` do contrato.

Pessoas juridicas empregadoras.
Matriz e filiais sao registros distintos, cada um com CNPJ proprio, REP-P proprio e arquivos fiscais proprios.

Implementado na Fase F2 (agente A1). Regra de negocio em `app/organizacao/empresas.py`.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Path, Query, Response

from app.core.erros import RESPOSTAS_PADRAO
from app.core.seguranca import Sujeito, exigir_permissao, tenant_id_ou_erro
from app.db.sessao import SessaoDb
from app.organizacao import empresas as servico
from app.organizacao.paginacao import paginar, resolver_pedido
from app.schemas import contrato

roteador = APIRouter(tags=["empresas"])

_ORDENACAO_PADRAO = "criado_em:desc"


@roteador.get(
    "/v1/empresas",
    status_code=200,
    operation_id="listarEmpresas",
    summary="Listar empresas",
    responses=RESPOSTAS_PADRAO,
)
async def listar_empresas(
    sessao: SessaoDb,
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("empresas.ler"))],
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
        UUID | None, Query(alias="empresaId", description="Filtra por identificador exato.")
    ] = None,
    cnpj: Annotated[
        str | None, Query(alias="cnpj", description="Filtra por CNPJ, somente digitos.")
    ] = None,
    tipo: Annotated[
        str | None, Query(alias="tipo", description="Filtra por matriz ou filial.")
    ] = None,
    matriz_id: Annotated[
        UUID | None, Query(alias="matrizId", description="Lista as filiais de uma matriz.")
    ] = None,
    ativo: Annotated[
        bool | None, Query(alias="ativo", description="Filtra por empresas ativas ou inativas.")
    ] = None,
    busca: Annotated[
        str | None,
        Query(
            alias="busca", description="Busca textual livre sobre os campos indexados do recurso."
        ),
    ] = None,
    incluir_excluidos: Annotated[
        bool | None,
        Query(
            alias="incluirExcluidos",
            description="Inclui registros com exclusao logica (excluidoEm preenchido) no resultado.",
        ),
    ] = None,
) -> contrato.ListaEmpresa:
    """Listar empresas"""
    tenant_id = tenant_id_ou_erro(sujeito)
    pedido = resolver_pedido(
        cursor=cursor, limite=limite, ordenar=ordenar, ordenacao_padrao=_ORDENACAO_PADRAO
    )
    linhas = await servico.listar_empresas(
        sessao,
        tenant_id=tenant_id,
        pedido=pedido,
        empresa_id=empresa_id,
        cnpj=cnpj,
        tipo=tipo,
        matriz_id=matriz_id,
        ativo=ativo,
        busca=busca,
        incluir_excluidos=bool(incluir_excluidos),
    )
    dados, paginacao = paginar(pedido=pedido, linhas=linhas)
    return contrato.ListaEmpresa(
        dados=[contrato.Empresa.model_validate(linha, from_attributes=True) for linha in dados],
        paginacao=contrato.Paginacao.model_validate(paginacao),
    )


@roteador.post(
    "/v1/empresas",
    status_code=201,
    operation_id="criarEmpresa",
    summary="Criar empresa",
    responses=RESPOSTAS_PADRAO,
)
async def criar_empresa(
    sessao: SessaoDb,
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("empresas.criar"))],
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    corpo: contrato.EmpresaCriar,
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
) -> contrato.Empresa:
    """Criar empresa"""
    tenant_id = tenant_id_ou_erro(sujeito)
    empresa = await servico.criar_empresa(
        sessao,
        tenant_id=tenant_id,
        usuario_id=sujeito.usuario_id,
        matriz_id=corpo.matriz_id,
        tipo=corpo.tipo,
        cnpj=corpo.cnpj,
        razao_social=corpo.razao_social,
        nome_fantasia=corpo.nome_fantasia,
        inscricao_estadual=corpo.inscricao_estadual,
        inscricao_municipal=corpo.inscricao_municipal,
        cnae_principal=corpo.cnae_principal,
        cei_caepf=corpo.cei_caepf,
        natureza_juridica=corpo.natureza_juridica,
        logradouro=corpo.logradouro,
        numero=corpo.numero,
        complemento=corpo.complemento,
        bairro=corpo.bairro,
        municipio=corpo.municipio,
        uf=corpo.uf,
        cep=corpo.cep,
        codigo_ibge_municipio=corpo.codigo_ibge_municipio,
        telefone=corpo.telefone,
        email=corpo.email,
        fuso_horario=corpo.fuso_horario,
        logo_ref=corpo.logo_ref,
        ativo=corpo.ativo,
    )
    return contrato.Empresa.model_validate(empresa, from_attributes=True)


@roteador.get(
    "/v1/empresas/{empresaId}",
    status_code=200,
    operation_id="obterEmpresa",
    summary="Obter empresa",
    responses=RESPOSTAS_PADRAO,
)
async def obter_empresa(
    sessao: SessaoDb,
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("empresas.ler"))],
    empresa_id: Annotated[UUID, Path(alias="empresaId", description="Identificador da empresa.")],
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
) -> contrato.Empresa:
    """Obter empresa"""
    tenant_id = tenant_id_ou_erro(sujeito)
    empresa = await servico.obter_empresa(sessao, tenant_id=tenant_id, empresa_id=empresa_id)
    return contrato.Empresa.model_validate(empresa, from_attributes=True)


@roteador.patch(
    "/v1/empresas/{empresaId}",
    status_code=200,
    operation_id="atualizarEmpresa",
    summary="Atualizar empresa",
    responses=RESPOSTAS_PADRAO,
)
async def atualizar_empresa(
    sessao: SessaoDb,
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("empresas.editar"))],
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    empresa_id: Annotated[UUID, Path(alias="empresaId", description="Identificador da empresa.")],
    corpo: contrato.EmpresaAtualizar,
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
) -> contrato.Empresa:
    """Atualizar empresa"""
    tenant_id = tenant_id_ou_erro(sujeito)
    dados = corpo.model_dump(exclude_unset=True)
    empresa = await servico.atualizar_empresa(
        sessao,
        tenant_id=tenant_id,
        empresa_id=empresa_id,
        usuario_id=sujeito.usuario_id,
        dados=dados,
    )
    return contrato.Empresa.model_validate(empresa, from_attributes=True)


@roteador.delete(
    "/v1/empresas/{empresaId}",
    status_code=204,
    operation_id="excluirEmpresa",
    summary="Excluir empresa",
    responses=RESPOSTAS_PADRAO,
    response_class=Response,
)
async def excluir_empresa(
    sessao: SessaoDb,
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("empresas.excluir"))],
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    empresa_id: Annotated[UUID, Path(alias="empresaId", description="Identificador da empresa.")],
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
    """Excluir empresa"""
    tenant_id = tenant_id_ou_erro(sujeito)
    await servico.excluir_empresa(
        sessao, tenant_id=tenant_id, empresa_id=empresa_id, usuario_id=sujeito.usuario_id
    )
    return Response(status_code=204)
