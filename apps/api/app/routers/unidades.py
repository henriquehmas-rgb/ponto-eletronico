"""Rotas da tag `unidades` do contrato.

Locais fisicos de trabalho.
A unidade carrega o fuso efetivo da apuracao, a geocerca do registro por aplicativo, a allowlist de faixas CIDR do registro por navegador e os conjuntos de feriados aplicaveis.

Implementado na Fase F2 (agente A1). Regra de negocio em `app/organizacao/unidades.py`.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Path, Query, Response

from app.core.erros import RESPOSTAS_PADRAO
from app.core.seguranca import Sujeito, exigir_permissao, tenant_id_ou_erro
from app.db.sessao import SessaoDb
from app.organizacao import unidades as servico
from app.organizacao.paginacao import paginar, resolver_pedido
from app.schemas import contrato

roteador = APIRouter(tags=["unidades"])

_ORDENACAO_PADRAO = "criado_em:desc"


@roteador.get(
    "/v1/unidades",
    status_code=200,
    operation_id="listarUnidades",
    summary="Listar unidades",
    responses=RESPOSTAS_PADRAO,
)
async def listar_unidades(
    sessao: SessaoDb,
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("unidades.ler"))],
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
        UUID | None, Query(alias="empresaId", description="Filtra pelas unidades de uma empresa.")
    ] = None,
    tipo: Annotated[
        str | None, Query(alias="tipo", description="Filtra pelo tipo de local.")
    ] = None,
    uf: Annotated[
        str | None, Query(alias="uf", description="Filtra pela unidade federativa.")
    ] = None,
    com_geocerca: Annotated[
        bool | None,
        Query(alias="comGeocerca", description="Filtra unidades com ou sem geocerca configurada."),
    ] = None,
    ativo: Annotated[
        bool | None, Query(alias="ativo", description="Filtra por unidades ativas ou inativas.")
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
) -> contrato.ListaUnidade:
    """Listar unidades"""
    tenant_id = tenant_id_ou_erro(sujeito)
    pedido = resolver_pedido(
        cursor=cursor, limite=limite, ordenar=ordenar, ordenacao_padrao=_ORDENACAO_PADRAO
    )
    linhas = await servico.listar_unidades(
        sessao,
        tenant_id=tenant_id,
        pedido=pedido,
        empresa_id=empresa_id,
        tipo=tipo,
        uf=uf,
        com_geocerca=com_geocerca,
        ativo=ativo,
        busca=busca,
        incluir_excluidos=bool(incluir_excluidos),
    )
    dados, paginacao = paginar(pedido=pedido, linhas=linhas)
    return contrato.ListaUnidade(
        dados=[contrato.Unidade.model_validate(linha, from_attributes=True) for linha in dados],
        paginacao=contrato.Paginacao.model_validate(paginacao),
    )


@roteador.post(
    "/v1/unidades",
    status_code=201,
    operation_id="criarUnidade",
    summary="Criar unidade",
    responses=RESPOSTAS_PADRAO,
)
async def criar_unidade(
    sessao: SessaoDb,
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("unidades.criar"))],
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    corpo: contrato.UnidadeCriar,
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
) -> contrato.Unidade:
    """Criar unidade"""
    tenant_id = tenant_id_ou_erro(sujeito)
    unidade = await servico.criar_unidade(
        sessao,
        tenant_id=tenant_id,
        usuario_id=sujeito.usuario_id,
        empresa_id=corpo.empresa_id,
        codigo=corpo.codigo,
        nome=corpo.nome,
        tipo=corpo.tipo,
        logradouro=corpo.logradouro,
        numero=corpo.numero,
        complemento=corpo.complemento,
        bairro=corpo.bairro,
        municipio=corpo.municipio,
        uf=corpo.uf,
        cep=corpo.cep,
        codigo_ibge_municipio=corpo.codigo_ibge_municipio,
        fuso_horario=corpo.fuso_horario,
        geocerca_latitude=corpo.geocerca_latitude,
        geocerca_longitude=corpo.geocerca_longitude,
        geocerca_raio_metros=corpo.geocerca_raio_metros,
        geocerca_poligono=corpo.geocerca_poligono,
        geocerca_obrigatoria=corpo.geocerca_obrigatoria,
        geocerca_tolerancia_metros=corpo.geocerca_tolerancia_metros,
        ativo=corpo.ativo,
    )
    return contrato.Unidade.model_validate(unidade, from_attributes=True)


@roteador.get(
    "/v1/unidades/{unidadeId}",
    status_code=200,
    operation_id="obterUnidade",
    summary="Obter unidade",
    responses=RESPOSTAS_PADRAO,
)
async def obter_unidade(
    sessao: SessaoDb,
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("unidades.ler"))],
    unidade_id: Annotated[UUID, Path(alias="unidadeId", description="Identificador da unidade.")],
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
) -> contrato.Unidade:
    """Obter unidade"""
    tenant_id = tenant_id_ou_erro(sujeito)
    unidade = await servico.obter_unidade(sessao, tenant_id=tenant_id, unidade_id=unidade_id)
    return contrato.Unidade.model_validate(unidade, from_attributes=True)


@roteador.patch(
    "/v1/unidades/{unidadeId}",
    status_code=200,
    operation_id="atualizarUnidade",
    summary="Atualizar unidade",
    responses=RESPOSTAS_PADRAO,
)
async def atualizar_unidade(
    sessao: SessaoDb,
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("unidades.editar"))],
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    unidade_id: Annotated[UUID, Path(alias="unidadeId", description="Identificador da unidade.")],
    corpo: contrato.UnidadeAtualizar,
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
) -> contrato.Unidade:
    """Atualizar unidade"""
    tenant_id = tenant_id_ou_erro(sujeito)
    dados = corpo.model_dump(exclude_unset=True)
    unidade = await servico.atualizar_unidade(
        sessao,
        tenant_id=tenant_id,
        unidade_id=unidade_id,
        usuario_id=sujeito.usuario_id,
        dados=dados,
    )
    return contrato.Unidade.model_validate(unidade, from_attributes=True)


@roteador.delete(
    "/v1/unidades/{unidadeId}",
    status_code=204,
    operation_id="excluirUnidade",
    summary="Excluir unidade",
    responses=RESPOSTAS_PADRAO,
    response_class=Response,
)
async def excluir_unidade(
    sessao: SessaoDb,
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("unidades.excluir"))],
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    unidade_id: Annotated[UUID, Path(alias="unidadeId", description="Identificador da unidade.")],
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
    """Excluir unidade"""
    tenant_id = tenant_id_ou_erro(sujeito)
    await servico.excluir_unidade(
        sessao, tenant_id=tenant_id, unidade_id=unidade_id, usuario_id=sujeito.usuario_id
    )
    return Response(status_code=204)


@roteador.get(
    "/v1/unidades/{unidadeId}/redes-permitidas",
    status_code=200,
    operation_id="listarRedesPermitidas",
    summary="Listar faixas de rede permitidas",
    responses=RESPOSTAS_PADRAO,
)
async def listar_redes_permitidas(
    sessao: SessaoDb,
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("unidades.ler"))],
    unidade_id: Annotated[UUID, Path(alias="unidadeId", description="Identificador da unidade.")],
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
    canal: Annotated[
        str | None, Query(alias="canal", description="Filtra pelo canal restrito.")
    ] = None,
    ativo: Annotated[
        bool | None, Query(alias="ativo", description="Filtra por faixas ativas.")
    ] = None,
) -> contrato.ListaRedePermitida:
    """Listar faixas de rede permitidas"""
    tenant_id = tenant_id_ou_erro(sujeito)
    pedido = resolver_pedido(
        cursor=cursor, limite=limite, ordenar=ordenar, ordenacao_padrao=_ORDENACAO_PADRAO
    )
    linhas = await servico.listar_redes_permitidas(
        sessao,
        tenant_id=tenant_id,
        unidade_id=unidade_id,
        pedido=pedido,
        canal=canal,
        ativo=ativo,
    )
    dados, paginacao = paginar(pedido=pedido, linhas=linhas)
    return contrato.ListaRedePermitida(
        dados=[
            contrato.RedePermitida.model_validate(linha, from_attributes=True) for linha in dados
        ],
        paginacao=contrato.Paginacao.model_validate(paginacao),
    )


@roteador.post(
    "/v1/unidades/{unidadeId}/redes-permitidas",
    status_code=201,
    operation_id="criarRedePermitida",
    summary="Adicionar faixa de rede permitida",
    responses=RESPOSTAS_PADRAO,
)
async def criar_rede_permitida(
    sessao: SessaoDb,
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("unidades.editar"))],
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    unidade_id: Annotated[UUID, Path(alias="unidadeId", description="Identificador da unidade.")],
    corpo: contrato.RedePermitidaCriar,
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
) -> contrato.RedePermitida:
    """Adicionar faixa de rede permitida"""
    tenant_id = tenant_id_ou_erro(sujeito)
    rede = await servico.criar_rede_permitida(
        sessao,
        tenant_id=tenant_id,
        usuario_id=sujeito.usuario_id,
        unidade_id=unidade_id,
        empresa_id=corpo.empresa_id,
        cidr=corpo.cidr,
        descricao=corpo.descricao,
        canal=corpo.canal,
        ativo=corpo.ativo,
    )
    return contrato.RedePermitida.model_validate(rede, from_attributes=True)


@roteador.delete(
    "/v1/unidades/{unidadeId}/redes-permitidas/{redeId}",
    status_code=204,
    operation_id="excluirRedePermitida",
    summary="Remover faixa de rede permitida",
    responses=RESPOSTAS_PADRAO,
    response_class=Response,
)
async def excluir_rede_permitida(
    sessao: SessaoDb,
    sujeito: Annotated[Sujeito, Depends(exigir_permissao("unidades.editar"))],
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    unidade_id: Annotated[UUID, Path(alias="unidadeId", description="Identificador da unidade.")],
    rede_id: Annotated[UUID, Path(alias="redeId", description="Identificador da faixa.")],
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
    """Remover faixa de rede permitida"""
    tenant_id = tenant_id_ou_erro(sujeito)
    await servico.excluir_rede_permitida(
        sessao, tenant_id=tenant_id, unidade_id=unidade_id, rede_id=rede_id
    )
    return Response(status_code=204)
