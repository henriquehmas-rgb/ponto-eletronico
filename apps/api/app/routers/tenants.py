"""Rotas da tag `tenants` do contrato.

Tenants do SaaS e suas configuracoes.
Todo dado de dominio pertence a um tenant e vive sob Row Level Security no banco: nenhuma operacao atravessa a fronteira, e tentativa de acesso cross-tenant e barrada e auditada.

Regra de negocio implementada na F1/A2 (T2) -- ver
`app.identidade.tenancy.servico`. `listarTenants` e `criarTenant` continuam
`501`: sao necessariamente CROSS-tenant e a role de conexao da aplicacao
(`ponto_app`) nao tem `BYPASSRLS` -- ver `docs/backlog.md` (item "F1 / A2").

Autenticacao dupla (retrofit de 2026-08-08): o contrato ja declarava os tres
esquemas alternativos por operacao (`bearerAuth`/`oauth2`/`apiKeyAuth`), mas
so sessao humana era aceita ate agora. `Depends(exigir_permissao(...))`
trocado por `Depends(exigir_permissao_ou_escopo(...))` -- sessao humana E'
tentada primeiro (comportamento humano preservado byte a byte), cliente de
integracao (OAuth/API key) so entra quando nao ha sessao humana autenticada.
Mesmo padrao ja provado em `app/routers/empresas.py`/`webhooks.py`.
`obterTenantAtual` ficou de fora de proposito: nao tem `x-permissao`/
`x-escopo` no contrato e ja nao exigia sujeito autenticado nenhum (ver
docstring do handler) -- nao ha o que retrofitar la.
"""

from __future__ import annotations

from typing import Annotated, Any, TypeVar
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Path, Query, Response
from pydantic import BaseModel

from app.comum.autenticacao_cliente import (
    ContextoAcesso,
    aplicar_limite_taxa_se_cliente,
    exigir_permissao_ou_escopo,
)
from app.comum.limitador_taxa import exigir_limite_taxa_sessao
from app.core import contexto
from app.core.erros import RESPOSTAS_PADRAO, ErroDeAplicacao, NaoImplementado
from app.core.seguranca import Sujeito
from app.db.sessao import SessaoDb
from app.identidade.tenancy import servico
from app.schemas import contrato

roteador = APIRouter(tags=["tenants"])

# Uma instancia por par (permissao, escopo) usado no arquivo -- nunca uma
# chamada nova a `exigir_permissao_ou_escopo` dentro do handler (identidade
# estavel do *callable* pro cache de dependencia do FastAPI).
# Sem `_ACESSO_CRIAR` (`tenants.criar`/`tenants:escrever`): `criarTenant` --
# como `listarTenants` -- nao tem, e nunca teve, dependencia de autenticacao
# nenhuma (ver docstring dos dois handlers: sao `501` incondicionais ate uma
# fase desenhar o acesso cross-tenant do suporte da SEEG). Retrofitar um
# portao de auth num stub `501` so trocaria o `501` por `401` para quem chama
# sem credencial -- regressao de comportamento, sem ganho.
_ACESSO_LER = exigir_permissao_ou_escopo(permissao="tenants.ler", escopo="tenants:ler")
_ACESSO_EDITAR = exigir_permissao_ou_escopo(permissao="tenants.editar", escopo="tenants:escrever")
_ACESSO_CONFIGURAR = exigir_permissao_ou_escopo(
    permissao="tenants.configurar", escopo="tenants:escrever"
)

_SchemaT = TypeVar("_SchemaT", bound=BaseModel)


def _sujeito_para_servico(acesso: ContextoAcesso) -> Sujeito:
    """`Sujeito` a repassar para a camada de servico.

    `atualizar_tenant` e `definir_configuracao_tenant` recebem o `Sujeito`
    INTEIRO (nao so `usuario_id`): usam-no para `criado_por`/`atualizado_por`
    e para `registrar_auditoria_de_sujeito` (que le `tenant_id`/`usuario_id`/
    `email`/`perfis`/`delegacao_id`).

    Acesso humano devolve o proprio `Sujeito` resolvido, sem nenhuma
    alteracao (comportamento preservado byte a byte). Acesso de cliente de
    integracao devolve um `Sujeito` sintetico so com o `tenant_id` do
    cliente: sem `usuario_id`, sem perfis, sem delegacao -- nao ha usuario
    humano a quem atribuir a acao, e `registrar_auditoria_de_sujeito` exige
    apenas `tenant_id` nao-nulo. Mesmo helper (e mesma decisao) de
    `app/routers/admin.py`.
    """
    if acesso.sujeito is not None:
        return acesso.sujeito
    return Sujeito(tenant_id=acesso.tenant_id, autenticado=True)


