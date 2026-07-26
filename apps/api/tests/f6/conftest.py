"""Fixture de banco da fase F6 (agente A1): um tenant real sob RLS, com
empresa e unidade, para os testes de `app.terminais`.

Conecta como role de LOGIN restrita (`ponto_teste_f6_a1`, membro de
`ponto_app`, NUNCA superusuario -- mesma regra do PCF de F1: testar RLS
conectado como `ponto` mascararia o defeito que estes testes existem para
achar). O provisionamento (tenant/empresa/unidade) roda pela conexao
administrativa (`PONTO_TEST_DATABASE_URL`), a unica que tem privilegio para
inserir em `tenants` sem que `app.tenant_id` ja exista.
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
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

VARIAVEL_URL = "PONTO_TEST_DATABASE_URL"
URL_PADRAO = "postgresql+asyncpg://ponto:ponto@localhost:5432/ponto"

PAPEL_LOGIN = "ponto_teste_f6_a1"
SENHA_LOGIN = "teste-f6-a1-senha"

#: Chave mestra de teste para `app.terminais.cifra` (hex de 32 bytes,
#: descartavel, so vale neste processo de teste).
CHAVE_MESTRA_TESTE = "b" * 64


def url_admin() -> str:
    return os.environ.get(VARIAVEL_URL, URL_PADRAO).strip()


def _url_com_role(url: str, role: str, senha: str) -> str:
    partes = sa.engine.make_url(url)
    # `str(URL)` mascara a senha com "***" por padrao (protecao contra
    # vazamento em log) -- por isso `render_as_string(hide_password=False)`
    # e obrigatorio aqui, senao a conexao tenta autenticar com "***" literal.
    return partes.set(username=role, password=senha).render_as_string(hide_password=False)


@pytest.fixture(scope="session", autouse=True)
def _chave_mestra_terminal() -> None:
    os.environ.setdefault("PONTO_TERMINAL_CHAVE_MESTRA", CHAVE_MESTRA_TESTE)


@dataclass(frozen=True, slots=True)
class TenantSemeado:
    id: uuid.UUID
    empresa_id: uuid.UUID
    unidade_id: uuid.UUID


@pytest_asyncio.fixture
async def tenant_f6() -> AsyncIterator[TenantSemeado]:
    """Cria um tenant + empresa + unidade isolados desta fase, via conexao
    administrativa (bypassa RLS por ser o dono/superusuario da instancia de
    teste)."""
    engine = create_async_engine(url_admin())
    tenant_id = uuid.uuid4()
    empresa_id = uuid.uuid4()
    unidade_id = uuid.uuid4()
    slug = f"f6-a1-{tenant_id.hex[:8]}"
    async with engine.begin() as conexao:
        await conexao.execute(
            text(
                "INSERT INTO tenants (id, slug, razao_social, nome_exibicao, plano, status) "
                "VALUES (:id, :slug, 'F6 A1 Teste Ltda', 'F6 A1 Teste', 'padrao', 'ativo')"
            ),
            {"id": str(tenant_id), "slug": slug},
        )
        await conexao.execute(
            text("SELECT set_config('app.tenant_id', :tenant, true)"), {"tenant": str(tenant_id)}
        )
        await conexao.execute(
            text(
                "INSERT INTO empresas (id, tenant_id, razao_social, nome_fantasia, cnpj, ativo) "
                "VALUES (:id, :tenant_id, 'Empresa F6 A1', 'F6 A1', :cnpj, TRUE)"
            ),
            {"id": str(empresa_id), "tenant_id": str(tenant_id), "cnpj": _cnpj_de(tenant_id)},
        )
        await conexao.execute(
            text(
                "INSERT INTO unidades (id, tenant_id, empresa_id, codigo, nome, ativo) "
                "VALUES (:id, :tenant_id, :empresa_id, 'UN01', 'Unidade F6 A1', TRUE)"
            ),
            {"id": str(unidade_id), "tenant_id": str(tenant_id), "empresa_id": str(empresa_id)},
        )
    await engine.dispose()
    yield TenantSemeado(id=tenant_id, empresa_id=empresa_id, unidade_id=unidade_id)


def _cnpj_de(base: uuid.UUID) -> str:
    """CNPJ sintetico (so digitos, 14 caracteres) determinado pelo uuid --
    nao precisa passar validacao de digito verificador, `empresas.cnpj` do
    schema so exige o formato de 14 digitos."""
    digitos = "".join(c for c in base.hex if c.isdigit()) or "0"
    return (digitos * 2)[:14].rjust(14, "0")


@pytest_asyncio.fixture
async def _role_login() -> AsyncIterator[None]:
    engine = create_async_engine(url_admin())
    async with engine.begin() as conexao:
        existe = (
            await conexao.execute(
                text("SELECT 1 FROM pg_roles WHERE rolname = :nome"), {"nome": PAPEL_LOGIN}
            )
        ).first()
        senha_literal = SENHA_LOGIN.replace("'", "''")
        if existe is None:
            await conexao.execute(
                text(f"CREATE ROLE {PAPEL_LOGIN} LOGIN PASSWORD '{senha_literal}'")
            )
        else:
            await conexao.execute(
                text(f"ALTER ROLE {PAPEL_LOGIN} WITH LOGIN PASSWORD '{senha_literal}'")
            )
        await conexao.execute(text(f"GRANT ponto_app TO {PAPEL_LOGIN}"))
    await engine.dispose()
    yield


@pytest_asyncio.fixture
async def sessao_tenant(_role_login: None, tenant_f6: TenantSemeado) -> AsyncIterator[AsyncSession]:
    """Sessao conectada como `ponto_teste_f6_a1` (RLS normal), com
    `app.tenant_id` publicado para `tenant_f6`."""
    url = _url_com_role(url_admin(), PAPEL_LOGIN, SENHA_LOGIN)
    engine = create_async_engine(url, pool_pre_ping=True)
    fabrica = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    async with fabrica() as sessao:
        await sessao.execute(
            text("SELECT set_config('app.tenant_id', :tenant, true)"),
            {"tenant": str(tenant_f6.id)},
        )
        yield sessao
        await sessao.rollback()
    await engine.dispose()


@pytest_asyncio.fixture
async def engine_app_role() -> AsyncIterator[sa.ext.asyncio.AsyncEngine]:
    """Engine crua conectada como `ponto_teste_f6_a1`, para testes que
    precisam de conexoes/transacoes proprias (ex.: append-only)."""
    url = _url_com_role(url_admin(), PAPEL_LOGIN, SENHA_LOGIN)
    engine = create_async_engine(url, pool_pre_ping=True)
    yield engine
    await engine.dispose()
