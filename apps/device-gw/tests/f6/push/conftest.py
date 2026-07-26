"""Fixtures de banco/Redis para os testes de `push`/T2/T4 (F6, agente A1).

Cria um terminal real (via conexao administrativa) sob RLS, e devolve a
configuracao do `device-gw` apontada para o banco/Redis de teste. Mesmo
padrao de `apps/api/tests/f6/conftest.py`: role de LOGIN restrita
(`ponto_teste_f6_a1`, ja criada por aquela fixture -- reaproveitada aqui) e
provisionamento pela conexao administrativa.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

VARIAVEL_URL = "PONTO_TEST_DATABASE_URL"
URL_PADRAO = "postgresql+asyncpg://ponto:ponto@localhost:5432/ponto"
VARIAVEL_REDIS = "PONTO_TEST_REDIS_URL"
REDIS_PADRAO = "redis://localhost:6379/7"

CHAVE_MESTRA_TESTE = "d" * 64
TOKEN_PUSH_GLOBAL_TESTE = "token-push-global-teste"  # noqa: S105 -- segredo de teste, descartavel


def url_admin() -> str:
    return os.environ.get(VARIAVEL_URL, URL_PADRAO).strip()


def redis_teste() -> str:
    return os.environ.get(VARIAVEL_REDIS, REDIS_PADRAO).strip()


@pytest.fixture(scope="session", autouse=True)
def _ambiente_device_gw() -> None:
    os.environ.setdefault("PONTO_TERMINAL_CHAVE_MESTRA", CHAVE_MESTRA_TESTE)
    os.environ["DATABASE_URL"] = url_admin()
    os.environ["REDIS_URL"] = redis_teste()
    os.environ["CONTROLID_PUSH_TOKEN"] = TOKEN_PUSH_GLOBAL_TESTE
    os.environ["CONTROLID_SIMULADOR"] = "true"
    from gateway.config import obter_configuracao

    obter_configuracao.cache_clear()


@dataclass(frozen=True, slots=True)
class TenantSemeado:
    id: uuid.UUID
    empresa_id: uuid.UUID
    unidade_id: uuid.UUID


def _cnpj_de(base: uuid.UUID) -> str:
    digitos = "".join(c for c in base.hex if c.isdigit()) or "0"
    return (digitos * 2)[:14].rjust(14, "0")


@pytest_asyncio.fixture
async def tenant_gw() -> AsyncIterator[TenantSemeado]:
    engine = create_async_engine(url_admin())
    tenant_id = uuid.uuid4()
    empresa_id = uuid.uuid4()
    unidade_id = uuid.uuid4()
    slug = f"f6-gw-{tenant_id.hex[:8]}"
    async with engine.begin() as conexao:
        await conexao.execute(
            text(
                "INSERT INTO tenants (id, slug, razao_social, nome_exibicao, plano, status) "
                "VALUES (:id, :slug, 'F6 GW Teste Ltda', 'F6 GW Teste', 'padrao', 'ativo')"
            ),
            {"id": str(tenant_id), "slug": slug},
        )
        await conexao.execute(
            text("SELECT set_config('app.tenant_id', :tenant, true)"), {"tenant": str(tenant_id)}
        )
        await conexao.execute(
            text(
                "INSERT INTO empresas (id, tenant_id, razao_social, nome_fantasia, cnpj, ativo) "
                "VALUES (:id, :tenant_id, 'Empresa F6 GW', 'F6 GW', :cnpj, TRUE)"
            ),
            {"id": str(empresa_id), "tenant_id": str(tenant_id), "cnpj": _cnpj_de(tenant_id)},
        )
        await conexao.execute(
            text(
                "INSERT INTO unidades (id, tenant_id, empresa_id, codigo, nome, ativo) "
                "VALUES (:id, :tenant_id, :empresa_id, 'UN01', 'Unidade F6 GW', TRUE)"
            ),
            {"id": str(unidade_id), "tenant_id": str(tenant_id), "empresa_id": str(empresa_id)},
        )
    await engine.dispose()
    yield TenantSemeado(id=tenant_id, empresa_id=empresa_id, unidade_id=unidade_id)


@dataclass(frozen=True, slots=True)
class TerminalSemeado:
    id: uuid.UUID
    tenant_id: uuid.UUID
    numero_serie: str
    dispositivo_id: uuid.UUID
    token_push: str | None


async def _criar_dispositivo(
    conexao: sa.ext.asyncio.AsyncConnection, tenant: TenantSemeado, identificador: str
) -> uuid.UUID:
    dispositivo_id = uuid.uuid4()
    await conexao.execute(
        text(
            "INSERT INTO dispositivos (id, tenant_id, empresa_id, unidade_id, tipo, plataforma, "
            "identificador, status) VALUES (:id, :tenant_id, :empresa_id, :unidade_id, 'terminal', "
            "'embarcado', :identificador, 'ativo')"
        ),
        {
            "id": str(dispositivo_id),
            "tenant_id": str(tenant.id),
            "empresa_id": str(tenant.empresa_id),
            "unidade_id": str(tenant.unidade_id),
            "identificador": identificador,
        },
    )
    return dispositivo_id


async def _criar_terminal(
    tenant: TenantSemeado,
    *,
    status: str = "ativo",
    token_push: str | None = None,
    numero_serie: str | None = None,
) -> TerminalSemeado:
    engine = create_async_engine(url_admin())
    numero_serie = numero_serie or f"IDF-TESTE-{uuid.uuid4().hex[:10]}"
    terminal_id = uuid.uuid4()
    async with engine.begin() as conexao:
        await conexao.execute(
            text("SELECT set_config('app.tenant_id', :tenant, true)"), {"tenant": str(tenant.id)}
        )
        dispositivo_id = await _criar_dispositivo(conexao, tenant, numero_serie)
        await conexao.execute(
            text(
                "INSERT INTO terminais (id, tenant_id, dispositivo_id, empresa_id, unidade_id, "
                "fabricante, numero_serie, modo_comunicacao, token_push, status) "
                "VALUES (:id, :tenant_id, :dispositivo_id, :empresa_id, :unidade_id, 'control_id', "
                ":numero_serie, 'push', :token_push, :status)"
            ),
            {
                "id": str(terminal_id),
                "tenant_id": str(tenant.id),
                "dispositivo_id": str(dispositivo_id),
                "empresa_id": str(tenant.empresa_id),
                "unidade_id": str(tenant.unidade_id),
                "numero_serie": numero_serie,
                "token_push": token_push,
                "status": status,
            },
        )
    await engine.dispose()
    return TerminalSemeado(
        id=terminal_id,
        tenant_id=tenant.id,
        numero_serie=numero_serie,
        dispositivo_id=dispositivo_id,
        token_push=token_push,
    )


@pytest_asyncio.fixture
async def terminal_ativo(tenant_gw: TenantSemeado) -> TerminalSemeado:
    """Terminal `ativo`, com `token_push` proprio."""
    return await _criar_terminal(tenant_gw, token_push="token-proprio-do-terminal")  # noqa: S106


@pytest_asyncio.fixture
async def terminal_inativo(tenant_gw: TenantSemeado) -> TerminalSemeado:
    return await _criar_terminal(tenant_gw, status="inativo", token_push="token-x")  # noqa: S106


@pytest_asyncio.fixture(autouse=True)
async def _limpar_redis() -> AsyncIterator[None]:
    from redis.asyncio import from_url

    cliente = from_url(redis_teste())
    await cliente.flushdb()
    yield
    await cliente.flushdb()
    await cliente.aclose()


@pytest_asyncio.fixture(autouse=True)
async def _engines_por_teste() -> AsyncIterator[None]:
    """Cada teste roda sob um event loop novo (`asyncio_default_fixture_loop_
    scope = function`). `gateway.dominio.bd`/`gateway.dominio.fila` cacheiam
    engine/cliente Redis em nivel de modulo; sem descarta-los entre testes, o
    segundo teste tenta reusar uma conexao presa ao loop fechado do primeiro
    -- mesmo problema documentado em `apps/api/app/db/sessao.py`, aqui coberto
    descartando no INICIO de cada teste (a engine se recria sozinha sob o loop
    novo, ver `bd.obter_engine`)."""
    from gateway.dominio import bd, fila

    await bd.encerrar_engine()
    await fila.encerrar_redis()
    yield
