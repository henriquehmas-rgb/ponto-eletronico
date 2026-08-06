"""Fixture de banco desta suíte (A2 -- Hardening). Mesmo padrão de
`tests/f13/conftest.py` (banco dedicado por agente, `PONTO_TEST_DATABASE_URL`
já aponta direto para ele, migração idempotente na primeira fixture de
sessão) -- self-contido, não importa de `tests.f13`/`tests.f1` (cada fase
mantém seu próprio bootstrap, mesmo padrão já duplicado por F1/F2/F5/F12/F13,
ver `docs/backlog.md` 2026-08-03).

Autenticação de teste por `dependency_overrides[obter_sujeito]`, não login
real via `/v1/auth/login` -- mesma técnica e mesma justificativa de
`tests/f11/conftest.py` ("esta fase não depende de tests/f1/conftest.py...
nem recria a infraestrutura pesada de par RS256 descartável só para
exercitar rota HTTP"): `app.core.seguranca.obter_sujeito` é o único ponto de
entrada do sujeito autenticado, sobrescrevê-lo continua exercitando o
roteador, a validação Pydantic, o RLS e agora também o
`IdempotenciaRetrofitMiddleware`/`exigir_limite_taxa_sessao` de ponta a
ponta -- só pula a cerimônia de JWT/RBAC, que já é testada por F1.
"""

from __future__ import annotations

import os
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
from httpx import ASGITransport, AsyncClient
from ponto_contracts import Tenant
from psycopg import sql
from sqlalchemy import text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.seguranca import AlcanceEfetivo, Sujeito

RAIZ_API = Path(__file__).resolve().parents[3]  # apps/api


@pytest_asyncio.fixture(autouse=True)
async def _redis_encerrado_por_teste() -> AsyncIterator[None]:
    """Autouse em TODA esta suíte (não só `test_limitador_taxa_sessao.py`):
    qualquer rota da amostra representativa (`empresas`, `colaboradores`
    etc.) agora passa por `exigir_limite_taxa_sessao`, que cria um cliente
    Redis global sob demanda (`app.comum.limitador_taxa._obter_cliente_
    redis`) -- inclusive nos testes de `test_idempotencia_middleware_http_
    e2e.py`, que não têm nada a ver com Redis à primeira vista. Sem encerrar
    esse cliente DENTRO do event loop do teste que o criou, o próximo teste
    (loop novo, `asyncio_default_fixture_loop_scope = "function"`) herda um
    cliente preso a um loop já fechado -- `RuntimeError: Event loop is
    closed` ao tentar fechar (mesma classe de bug já documentada em
    `docs/backlog.md`, 2026-08-03, para engine/Redis vazado entre testes)."""
    import app.comum.limitador_taxa as limitador_mod

    yield
    await limitador_mod._para_teste["encerrar_cliente_redis"]()


_URL_PADRAO_LOCAL = "postgresql+asyncpg://ponto:ponto@localhost:5432/ponto_f14_a2_local"


def _url_banco_teste() -> URL:
    bruta = os.environ.get("PONTO_TEST_DATABASE_URL", _URL_PADRAO_LOCAL)
    return make_url(bruta)


def _garantir_banco_existe(url_banco: URL) -> None:
    dsn_manutencao = (url_banco.set(drivername="postgresql", database="postgres")).render_as_string(
        hide_password=False
    )
    with psycopg.connect(dsn_manutencao, autocommit=True) as conexao, conexao.cursor() as cursor:
        cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", (url_banco.database,))
        if cursor.fetchone() is None:
            cursor.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(url_banco.database)))


def _aplica_migracao(url_banco: URL) -> None:
    ambiente = dict(os.environ)
    ambiente["DATABASE_URL"] = url_banco.render_as_string(hide_password=False)
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
            "alembic upgrade head falhou ao preparar o banco de teste de F14/A2:\n"
            f"--- stdout ---\n{resultado.stdout}\n--- stderr ---\n{resultado.stderr}"
        )


@pytest.fixture(scope="session")
def url_banco_f14a2() -> URL:
    url_banco = _url_banco_teste()
    _garantir_banco_existe(url_banco)
    _aplica_migracao(url_banco)

    dsn_sync = url_banco.set(drivername="postgresql").render_as_string(hide_password=False)
    ultimo_erro: Exception | None = None
    for tentativa in range(5):
        try:
            with psycopg.connect(dsn_sync, connect_timeout=5):
                pass
            break
        except Exception as exc:  # pragma: no cover - so em falha real de rede
            ultimo_erro = exc
            time.sleep(0.3 * (tentativa + 1))
    else:
        raise RuntimeError(
            f"Nao foi possivel conectar ao banco de teste apos 5 tentativas: {ultimo_erro}"
        )
    return url_banco


