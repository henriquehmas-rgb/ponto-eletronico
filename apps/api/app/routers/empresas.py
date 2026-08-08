"""Rotas da tag `empresas` do contrato.

Pessoas juridicas empregadoras.
Matriz e filiais sao registros distintos, cada um com CNPJ proprio, REP-P proprio e arquivos fiscais proprios.

Implementado na Fase F2 (agente A1). Regra de negocio em `app/organizacao/empresas.py`.

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

from app.comum.autenticacao_cliente import (
    ContextoAcesso,
    aplicar_limite_taxa_se_cliente,
    exigir_permissao_ou_escopo,
    usuario_id_do_acesso,
)
from app.comum.limitador_taxa import exigir_limite_taxa_sessao
from app.core.erros import RESPOSTAS_PADRAO
from app.db.sessao import SessaoDb
from app.organizacao import empresas as servico
from app.organizacao.paginacao import paginar, resolver_pedido
from app.schemas import contrato

roteador = APIRouter(tags=["empresas"])

_ORDENACAO_PADRAO = "criado_em:desc"

# Uma instancia por operacao (nao uma fabrica chamada de novo dentro do
# handler): mesmo motivo documentado em `app.comum.limitador_taxa`
# (identidade estavel do *callable* pro cache de dependencia do FastAPI).
_ACESSO_LISTAR = exigir_permissao_ou_escopo(permissao="empresas.ler", escopo="organizacao:ler")
_ACESSO_CRIAR = exigir_permissao_ou_escopo(
    permissao="empresas.criar", escopo="organizacao:escrever"
)
_ACESSO_OBTER = exigir_permissao_ou_escopo(permissao="empresas.ler", escopo="organizacao:ler")
_ACESSO_ATUALIZAR = exigir_permissao_ou_escopo(
    permissao="empresas.editar", escopo="organizacao:escrever"
)
_ACESSO_EXCLUIR = exigir_permissao_ou_escopo(
    permissao="empresas.excluir", escopo="organizacao:escrever"
)


@roteador.get(
    "/v1/empresas",
    status_code=200,
    operation_id="listarEmpresas",
    summary="Listar empresas",
    responses=RESPOSTAS_PADRAO,
)
async def listar_empresas(
    sessao: SessaoDb,
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_LISTAR)],
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
    await aplicar_limite_taxa_se_cliente(response, acesso)
    pedido = resolver_pedido(
        cursor=cursor, limite=limite, ordenar=ordenar, ordenacao_padrao=_ORDENACAO_PADRAO
    )
    linhas = await servico.listar_empresas(
        sessao,
        tenant_id=acesso.tenant_id,
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
    dependencies=[Depends(exigir_limite_taxa_sessao())],
)
async def criar_empresa(
    sessao: SessaoDb,
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_CRIAR)],
    response: Response,
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
    await aplicar_limite_taxa_se_cliente(response, acesso)
    empresa = await servico.criar_empresa(
        sessao,
        tenant_id=acesso.tenant_id,
        usuario_id=usuario_id_do_acesso(acesso),
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
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_OBTER)],
    response: Response,
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
    await aplicar_limite_taxa_se_cliente(response, acesso)
    empresa = await servico.obter_empresa(sessao, tenant_id=acesso.tenant_id, empresa_id=empresa_id)
    return contrato.Empresa.model_validate(empresa, from_attributes=True)


@roteador.patch(
    "/v1/empresas/{empresaId}",
    status_code=200,
    operation_id="atualizarEmpresa",
    summary="Atualizar empresa",
    responses=RESPOSTAS_PADRAO,
    dependencies=[Depends(exigir_limite_taxa_sessao())],
)
async def atualizar_empresa(
    sessao: SessaoDb,
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_ATUALIZAR)],
    response: Response,
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
    await aplicar_limite_taxa_se_cliente(response, acesso)
    dados = corpo.model_dump(exclude_unset=True)
    empresa = await servico.atualizar_empresa(
        sessao,
        tenant_id=acesso.tenant_id,
        empresa_id=empresa_id,
        usuario_id=usuario_id_do_acesso(acesso),
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
    dependencies=[Depends(exigir_limite_taxa_sessao())],
)
async def excluir_empresa(
    sessao: SessaoDb,
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_EXCLUIR)],
    response: Response,
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
    await aplicar_limite_taxa_se_cliente(response, acesso)
    await servico.excluir_empresa(
        sessao,
        tenant_id=acesso.tenant_id,
        empresa_id=empresa_id,
        usuario_id=usuario_id_do_acesso(acesso),
    )
    # Reaproveita o `response` injetado (ja carrega os cabecalhos
    # `RateLimit-*` setados acima, quando o acesso e de cliente de
    # integracao) em vez de construir um `Response` novo, que perderia
    # esses cabecalhos -- mesmo padrao de `app/routers/webhooks.py`.
    response.status_code = 204
    return response
