"""Fixture de banco dos testes de RBAC e auditoria (T8/T9/T10, F1/A3).

Escopo deste `conftest.py`: SOMENTE `tests/f1/rbac/**` (ownership exclusivo
desta fase/agente). Deliberadamente NAO depende de `tests/f1/conftest.py`
(ownership exclusivo de F1/A2, evoluindo em paralelo nesta mesma janela) --
os testes de RBAC precisam poder rodar sozinhos, sem acoplar ao estado de um
arquivo que outro agente esta editando ao mesmo tempo.

Conecta contra o PostgreSQL 16 real apontado por `PONTO_TEST_DATABASE_URL`
(default: a instancia de teste da VPS, isolada, exclusiva deste agente).
Dois papeis de banco distintos:

* O USUARIO DA PROPRIA URL (superusuario nesta instancia de teste) -- so para
  provisionar: migrar, criar a role de login e semear o catalogo GLOBAL de
  permissoes (que a role da aplicacao nao pode INSERIR, ver `schema.sql`
  secao 20).
* `ponto_app_login`, role de LOGIN NAO-superusuario criada aqui (idempotente,
  `GRANT ponto_app`) -- e a UNICA role sob a qual os testes de RLS rodam.
  Nunca conectamos como superusuario para testar RLS: superusuario ignora a
  policy mesmo com `FORCE`, e um teste que rodasse assim nao provaria nada.
"""

from __future__ import annotations

import os
import secrets
import subprocess
import sys
import uuid
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session as SessaoSincrona

_RAIZ_API = Path(__file__).resolve().parents[3]
if str(_RAIZ_API / "migrations") not in sys.path:
    sys.path.insert(0, str(_RAIZ_API / "migrations"))

import seed_dev  # noqa: E402 -- import apos ajustar sys.path, ver acima

VARIAVEL_URL = "PONTO_TEST_DATABASE_URL"
URL_PADRAO_LOCAL = "postgresql+asyncpg://ponto:ponto@localhost:5432/ponto"
_ROLE_LOGIN = "ponto_app_login"
_SENHA_ROLE_LOGIN = "testeSomenteLocal_2026"


def _url_bruta() -> URL:
    return make_url(os.environ.get(VARIAVEL_URL, URL_PADRAO_LOCAL).strip())


def _url_async(url: URL) -> URL:
    if url.drivername in ("postgresql+psycopg", "postgresql", "postgres"):
        return url.set(drivername="postgresql+asyncpg")
    return url


def _url_sync(url: URL) -> URL:
    if url.drivername in ("postgresql+asyncpg", "postgres+asyncpg", "postgresql"):
        return url.set(drivername="postgresql+psycopg")
    return url