@pytest_asyncio.fixture
async def engine_f14a2(url_banco_f14a2: URL) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(url_banco_f14a2, pool_pre_ping=True, pool_size=8, max_overflow=4)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def sessao_f14a2(engine_f14a2: AsyncEngine) -> AsyncIterator[AsyncSession]:
    fabrica = async_sessionmaker(engine_f14a2, expire_on_commit=False, autoflush=False)
    async with fabrica() as sessao:
        yield sessao
        await sessao.rollback()


async def aplicar_tenant_teste(sessao: AsyncSession, tenant_id: uuid.UUID) -> None:
    await sessao.execute(
        text("SELECT set_config('app.tenant_id', :tenant, true)"), {"tenant": str(tenant_id)}
    )


@dataclass(frozen=True, slots=True)
class ContextoF14A2:
    tenant_id: uuid.UUID
    tenant_slug: str
    usuario_id: uuid.UUID


@pytest_asyncio.fixture
async def contexto_f14a2(sessao_f14a2: AsyncSession) -> ContextoF14A2:
    """Semeia (ou reaproveita) UM tenant real -- suficiente para as rotas de
    criação simples da amostra representativa (nenhuma delas depende de
    empresa/unidade pré-existente)."""
    tenant_id = uuid.uuid4()
    slug = f"f14a2-{uuid.uuid4().hex[:10]}"
    await sessao_f14a2.execute(
        text("SELECT set_config('app.tenant_id', :tid, true)"), {"tid": str(tenant_id)}
    )
    tenant = Tenant(
        id=tenant_id,
        slug=slug,
        razao_social="Tenant de teste F14/A2",
        nome_exibicao="Tenant F14 A2",
        status="ativo",
        plano="enterprise",
    )
    sessao_f14a2.add(tenant)
    await sessao_f14a2.flush()
    await sessao_f14a2.commit()
    return ContextoF14A2(tenant_id=tenant_id, tenant_slug=slug, usuario_id=uuid.uuid4())


def sujeito_de_teste(ctx: ContextoF14A2, *, permissoes: frozenset[str]) -> Sujeito:
    return Sujeito(
        usuario_id=ctx.usuario_id,
        tenant_id=ctx.tenant_id,
        email="teste-f14a2@exemplo.com",
        perfis=("perfil-teste-f14a2",),
        permissoes=permissoes,
        autenticado=True,
        alcance=AlcanceEfetivo(amplo_tenant=True),
    )


@pytest_asyncio.fixture
async def cliente_http_f14a2(
    url_banco_f14a2: URL, contexto_f14a2: ContextoF14A2
) -> AsyncIterator[AsyncClient]:
    """`AsyncClient` (via `ASGITransport`) contra a aplicação real, apontada
    para o banco desta suíte. `dependency_overrides[obter_sujeito]` é
    aplicado por cada teste (via `sobrescrever_sujeito`), não aqui -- o
    conjunto de permissões varia por rota exercitada."""
    from app.core.config import obter_configuracao
    from app.db.sessao import encerrar_engine
    from app.main import criar_aplicacao

    antigo = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url_banco_f14a2.render_as_string(hide_password=False)
    obter_configuracao.cache_clear()
    await encerrar_engine()
    try:
        aplicacao = criar_aplicacao()
        transporte = ASGITransport(app=aplicacao)
        async with AsyncClient(transport=transporte, base_url="http://test") as cliente:
            # Guardado como atributo dinâmico (não é API pública do httpx):
            # `sobrescrever_sujeito` precisa do `FastAPI.dependency_overrides`
            # do app real por trás deste cliente, e `AsyncClient` não expõe
            # isso de outra forma quando construído via `ASGITransport`.
            cliente._app_para_teste = aplicacao  # type: ignore[attr-defined]
            yield cliente
    finally:
        await encerrar_engine()
        if antigo is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = antigo
        obter_configuracao.cache_clear()


def sobrescrever_sujeito(cliente_http: AsyncClient, sujeito: Sujeito) -> None:
    from app.core.seguranca import obter_sujeito

    aplicacao = cliente_http._app_para_teste  # type: ignore[attr-defined]
    aplicacao.dependency_overrides[obter_sujeito] = lambda: sujeito


def cabecalhos(tenant_slug: str, *, idempotencia: str | None = None) -> dict[str, str]:
    return {
        "X-Tenant": tenant_slug,
        "Idempotency-Key": idempotencia or f"teste-f14a2-{uuid.uuid4()}",
    }
