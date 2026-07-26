"""Confere que a fixture de RBAC (catalogo completo, dois tenants) sobe."""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker


async def test_tenants_resolvidos(tenant_a_id: uuid.UUID, tenant_b_id: uuid.UUID) -> None:
    assert tenant_a_id != tenant_b_id


async def test_catalogo_permissoes_completo(
    fabrica_sessoes: async_sessionmaker,
) -> None:
    async with fabrica_sessoes() as sessao:
        total = (await sessao.execute(sa.text("SELECT count(*) FROM permissoes"))).scalar_one()
    assert total >= 142