def _para_schema(schema_cls: type[_SchemaT], origem: Any, **extras: Any) -> _SchemaT:
    """Converte um objeto ORM no schema pydantic do contrato.

    Mesmo helper de `app/routers/admin.py` (A3, T8): le, para cada campo
    declarado no schema, o atributo homonimo do objeto ORM (os models de
    `packages/contracts` usam os mesmos nomes de coluna dos schemas gerados).
    """
    dados = {nome: getattr(origem, nome, None) for nome in schema_cls.model_fields}
    dados.update(extras)
    return schema_cls.model_validate(dados)


async def _exigir_mesmo_tenant(
    tenant_id: Annotated[UUID, Path(alias="tenantId", description="Identificador do tenant.")],
) -> None:
    """Recusa acesso cross-tenant a um `{tenantId}` explicito, ANTES de
    consultar o banco e antes de qualquer verificacao de permissao.

    `contexto.tenant_atual()` e o UUID que `TenantMiddleware` (T2) resolveu a
    partir do `X-Tenant`/subdominio da requisicao corrente -- nao depende de
    sujeito autenticado. Tenant nao resolvido (string vazia) nao e responsa-
    bilidade desta funcao: `SessaoDb` (`app/db/sessao.py:obter_sessao`) recusa
    abrir sessao nesse caso com `PONTO-VAL-011`.
    """
    tenant_atual = contexto.tenant_atual()
    if tenant_atual and str(tenant_id) != tenant_atual:
        raise ErroDeAplicacao(
            "PONTO-TEN-004",
            contexto_log={"tenant_alvo": str(tenant_id), "tenant_atual": tenant_atual},
        )


@roteador.get(
    "/v1/tenants/atual",
    status_code=200,
    operation_id="obterTenantAtual",
    summary="Obter tenant corrente",
    responses=RESPOSTAS_PADRAO,
)
async def obter_tenant_atual(
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
) -> contrato.Tenant:
    """Obter tenant corrente.

    Publico dentro do tenant resolvido (sem `x-permissao` no contrato): a
    unica coisa que restringe a resposta a linha certa e a policy de RLS de
    `tenants` (compara `id`, a excecao documentada da tabela).
    """
    linha = await servico.obter_tenant_atual(sessao)
    return _para_schema(contrato.Tenant, linha)


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
    """Listar tenants.

    Cross-tenant por natureza (lista TODOS os tenants do SaaS): a role
    `ponto_app` usada por `app/db/sessao.py:obter_sessao` nao tem `BYPASSRLS`
    (so `ponto_suporte` tem, e essa role nao esta ligada ao ciclo padrao de
    requisicao). Continua `501` ate uma fase decidir o desenho do acesso do
    suporte da SEEG -- ver `docs/backlog.md`, item "F1 / A2".
    """
    raise NaoImplementado("listarTenants", fase="F1")


