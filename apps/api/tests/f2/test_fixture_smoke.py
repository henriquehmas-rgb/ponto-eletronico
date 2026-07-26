"""Prova de vida da fixture da fase (T1): banco migrado, role de LOGIN
operante sob RLS e semente organizacional minima presente.

Este arquivo nao pertence a nenhuma tag de negocio -- existe so para provar,
de forma isolada, que `conftest.py` cumpre o que o PCF exige antes que os
testes de `organizacao/` (T2..T4) comecem a depender dele.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.f2.conftest import ContextoOrganizacional, aplicar_tenant_teste


@pytest.mark.asyncio
async def test_fixture_semeia_tenant_duas_empresas_e_duas_unidades(
    contexto_organizacional: ContextoOrganizacional,
) -> None:
    assert contexto_organizacional.tenant_id is not None
    assert contexto_organizacional.empresa_matriz_id != contexto_organizacional.empresa_filial_id
    assert (
        contexto_organizacional.unidade_ponto_raio_id != contexto_organizacional.unidade_poligono_id
    )


@pytest.mark.asyncio
async def test_role_de_login_esta_sob_rls_e_nao_enxerga_outro_tenant(
    sessao_f2: AsyncSession,
    contexto_organizacional: ContextoOrganizacional,
) -> None:
    """A prova real de que a suite nao roda como superusuario: publicar um
    tenant diferente do semeado esconde a linha, mesmo que ela exista."""
    linha = (
        await sessao_f2.execute(
            text("SELECT id FROM tenants WHERE id = :id"),
            {"id": contexto_organizacional.tenant_id},
        )
    ).first()
    assert linha is not None

    await aplicar_tenant_teste(sessao_f2, uuid.uuid4())
    escondida = (
        await sessao_f2.execute(
            text("SELECT id FROM tenants WHERE id = :id"),
            {"id": contexto_organizacional.tenant_id},
        )
    ).first()
    assert escondida is None


@pytest.mark.asyncio
async def test_role_de_login_nao_e_superusuario_nem_bypassa_rls(
    sessao_f2: AsyncSession,
) -> None:
    linha = (
        await sessao_f2.execute(
            text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user")
        )
    ).first()
    assert linha is not None
    rolsuper, rolbypassrls = linha
    assert rolsuper is False
    assert rolbypassrls is False


@pytest.mark.asyncio
async def test_unidade_ponto_raio_e_poligono_tem_geocercas_distintas(
    sessao_f2: AsyncSession,
    contexto_organizacional: ContextoOrganizacional,
) -> None:
    linha_ponto = (
        await sessao_f2.execute(
            text(
                "SELECT geocerca_latitude, geocerca_raio_metros, geocerca_poligono "
                "FROM unidades WHERE id = :id"
            ),
            {"id": contexto_organizacional.unidade_ponto_raio_id},
        )
    ).first()
    assert linha_ponto is not None
    assert linha_ponto[0] is not None
    assert linha_ponto[1] == 100
    assert linha_ponto[2] is None

    linha_poligono = (
        await sessao_f2.execute(
            text(
                "SELECT geocerca_latitude, geocerca_raio_metros, geocerca_poligono "
                "FROM unidades WHERE id = :id"
            ),
            {"id": contexto_organizacional.unidade_poligono_id},
        )
    ).first()
    assert linha_poligono is not None
    assert linha_poligono[0] is None
    assert linha_poligono[1] is None
    assert linha_poligono[2] is not None
