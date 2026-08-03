"""Fixture do subarvore `webhooks` da fase F13 (A3, T9-T13 -- ownership
exclusivo de A3, `apps/api/tests/f13/webhooks/**`). Deliberadamente SEPARADA
de `apps/api/tests/f13/conftest.py` (compartilhada da fase, criacao
exclusiva de A1, PCF F13 secao 5.2) -- mesmo padrao ja usado por
`apps/api/tests/f13/folha/conftest.py` (A5): banco/role de teste exclusivos
deste agente, para nao ficar bloqueado esperando a fixture compartilhada.

Banco de teste EXCLUSIVO deste agente (`ponto_f13_a3`), criado sob demanda a
partir de `PONTO_TEST_DATABASE_URL` (conexao administrativa). Role de LOGIN
propria (`ponto_f13_a3_login`, membro de `ponto_app`, nunca superusuario) --
necessario para que RLS realmente se aplique nos testes.
"""

from __future__ import annotations

import asyncio
import os
import secrets
import subprocess
import sys
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path

import psycopg
import pytest
import pytest_asyncio
from psycopg import sql
from sqlalchemy import text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

RAIZ_API = Path(__file__).resolve().parents[3]

_URL_PADRAO_LOCAL = "postgresql+asyncpg://ponto:ponto@localhost:5432/postgres"
_NOME_BANCO = "ponto_f13_a3"
_ROLE_LOGIN = "ponto_f13_a3_login"


def _url_administrativa() -> URL:
    bruta = os.environ.get("PONTO_TEST_DATABASE_URL", _URL_PADRAO_LOCAL)
    return make_url(bruta)


def _garantir_banco_exclusivo(url_admin: URL) -> URL:
    dsn_manutencao = url_admin.set(drivername="postgresql").render_as_string(hide_password=False)
    with psycopg.connect(dsn_manutencao, autocommit=True) as conexao, conexao.cursor() as cursor:
        cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", (_NOME_BANCO,))
        if cursor.fetchone() is None:
            cursor.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(_NOME_BANCO)))
    return url_admin.set(database=_NOME_BANCO)


def _aplica_migracao(url_admin_banco: URL) -> None:
    ambiente = dict(os.environ)
    ambiente["DATABASE_URL"] = url_admin_banco.render_as_string(hide_password=False)
    resultado = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=str(RAIZ_API),
        env=ambiente,
        capture_output=True,
        text=True,
        check=False,
    )
    if resultado.returncode != 0:
        raise RuntimeError(
            "alembic upgrade head falhou ao preparar o banco de teste da F13/A3:\n"
            f"--- stdout ---\n{resultado.stdout}\n--- stderr ---\n{resultado.stderr}"
        )


def _cria_ou_atualiza_role_login(url_admin_banco: URL, senha: str) -> None:
    dsn_admin = url_admin_banco.set(drivername="postgresql").render_as_string(hide_password=False)
    with psycopg.connect(dsn_admin, autocommit=True) as conexao, conexao.cursor() as cursor:
        cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (_ROLE_LOGIN,))
        if cursor.fetchone():
            cursor.execute(
                sql.SQL("ALTER ROLE {} WITH LOGIN PASSWORD {}").format(
                    sql.Identifier(_ROLE_LOGIN), sql.Literal(senha)
                )
            )
        else:
            cursor.execute(
                sql.SQL("CREATE ROLE {} LOGIN PASSWORD {} IN ROLE ponto_app").format(
                    sql.Identifier(_ROLE_LOGIN), sql.Literal(senha)
                )
            )


@pytest.fixture(scope="session")
def url_login_sessao_f13a3() -> URL:
    url_admin = _url_administrativa()
    url_admin_banco = _garantir_banco_exclusivo(url_admin)
    _aplica_migracao(url_admin_banco)
    senha = secrets.token_urlsafe(24)
    _cria_ou_atualiza_role_login(url_admin_banco, senha)
    url_login = url_admin_banco.set(
        drivername="postgresql+asyncpg", username=_ROLE_LOGIN, password=senha
    )
    dsn_login = url_login.set(drivername="postgresql").render_as_string(hide_password=False)
    ultimo_erro: Exception | None = None
    for tentativa in range(5):
        try:
            with psycopg.connect(dsn_login, connect_timeout=5):
                pass
            break
        except Exception as exc:  # pragma: no cover - so em falha real de rede
            ultimo_erro = exc
            time.sleep(0.3 * (tentativa + 1))
    else:
        raise RuntimeError(
            f"Nao foi possivel validar a role de LOGIN apos 5 tentativas: {ultimo_erro}"
        )
    return url_login


@pytest_asyncio.fixture
async def engine_f13a3(url_login_sessao_f13a3: URL) -> AsyncIterator[AsyncEngine]:
    ultimo_erro: Exception | None = None
    for tentativa in range(8):
        engine = create_async_engine(
            url_login_sessao_f13a3,
            pool_pre_ping=True,
            pool_size=8,
            max_overflow=4,
            connect_args={"timeout": 8},
        )
        try:
            async with asyncio.timeout(10):
                async with engine.connect():
                    pass
        except Exception as exc:  # pragma: no cover - so em falha real de rede
            ultimo_erro = exc
            await engine.dispose()
            await asyncio.sleep(min(0.5 * (tentativa + 1), 3.0))
            continue
        try:
            yield engine
        finally:
            await engine.dispose()
        return
    raise RuntimeError(f"Nao foi possivel abrir a engine de teste da F13/A3: {ultimo_erro}")


