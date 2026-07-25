"""Rotas da tag `tenants` do contrato. GERADO -- nao editar.

Tenants do SaaS e suas configuracoes.
Todo dado de dominio pertence a um tenant e vive sob Row Level Security no banco: nenhuma operacao atravessa a fronteira, e tentativa de acesso cross-tenant e barrada e auditada.

Regra de negocio destas operacoes entra na fase F1. Ate la toda chamada
responde 501 com PONTO-INT-005. Regerar com
`python tools/gerar_do_contrato.py`.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Path, Query

from app.core.erros import RESPOSTAS_PADRAO, NaoImplementado
from app.schemas import contrato

roteador = APIRouter(tags=["tenants"])


@roteador.get(
    "/v1/tenants/atual",
    status_code=200,
    operation_id="obterTenantAtual",
    summary="Obter tenant corrente",
    responses=RESPOSTAS_PADRAO,
)
async def obter_tenant_atual(
    x_tenant: Annotated[
        str | None,
        Header(
            alias="X-Tenant",
            description="Slug ou UUID do tenant alvo. Obrigatorio quando o host nao identifica o tenant (chamadas a api.ponto.<dominio> por cliente de integracao). Em acesso por subd...",
        ),
    ] = None,
    x_request_id: Annotated[
        str | None,
        Header(
            alias="X-Request-Id",
            description="Identificador de correlacao gerado pelo cliente. Quando ausente o servidor gera um e devolve no cabecalho de resposta de mesmo nome. Aparece na trilha de aud...",
        ),
    ] = None,
) -> contrato.Tenant:
    """Obter tenant corrente

    Fase 0 entrega andaime: a implementacao entra na fase F1.
    """
    raise NaoImplementado("obterTenantAtual", fase="F1")


@roteador.get(
    "/v1/tenants",
    status_code=200,
    operation_id="listarTenants",
    summary="Listar tenants",
    responses=RESPOSTAS_PADRAO,
)
async def listar_tenants(
    x_tenant: Annotated[
        str | None,
        Header(
            alias="X-Tenant",
            description="Slug ou UUID do tenant alvo. Obrigatorio quando o host nao identifica o tenant (chamadas a api.ponto.<dominio> por cliente de integracao). Em acesso por subd...",
        ),
    ] = None,
    x_request_id: Annotated[
        str | None,
        Header(
            alias="X-Request-Id",
            description="Identificador de correlacao gerado pelo cliente. Quando ausente o servidor gera um e devolve no cabecalho de resposta de mesmo nome. Aparece na trilha de aud...",
        ),
    ] = None,
    cursor: Annotated[
        str | None,
        Query(
            alias="cursor",
            description="Cursor opaco devolvido em paginacao.proximoCursor da pagina anterior. Ausente retorna a primeira pagina. O cursor codifica a ordenacao usada: trocar o parame...",
        ),
    ] = None,
    limite: Annotated[
        int | None, Query(alias="limite", description="Quantidade de itens por pagina.")
    ] = None,
    ordenar: Annotated[
        str | None,
        Query(
            alias="ordenar",
            description="Ordenacao no formato campo:direcao, separando multiplos criterios por virgula. Direcoes aceitas: asc e desc. Campos aceitos sao os documentados em cada opera...",
        ),
    ] = None,
    status: Annotated[
        str | None, Query(alias="status", description="Filtra pela situacao contratual.")
    ] = None,
    plano: Annotated[
        str | None, Query(alias="plano", description="Filtra pelo plano contratado.")
    ] = None,
    busca: Annotated[
        str | None,
        Query(
            alias="busca", description="Busca textual livre sobre os campos indexados do recurso."
        ),
    ] = None,
) -> contrato.ListaTenant:
    """Listar tenants

    Fase 0 entrega andaime: a implementacao entra na fase F1.
    """
    raise NaoImplementado("listarTenants", fase="F1")


@roteador.post(
    "/v1/tenants",
    status_code=201,
    operation_id="criarTenant",
    summary="Criar tenant",
    responses=RESPOSTAS_PADRAO,
)
async def criar_tenant(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo devo...",
        ),
    ],
    corpo: contrato.TenantCriar,
    x_tenant: Annotated[
        str | None,
        Header(
            alias="X-Tenant",
            description="Slug ou UUID do tenant alvo. Obrigatorio quando o host nao identifica o tenant (chamadas a api.ponto.<dominio> por cliente de integracao). Em acesso por subd...",
        ),
    ] = None,
    x_request_id: Annotated[
        str | None,
        Header(
            alias="X-Request-Id",
            description="Identificador de correlacao gerado pelo cliente. Quando ausente o servidor gera um e devolve no cabecalho de resposta de mesmo nome. Aparece na trilha de aud...",
        ),
    ] = None,
) -> contrato.Tenant:
    """Criar tenant

    Fase 0 entrega andaime: a implementacao entra na fase F1.
    """
    raise NaoImplementado("criarTenant", fase="F1")


@roteador.get(
    "/v1/tenants/{tenantId}",
    status_code=200,
    operation_id="obterTenant",
    summary="Obter tenant",
    responses=RESPOSTAS_PADRAO,
)
async def obter_tenant(
    tenant_id: Annotated[UUID, Path(alias="tenantId", description="Identificador do tenant.")],
    x_tenant: Annotated[
        str | None,
        Header(
            alias="X-Tenant",
            description="Slug ou UUID do tenant alvo. Obrigatorio quando o host nao identifica o tenant (chamadas a api.ponto.<dominio> por cliente de integracao). Em acesso por subd...",
        ),
    ] = None,
    x_request_id: Annotated[
        str | None,
        Header(
            alias="X-Request-Id",
            description="Identificador de correlacao gerado pelo cliente. Quando ausente o servidor gera um e devolve no cabecalho de resposta de mesmo nome. Aparece na trilha de aud...",
        ),
    ] = None,
) -> contrato.Tenant:
    """Obter tenant

    Fase 0 entrega andaime: a implementacao entra na fase F1.
    """
    raise NaoImplementado("obterTenant", fase="F1")


@roteador.patch(
    "/v1/tenants/{tenantId}",
    status_code=200,
    operation_id="atualizarTenant",
    summary="Atualizar tenant",
    responses=RESPOSTAS_PADRAO,
)
async def atualizar_tenant(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo devo...",
        ),
    ],
    tenant_id: Annotated[UUID, Path(alias="tenantId", description="Identificador do tenant.")],
    corpo: contrato.TenantAtualizar,
    x_tenant: Annotated[
        str | None,
        Header(
            alias="X-Tenant",
            description="Slug ou UUID do tenant alvo. Obrigatorio quando o host nao identifica o tenant (chamadas a api.ponto.<dominio> por cliente de integracao). Em acesso por subd...",
        ),
    ] = None,
    x_request_id: Annotated[
        str | None,
        Header(
            alias="X-Request-Id",
            description="Identificador de correlacao gerado pelo cliente. Quando ausente o servidor gera um e devolve no cabecalho de resposta de mesmo nome. Aparece na trilha de aud...",
        ),
    ] = None,
) -> contrato.Tenant:
    """Atualizar tenant

    Fase 0 entrega andaime: a implementacao entra na fase F1.
    """
    raise NaoImplementado("atualizarTenant", fase="F1")


@roteador.get(
    "/v1/tenants/{tenantId}/configuracoes",
    status_code=200,
    operation_id="listarConfiguracoesTenant",
    summary="Listar configuracoes do tenant",
    responses=RESPOSTAS_PADRAO,
)
async def listar_configuracoes_tenant(
    tenant_id: Annotated[UUID, Path(alias="tenantId", description="Identificador do tenant.")],
    x_tenant: Annotated[
        str | None,
        Header(
            alias="X-Tenant",
            description="Slug ou UUID do tenant alvo. Obrigatorio quando o host nao identifica o tenant (chamadas a api.ponto.<dominio> por cliente de integracao). Em acesso por subd...",
        ),
    ] = None,
    x_request_id: Annotated[
        str | None,
        Header(
            alias="X-Request-Id",
            description="Identificador de correlacao gerado pelo cliente. Quando ausente o servidor gera um e devolve no cabecalho de resposta de mesmo nome. Aparece na trilha de aud...",
        ),
    ] = None,
    cursor: Annotated[
        str | None,
        Query(
            alias="cursor",
            description="Cursor opaco devolvido em paginacao.proximoCursor da pagina anterior. Ausente retorna a primeira pagina. O cursor codifica a ordenacao usada: trocar o parame...",
        ),
    ] = None,
    limite: Annotated[
        int | None, Query(alias="limite", description="Quantidade de itens por pagina.")
    ] = None,
    ordenar: Annotated[
        str | None,
        Query(
            alias="ordenar",
            description="Ordenacao no formato campo:direcao, separando multiplos criterios por virgula. Direcoes aceitas: asc e desc. Campos aceitos sao os documentados em cada opera...",
        ),
    ] = None,
    categoria: Annotated[
        str | None, Query(alias="categoria", description="Filtra por categoria de configuracao.")
    ] = None,
) -> contrato.ListaTenantConfiguracao:
    """Listar configuracoes do tenant

    Fase 0 entrega andaime: a implementacao entra na fase F1.
    """
    raise NaoImplementado("listarConfiguracoesTenant", fase="F1")


@roteador.put(
    "/v1/tenants/{tenantId}/configuracoes/{chave}",
    status_code=200,
    operation_id="definirConfiguracaoTenant",
    summary="Definir configuracao do tenant",
    responses=RESPOSTAS_PADRAO,
)
async def definir_configuracao_tenant(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo devo...",
        ),
    ],
    tenant_id: Annotated[UUID, Path(alias="tenantId", description="Identificador do tenant.")],
    chave: Annotated[
        str,
        Path(
            alias="chave",
            description="Chave hierarquica da configuracao, por exemplo seguranca.mfa.obrigatorio.",
        ),
    ],
    corpo: contrato.TenantConfiguracaoCriar,
    x_tenant: Annotated[
        str | None,
        Header(
            alias="X-Tenant",
            description="Slug ou UUID do tenant alvo. Obrigatorio quando o host nao identifica o tenant (chamadas a api.ponto.<dominio> por cliente de integracao). Em acesso por subd...",
        ),
    ] = None,
    x_request_id: Annotated[
        str | None,
        Header(
            alias="X-Request-Id",
            description="Identificador de correlacao gerado pelo cliente. Quando ausente o servidor gera um e devolve no cabecalho de resposta de mesmo nome. Aparece na trilha de aud...",
        ),
    ] = None,
) -> contrato.TenantConfiguracao:
    """Definir configuracao do tenant

    Fase 0 entrega andaime: a implementacao entra na fase F1.
    """
    raise NaoImplementado("definirConfiguracaoTenant", fase="F1")
