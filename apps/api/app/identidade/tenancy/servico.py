"""Regras de negocio de `obterTenantAtual`, `obterTenant`, `atualizarTenant`,
`listarConfiguracoesTenant` e `definirConfiguracaoTenant` (T2).

`listarTenants` e `criarTenant` NAO moram aqui: as duas sao necessariamente
CROSS-tenant (listar todos os tenants do SaaS; criar um tenant cuja propria
linha ainda nao existe) e por isso vivem em
`app.identidade.tenancy.servico_suporte`, que recebe a sessao de bypass
(`app/db/sessao_suporte.py`, role `ponto_app_suporte`) e grava auditoria de
acesso cross-tenant. Toda funcao DESTE modulo recebe a sessao normal
(`SessaoDb`, role `ponto_app_runtime`, sem `BYPASSRLS`) e depende da RLS para
o isolamento -- nenhuma delas deve passar a aceitar a sessao de suporte.

Cada funcao publica devolve o objeto ORM pronto para o `_para_schema` do
router converter no schema pydantic do contrato -- mesmo padrao de
`app.identidade.rbac.servico` (T8).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.erros import ErroDeAplicacao
from app.core.seguranca import Sujeito
from app.identidade.auditoria.hash_chain import registrar_auditoria_de_sujeito
from app.identidade.rbac import paginacao
from app.identidade.tenancy._contrato import contrato


async def obter_tenant_atual(sessao: AsyncSession) -> Any:
    """`SELECT * FROM tenants` sem NENHUM filtro de aplicacao.

    A policy de RLS de `tenants` compara `id` (nao `tenant_id`, a excecao
    documentada da tabela) com `current_setting('app.tenant_id')`: e ela, e so
    ela, quem restringe o resultado a uma unica linha, a do tenant corrente.
    """
    linha = (await sessao.execute(sa.select(contrato.Tenant))).scalar_one_or_none()
    if linha is None:
        # Defensivo: nao deveria acontecer -- `TenantMiddleware` (T2) ja
        # validou a existencia do tenant via `fn_resolve_tenant` antes de
        # `SessaoDb` publicar `app.tenant_id`.
        raise ErroDeAplicacao("PONTO-REC-001")
    return linha


async def obter_tenant(sessao: AsyncSession, *, tenant_id: UUID) -> Any:
    """Busca pela PK. `_exigir_mesmo_tenant` (router) ja recusou o caso
    cross-tenant antes de chegar aqui; a RLS barraria de qualquer forma."""
    linha = await sessao.get(contrato.Tenant, tenant_id)
    if linha is None:
        raise ErroDeAplicacao("PONTO-REC-001")
    return linha


_CAMPOS_TENANT_AUDITAVEIS = (
    "slug",
    "razao_social",
    "nome_exibicao",
    "documento",
    "plano",
    "status",
    "fuso_horario",
    "locale",
    "dominio_proprio",
    "limite_colaboradores",
    "data_contratacao",
    "data_cancelamento",
)


def _instantaneo_tenant(linha: Any) -> dict[str, Any]:
    return {campo: getattr(linha, campo, None) for campo in _CAMPOS_TENANT_AUDITAVEIS}


async def atualizar_tenant(
    sessao: AsyncSession, *, tenant_id: UUID, dados: Any, sujeito: Sujeito
) -> Any:
    linha = await sessao.get(contrato.Tenant, tenant_id)
    if linha is None:
        raise ErroDeAplicacao("PONTO-REC-001")

    valor_anterior = _instantaneo_tenant(linha)
    campos_enviados = dados.model_dump(exclude_unset=True, by_alias=False)
    for campo, valor in campos_enviados.items():
        if hasattr(valor, "value"):  # StrEnum (plano, status)
            valor = valor.value
        setattr(linha, campo, valor)
    await sessao.flush()

    await registrar_auditoria_de_sujeito(
        sessao,
        sujeito,
        evento="identidade.tenant.atualizado",
        entidade="tenants",
        entidade_id=linha.id,
        acao="atualizar",
        valor_anterior=valor_anterior,
        valor_novo=_instantaneo_tenant(linha),
    )
    return linha


async def listar_configuracoes_tenant(
    sessao: AsyncSession,
    *,
    tenant_id: UUID,
    cursor: str | None,
    limite: int | None,
    categoria: str | None,
) -> tuple[list[Any], dict[str, Any]]:
    consulta = sa.select(contrato.TenantConfiguracao).where(
        contrato.TenantConfiguracao.tenant_id == tenant_id
    )
    if categoria:
        consulta = consulta.where(contrato.TenantConfiguracao.categoria == categoria)
    return await paginacao.paginar(
        sessao,
        consulta,
        coluna_criado_em=contrato.TenantConfiguracao.criado_em,
        coluna_id=contrato.TenantConfiguracao.id,
        cursor=cursor,
        limite=limite,
    )


async def definir_configuracao_tenant(
    sessao: AsyncSession, *, tenant_id: UUID, chave: str, dados: Any, sujeito: Sujeito
) -> Any:
    """Upsert por `(tenant_id, chave)` -- `uq_tenant_configuracoes`.

    Uma configuracao `somente_leitura` existente so e alterada por quem ja
    passou por `exigir_permissao("tenants.configurar")`; nao ha um papel
    "super admin da SEEG" modelado em `Sujeito` nesta fase (nenhum PCF define
    esse conceito para o RBAC por tenant), entao o campo e gravado e devolvido
    tal como o contrato descreve, sem um portao adicional que o contrato nao
    especifica -- ver `docs/backlog.md` se uma fase futura precisar dele.
    """
    existente = await sessao.scalars(
        sa.select(contrato.TenantConfiguracao).where(
            contrato.TenantConfiguracao.tenant_id == tenant_id,
            contrato.TenantConfiguracao.chave == chave,
        )
    )
    linha = existente.first()
    valor_anterior = None
    if linha is None:
        linha = contrato.TenantConfiguracao(
            tenant_id=tenant_id,
            chave=chave,
            categoria=(dados.categoria.value if dados.categoria else "geral"),
            valor=dados.valor,
            descricao=dados.descricao,
            somente_leitura=bool(dados.somente_leitura),
            criado_por=sujeito.usuario_id,
        )
        sessao.add(linha)
        evento = "identidade.tenant_configuracao.criada"
    else:
        valor_anterior = {"valor": linha.valor, "descricao": linha.descricao}
        linha.categoria = dados.categoria.value if dados.categoria else linha.categoria
        linha.valor = dados.valor
        linha.descricao = dados.descricao
        linha.somente_leitura = bool(dados.somente_leitura)
        linha.atualizado_por = sujeito.usuario_id
        evento = "identidade.tenant_configuracao.atualizada"
    await sessao.flush()

    await registrar_auditoria_de_sujeito(
        sessao,
        sujeito,
        evento=evento,
        entidade="tenant_configuracoes",
        entidade_id=linha.id,
        # `auditoria.acao` NAO aceita "editar" (vocabulario proprio, distinto
        # de `permissoes.acao` -- ver `packages/contracts/schema.sql`,
        # CHECK de `auditoria`): so "criar"/"atualizar" fazem sentido aqui.
        acao=("criar" if valor_anterior is None else "atualizar"),
        valor_anterior=valor_anterior,
        valor_novo={"valor": linha.valor, "descricao": linha.descricao},
    )
    return linha