@pytest_asyncio.fixture
async def sessao_f13a3(engine_f13a3: AsyncEngine) -> AsyncIterator[AsyncSession]:
    fabrica = async_sessionmaker(engine_f13a3, expire_on_commit=False, autoflush=False)
    async with fabrica() as sessao:
        yield sessao
        await sessao.rollback()


async def aplicar_tenant_teste(sessao: AsyncSession, tenant_id: uuid.UUID) -> None:
    await sessao.execute(
        text("SELECT set_config('app.tenant_id', :tenant, true)"), {"tenant": str(tenant_id)}
    )


def _sync_dsn(url_login: URL) -> str:
    return url_login.set(drivername="postgresql+psycopg").render_as_string(hide_password=False)


@dataclass(frozen=True, slots=True)
class ContextoWebhooksF13:
    tenant_id: uuid.UUID
    empresa_id: uuid.UUID
    api_client_id: uuid.UUID


@pytest_asyncio.fixture
async def contexto_webhooks_f13a3(
    sessao_f13a3: AsyncSession, url_login_sessao_f13a3: URL, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[ContextoWebhooksF13]:
    """Semeia 1 tenant, 1 empresa e 1 `api_clients` -- base minima para
    exercitar CRUD de `webhooks` e o fan-out de `webhook_entregas`.

    Tambem publica `PONTO_WEBHOOK_CHAVE_MESTRA` (se ainda ausente) e aponta
    `app.core.config` / `app.integracoes.webhooks.fan_out` para o MESMO
    banco de teste (via `DATABASE_URL`), para que o listener `after_commit`
    (que abre sua PROPRIA engine sincrona, independente da `sessao_f13a3`)
    escreva no banco de teste correto, nao no `localhost:5432` padrao de
    producao/dev.

    `monkeypatch.setenv` (nunca `os.environ[...] =` direto) -- mesma correcao
    de `tests/f13/sso/oidc/conftest.py::contexto_sso_oidc_f13a9`: uma
    atribuicao direta sobrevive ao teste e vazaria `DATABASE_URL` para
    qualquer arquivo que rode depois no mesmo processo `pytest tests/f13`.
    """
    os.environ.setdefault("PONTO_WEBHOOK_CHAVE_MESTRA", secrets.token_hex(32))
    monkeypatch.setenv("DATABASE_URL", url_login_sessao_f13a3.render_as_string(hide_password=False))
    # `app.core.config.obter_configuracao` e `functools.lru_cache` -- limpa
    # para reler `DATABASE_URL` acima, e reinicia a engine sincrona do
    # fan-out para nao reusar uma conexao presa a um DSN antigo.
    from app.core.config import obter_configuracao
    from app.integracoes.webhooks import fan_out

    obter_configuracao.cache_clear()
    fan_out.reiniciar_engine_sync_para_testes()

    sufixo = uuid.uuid4().hex[:10]
    tenant_id = uuid.uuid4()
    await aplicar_tenant_teste(sessao_f13a3, tenant_id)

    await sessao_f13a3.execute(
        text(
            "INSERT INTO tenants (id, slug, razao_social, nome_exibicao, status) "
            "VALUES (:id, :slug, :razao, :nome, 'ativo')"
        ),
        {
            "id": tenant_id,
            "slug": f"f13a3-{sufixo}",
            "razao": "Tenant de teste F13/A3",
            "nome": "Tenant F13 A3",
        },
    )

    empresa_id = uuid.uuid4()
    empresa_cnpj = str(uuid.uuid4().int)[:14].zfill(14)
    await sessao_f13a3.execute(
        text(
            "INSERT INTO empresas "
            "(id, tenant_id, tipo, cnpj, razao_social, nome_fantasia, uf, codigo_ibge_municipio) "
            "VALUES (:id, :tenant_id, 'matriz', :cnpj, :razao, :fantasia, 'GO', '5208707')"
        ),
        {
            "id": empresa_id,
            "tenant_id": tenant_id,
            "cnpj": empresa_cnpj,
            "razao": "Empresa de teste F13 A3 Ltda",
            "fantasia": "Empresa Teste F13 A3",
        },
    )

    api_client_id = uuid.uuid4()
    await sessao_f13a3.execute(
        text(
            "INSERT INTO api_clients "
            "(id, tenant_id, nome, client_id, tipo, ambiente, escopos, "
            " rate_limit_por_minuto, status) "
            "VALUES (:id, :tenant_id, :nome, :client_id, 'confidencial', 'sandbox', "
            "        ARRAY['webhooks:ler','webhooks:escrever']::text[], 600, 'ativo')"
        ),
        {
            "id": api_client_id,
            "tenant_id": tenant_id,
            "nome": f"Cliente de teste {sufixo}",
            "client_id": f"cli_{sufixo}",
        },
    )

    await sessao_f13a3.commit()
    await aplicar_tenant_teste(sessao_f13a3, tenant_id)

    yield ContextoWebhooksF13(
        tenant_id=tenant_id, empresa_id=empresa_id, api_client_id=api_client_id
    )

    fan_out.reiniciar_engine_sync_para_testes()


@pytest.fixture
def redis_teste_url() -> str:
    """Mesmo nome/padrao de `tests/f2/conftest.py::redis_teste_url` --
    `PONTO_TEST_REDIS_URL` (variavel exigida pelo PCF da fase para qualquer
    teste que precise de fila real)."""
    return os.environ.get("PONTO_TEST_REDIS_URL", "redis://localhost:6379/1")