@roteador.post(
    "/v1/tenants",
    status_code=201,
    operation_id="criarTenant",
    summary="Criar tenant",
    responses=RESPOSTAS_PADRAO,
    dependencies=[Depends(exigir_limite_taxa_sessao())],
)
async def criar_tenant(
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    corpo: contrato.TenantCriar,
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
) -> contrato.Tenant:
    """Criar tenant.

    A propria linha ainda nao existe quando a requisicao chega: nao ha
    `app.tenant_id` para publicar antes do `INSERT` dentro do ciclo padrao de
    `obter_sessao` (que exige tenant JA resolvido). `migrations/seed_dev.py`
    resolve isso abrindo sua PROPRIA sessao administrativa fora do ciclo de
    requisicao -- decisao de desenho fora do escopo de T2, registrada em
    `docs/backlog.md` (item "F1 / A2") para quem desenhar o acesso do suporte
    da SEEG.
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
    _mesmo_tenant: Annotated[None, Depends(_exigir_mesmo_tenant)],
    sessao: SessaoDb,
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_LER)],
    response: Response,
    tenant_id: Annotated[UUID, Path(alias="tenantId", description="Identificador do tenant.")],
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
) -> contrato.Tenant:
    """Obter tenant.

    `_exigir_mesmo_tenant` recusa com `PONTO-TEN-004` antes mesmo de checar
    permissao ou consultar o banco quando `{tenantId}` diverge do tenant
    resolvido da requisicao -- a RLS barraria de qualquer forma (so a linha do
    tenant corrente e visivel), mas a recusa explicita evita depender so do
    "zero linha vira 404" para um caso que e, na pratica, uma tentativa de
    cruzar a fronteira do tenant.
    """
    await aplicar_limite_taxa_se_cliente(response, acesso)
    linha = await servico.obter_tenant(sessao, tenant_id=tenant_id)
    return _para_schema(contrato.Tenant, linha)


@roteador.patch(
    "/v1/tenants/{tenantId}",
    status_code=200,
    operation_id="atualizarTenant",
    summary="Atualizar tenant",
    responses=RESPOSTAS_PADRAO,
    dependencies=[Depends(exigir_limite_taxa_sessao())],
)
async def atualizar_tenant(
    _mesmo_tenant: Annotated[None, Depends(_exigir_mesmo_tenant)],
    sessao: SessaoDb,
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_EDITAR)],
    response: Response,
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
        ),
    ],
    tenant_id: Annotated[UUID, Path(alias="tenantId", description="Identificador do tenant.")],
    corpo: contrato.TenantAtualizar,
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
) -> contrato.Tenant:
    """Atualizar tenant.

    Mesma recusa cross-tenant explicita de `obterTenant`, agora tambem para
    ESCRITA: `{tenantId}` de outro tenant nao chega a acionar nenhum `UPDATE`.
    """
    await aplicar_limite_taxa_se_cliente(response, acesso)
    linha = await servico.atualizar_tenant(
        sessao, tenant_id=tenant_id, dados=corpo, sujeito=_sujeito_para_servico(acesso)
    )
    return _para_schema(contrato.Tenant, linha)


@roteador.get(
    "/v1/tenants/{tenantId}/configuracoes",
    status_code=200,
    operation_id="listarConfiguracoesTenant",
    summary="Listar configuracoes do tenant",
    responses=RESPOSTAS_PADRAO,
)
async def listar_configuracoes_tenant(
    _mesmo_tenant: Annotated[None, Depends(_exigir_mesmo_tenant)],
    sessao: SessaoDb,
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_LER)],
    response: Response,
    tenant_id: Annotated[UUID, Path(alias="tenantId", description="Identificador do tenant.")],
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
        str | None, Query(alias="categoria", description="Filtra por categoria de configuracao.")
    ] = None,
) -> contrato.ListaTenantConfiguracao:
    """Listar configuracoes do tenant."""
    await aplicar_limite_taxa_se_cliente(response, acesso)
    linhas, paginacao_bruta = await servico.listar_configuracoes_tenant(
        sessao, tenant_id=tenant_id, cursor=cursor, limite=limite, categoria=categoria
    )
    dados = [_para_schema(contrato.TenantConfiguracao, linha) for linha in linhas]
    return contrato.ListaTenantConfiguracao(
        dados=dados, paginacao=contrato.Paginacao.model_validate(paginacao_bruta)
    )


@roteador.put(
    "/v1/tenants/{tenantId}/configuracoes/{chave}",
    status_code=200,
    operation_id="definirConfiguracaoTenant",
    summary="Definir configuracao do tenant",
    responses=RESPOSTAS_PADRAO,
    dependencies=[Depends(exigir_limite_taxa_sessao())],
)
async def definir_configuracao_tenant(
    _mesmo_tenant: Annotated[None, Depends(_exigir_mesmo_tenant)],
    sessao: SessaoDb,
    acesso: Annotated[ContextoAcesso, Depends(_ACESSO_CONFIGURAR)],
    response: Response,
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            description="Chave de idempotencia da escrita, unica por cliente e por operacao logica, com validade de 24 horas. Repetir a chamada com a mesma chave e o mesmo corpo…",
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
) -> contrato.TenantConfiguracao:
    """Definir configuracao do tenant. Upsert por `(tenantId, chave)`

    (`tenants.configurar` -- RFC-002 opcao (a), a acao ja aceita pelo `CHECK`
    de `permissoes.acao`).
    """
    await aplicar_limite_taxa_se_cliente(response, acesso)
    linha = await servico.definir_configuracao_tenant(
        sessao, tenant_id=tenant_id, chave=chave, dados=corpo, sujeito=_sujeito_para_servico(acesso)
    )
    return _para_schema(contrato.TenantConfiguracao, linha)