@pytest.fixture(scope="session")
def preparar_banco() -> dict[str, Any]:
    """Roda uma vez por sessao: migra, cria a role de login e semeia dois tenants
    com o catalogo GLOBAL completo de permissoes (`seed_dev.semeia`).

    Sincrono de proposito (psycopg + subprocess do Alembic): nao depende de
    nenhum event loop de asyncio, o que evita a engine assincrona presa a um
    loop ja encerrado quando fixtures de escopos diferentes se misturam.
    """
    url_admin_sync = _url_sync(_url_bruta())

    ambiente = dict(os.environ)
    ambiente["DATABASE_URL_SYNC"] = url_admin_sync.render_as_string(hide_password=False)
    subprocess.run(  # noqa: S603 -- argv fixo (sys.executable + literais), sem input externo
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=str(_RAIZ_API),
        env=ambiente,
        check=True,
        capture_output=True,
        text=True,
    )

    engine_admin = sa.create_engine(url_admin_sync, future=True)
    try:
        with engine_admin.begin() as conexao:
            existe = conexao.execute(
                sa.text("SELECT 1 FROM pg_roles WHERE rolname = :nome"), {"nome": _ROLE_LOGIN}
            ).first()
            senha_literal = _SENHA_ROLE_LOGIN.replace("'", "''")
            if existe is None:
                conexao.execute(
                    sa.text(f"CREATE ROLE {_ROLE_LOGIN} LOGIN PASSWORD '{senha_literal}'")
                )
            conexao.execute(sa.text(f"GRANT ponto_app TO {_ROLE_LOGIN}"))

        tenant_ids: dict[str, uuid.UUID] = {}
        for slug, email, cnpj in (
            ("tenant-a", "admin.seed@tenant-a.f1a3.local", "60258502000149"),
            ("tenant-b", "admin.seed@tenant-b.f1a3.local", "11222333000181"),
        ):
            resumo = seed_dev.Resumo()
            senha_admin = "Senha-Seed-F1A3-" + secrets.token_urlsafe(8)
            with SessaoSincrona(engine_admin) as sessao, sessao.begin():
                tenant_id = seed_dev.semeia(
                    sessao,
                    slug=slug,
                    razao_social=f"Tenant de teste {slug} (F1/A3)",
                    cnpj=cnpj,
                    admin_email=email,
                    admin_nome=f"Admin seed {slug}",
                    senha=senha_admin,
                    resumo=resumo,
                )
            tenant_ids[slug] = tenant_id
    finally:
        engine_admin.dispose()

    url_async = _url_async(_url_bruta())
    url_login_async = url_async.set(username=_ROLE_LOGIN, password=_SENHA_ROLE_LOGIN)
    return {
        "tenant_a_id": tenant_ids["tenant-a"],
        "tenant_b_id": tenant_ids["tenant-b"],
        "url_login_async": url_login_async.render_as_string(hide_password=False),
    }


@pytest.fixture(scope="session")
def tenant_a_id(preparar_banco: dict[str, Any]) -> uuid.UUID:
    return preparar_banco["tenant_a_id"]


@pytest.fixture(scope="session")
def tenant_b_id(preparar_banco: dict[str, Any]) -> uuid.UUID:
    return preparar_banco["tenant_b_id"]


@pytest_asyncio.fixture
async def engine(preparar_banco: dict[str, Any]) -> AsyncIterator[AsyncEngine]:
    """Engine assincrona nova POR TESTE: cada teste `async def` do pytest-asyncio
    em modo `function` tem seu proprio event loop, e uma engine asyncpg presa a
    um loop encerrado explode no proximo teste com "Event loop is closed".

    Pool deliberadamente PEQUENO: esta instancia de teste (`max_connections`)
    e compartilhada por todos os agentes da Onda 1 rodando em paralelo na
    mesma VPS -- um pool largo aqui derruba os outros com
    `TooManyConnectionsError`. O teste de concorrencia do hash chain (T10)
    respeita este limite com um `asyncio.Semaphore` do lado do teste, e nao
    com um pool grande do lado da engine.
    """
    eng = create_async_engine(
        preparar_banco["url_login_async"], pool_pre_ping=True, pool_size=5, max_overflow=5
    )
    try:
        yield eng
    finally:
        await eng.dispose()


@pytest.fixture
def fabrica_sessoes(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


@pytest.fixture(scope="session")
def admin_engine_sync(preparar_banco: dict[str, Any]) -> Iterator[sa.engine.Engine]:
    """Engine SINCRONA conectada como o usuario administrativo (superusuario
    nesta instancia de teste), reservada para os testes de T10 que precisam
    simular uma remocao adversarial de linha de `auditoria` -- desligando o
    gatilho `trg_auditoria_bloqueia_delete` de proposito, o que so o dono da
    tabela ou um superusuario pode fazer. NUNCA use esta engine para testar
    RLS: superusuario ignora a policy mesmo com `FORCE`."""
    eng = sa.create_engine(_url_sync(_url_bruta()), future=True)
    try:
        yield eng
    finally:
        eng.dispose()


async def aplicar_tenant(sessao: AsyncSession, tenant_id: uuid.UUID) -> None:
    """Mesmo mecanismo de `app/db/sessao.py:aplicar_tenant` -- `SET LOCAL app.tenant_id`."""
    await sessao.execute(
        sa.text("SELECT set_config('app.tenant_id', :tenant, true)"), {"tenant": str(tenant_id)}
    )
