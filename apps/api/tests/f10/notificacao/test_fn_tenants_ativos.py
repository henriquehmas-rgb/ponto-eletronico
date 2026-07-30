"""Prova de `fn_tenants_ativos()` (RFC-014, `packages/contracts/schema.sql`
seção 2) -- critério de aceite 11 estendido: `SECURITY DEFINER` cross-tenant
funciona pela role comum `ponto_app`, sem `app.tenant_id` publicado."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from tests.f10.notificacao.conftest import semear_tenant_minimo


async def test_fn_tenants_ativos_enumera_dois_tenants_diferentes_cross_tenant(
    sessao_notificacao: AsyncSession, engine_notificacao: AsyncEngine
) -> None:
    """Dois tenants `status='ativo'`, de contextos DIFERENTES, aparecem
    numa única chamada, por uma conexão que NUNCA publicou `app.tenant_id`
    -- mesma prova que F4/F6 já fizeram para as funções irmãs."""
    contexto_a = await semear_tenant_minimo(sessao_notificacao, sufixo="crossa")
    contexto_b = await semear_tenant_minimo(sessao_notificacao, sufixo="crossb")
    await sessao_notificacao.commit()

    # Conexao NOVA, propria, sem NENHUM `SET LOCAL app.tenant_id` -- exatamente
    # o cenario do cron (sem tenant de entrada).
    async with engine_notificacao.connect() as conexao:
        resultado = await conexao.execute(text("SELECT id, slug FROM fn_tenants_ativos()"))
        linhas = {(linha.id, linha.slug) for linha in resultado}

    assert (contexto_a.tenant_id, contexto_a.tenant_slug) in linhas
    assert (contexto_b.tenant_id, contexto_b.tenant_slug) in linhas


async def test_fn_tenants_ativos_nao_devolve_tenant_suspenso(
    sessao_notificacao: AsyncSession, engine_notificacao: AsyncEngine
) -> None:
    contexto_suspenso = await semear_tenant_minimo(
        sessao_notificacao, sufixo="suspenso", status_tenant="suspenso"
    )
    contexto_ativo = await semear_tenant_minimo(sessao_notificacao, sufixo="ativo2")
    await sessao_notificacao.commit()

    async with engine_notificacao.connect() as conexao:
        resultado = await conexao.execute(text("SELECT id FROM fn_tenants_ativos()"))
        ids = {linha.id for linha in resultado}

    assert contexto_ativo.tenant_id in ids
    assert contexto_suspenso.tenant_id not in ids


async def test_fn_tenants_ativos_expoe_so_id_e_slug(
    sessao_notificacao: AsyncSession, engine_notificacao: AsyncEngine
) -> None:
    """Prova de superfície mínima (PCF §2.10/§5): a função nunca devolve
    dado de domínio, só a identidade do tenant."""
    async with engine_notificacao.connect() as conexao:
        resultado = await conexao.execute(text("SELECT * FROM fn_tenants_ativos() LIMIT 0"))
        colunas = set(resultado.keys())
    assert colunas == {"id", "slug"}
