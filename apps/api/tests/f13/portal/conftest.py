"""Fixtures do subdiretorio `tests/f13/portal/` (agente A2, T7/T8).

Banco de teste EXCLUSIVO deste agente (`ponto_f13_a2`), mesmo padrao de
`tests/f5/conftest.py`: cria sob demanda a partir da conexao administrativa
apontada por `PONTO_TEST_DATABASE_URL`, migra, e cria uma role de LOGIN
propria (`ponto_f13_a2_login`, membro de `ponto_app`, NUNCA superusuario) --
os testes de isolamento entre tenants (T8, "sem nenhum dado real do tenant de
producao aparecer") so significam algo rodando sob RLS de verdade, nao como
superusuario.

Nomes de fixture com o sufixo `_f13_a2`, de proposito: `tests/f13/conftest.py`
(A1, ainda nao publicado no momento em que este arquivo foi escrito) e
`tests/f13/webhooks/conftest.py`/`tests/f13/folha/conftest.py`/etc. (outros
agentes) coexistem no mesmo processo pytest quando a suite inteira roda junto
-- nomes distintos evitam qualquer colisao de fixture entre agentes.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import subprocess
import sys
import time
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import psycopg
import pytest
import pytest_asyncio
import sqlalchemy as sa
from psycopg import sql
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

RAIZ_API = Path(__file__).resolve().parents[3]

_URL_PADRAO_LOCAL = "postgresql+asyncpg://ponto:ponto@localhost:5432/postgres"
_NOME_BANCO = "ponto_f13_a2"
_ROLE_LOGIN = "ponto_f13_a2_login"


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
            "alembic upgrade head falhou ao preparar o banco de teste da F13/A2:\n"
            f"--- stdout ---\n{resultado.stdout}\n--- stderr ---\n{resultado.stderr}"
        )


#: Mesmas duas linhas que `constantes.PERMISSOES_ADMIN_DEMO` espera encontrar
#: (so LEITURA, nunca escritas pela role de LOGIN -- ver nota em
#: `semear.py::_obter_permissao`). Semeadas aqui, com a conexao
#: ADMINISTRATIVA, porque `permissoes` tem `INSERT` revogado de `ponto_app`
#: pela propria migration (`schema.sql`, bloco de GRANTs) -- exatamente o
#: mesmo papel que `seed_dev.py::semeia_permissoes` cumpre num ambiente real.
_CATALOGO_MINIMO = (
    ("integracao", "api_clients", "criar"),
    ("integracao", "api_clients", "ler"),
)


def _semeia_catalogo_de_permissoes(url_admin_banco: URL) -> None:
    dsn_admin = url_admin_banco.set(drivername="postgresql").render_as_string(hide_password=False)
    with psycopg.connect(dsn_admin, autocommit=True) as conexao, conexao.cursor() as cursor:
        for modulo, recurso, acao in _CATALOGO_MINIMO:
            codigo = f"{recurso}.{acao}"
            cursor.execute("SELECT 1 FROM permissoes WHERE codigo = %s", (codigo,))
            if cursor.fetchone() is None:
                cursor.execute(
                    "INSERT INTO permissoes (codigo, recurso, acao, descricao, sensivel, modulo) "
                    "VALUES (%s, %s, %s, %s, FALSE, %s)",
                    (codigo, recurso, acao, f"[teste f13/a2] {codigo}", modulo),
                )


#: Senha FIXA (nao um segredo real: role de teste, banco so alcancavel pelo
#: tunel SSH da sessao, nunca exposta fora dele) deliberadamente estavel
#: entre execucoes -- ver nota do lock logo abaixo sobre por que uma senha
#: sorteada a cada fixture (o padrao de `tests/f5/conftest.py`) e insegura
#: quando varios processos `pytest tests/f13 -q` (sem escopar o
#: subdiretorio) recriam a MESMA role concorrentemente: o ultimo `ALTER ROLE`
#: a terminar "vence", derrubando a senha que um processo irmao acabou de
#: usar para autenticar -- reproduzido de verdade nesta sessao
#: ("password authentication failed for user ponto_f13_a2_login" depois de um
#: `CREATE ROLE`/`ALTER ROLE` bem-sucedido segundos antes). Senha estavel
#: elimina a janela: toda `CREATE`/`ALTER` concorrente converge para o MESMO
#: valor.
_SENHA_ROLE_LOGIN = hashlib.sha256(b"ponto_f13_a2_login_fixture_v1").hexdigest()


def _cria_ou_atualiza_role_login(url_admin_banco: URL) -> None:
    dsn_admin = url_admin_banco.set(drivername="postgresql").render_as_string(hide_password=False)
    with psycopg.connect(dsn_admin, autocommit=True) as conexao, conexao.cursor() as cursor:
        cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (_ROLE_LOGIN,))
        if cursor.fetchone():
            cursor.execute(
                sql.SQL("ALTER ROLE {} WITH LOGIN PASSWORD {}").format(
                    sql.Identifier(_ROLE_LOGIN), sql.Literal(_SENHA_ROLE_LOGIN)
                )
            )
        else:
            cursor.execute(
                sql.SQL("CREATE ROLE {} WITH LOGIN PASSWORD {} IN ROLE ponto_app").format(
                    sql.Identifier(_ROLE_LOGIN), sql.Literal(_SENHA_ROLE_LOGIN)
                )
            )


#: Chave fixa do `pg_advisory_lock` que serializa a preparacao do banco
#: exclusivo desta fase/agente. Existe porque `tests/f13/**` e uma arvore
#: compartilhada por dez agentes: rodar `pytest tests/f13 -q` (sem escopar o
#: subdiretorio) tambem coleta este `conftest.py` e dispara esta MESMA
#: fixture -- observado de verdade nesta sessao (dois processos python
#: concorrentes rodando `pytest tests/f13 -q`, um deles disparado por outro
#: agente/pelo orquestrador). Sem o lock, dois processos que chegam aqui ao
#: mesmo tempo colidem no `CREATE TABLE alembic_version` (unique violation) --
#: reproduzido e corrigido nesta sessao, nao e um risco hipotetico.
_CHAVE_LOCK_SETUP = "ponto_f13_a2_setup"


@pytest.fixture(scope="session")
def url_login_sessao_f13_a2() -> URL:
    url_admin = _url_administrativa()
    url_admin_banco = _garantir_banco_exclusivo(url_admin)

    dsn_lock = url_admin.set(drivername="postgresql").render_as_string(hide_password=False)
    with psycopg.connect(dsn_lock, autocommit=True) as conexao_lock:
        conexao_lock.execute("SELECT pg_advisory_lock(hashtext(%s))", (_CHAVE_LOCK_SETUP,))
        try:
            _aplica_migracao(url_admin_banco)
            _semeia_catalogo_de_permissoes(url_admin_banco)
            # A criacao/senha da role de LOGIN tambem entra no lock: com senha
            # FIXA (ver `_SENHA_ROLE_LOGIN`) isto e so para evitar a janela de
            # `CREATE ROLE` concorrente colidir com "role ja existe", nao para
            # proteger a senha em si (que e a mesma sempre).
            _cria_ou_atualiza_role_login(url_admin_banco)
        finally:
            conexao_lock.execute("SELECT pg_advisory_unlock(hashtext(%s))", (_CHAVE_LOCK_SETUP,))

    url_login = url_admin_banco.set(
        drivername="postgresql+asyncpg", username=_ROLE_LOGIN, password=_SENHA_ROLE_LOGIN
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
async def engine_f13_a2(url_login_sessao_f13_a2: URL) -> AsyncIterator[AsyncEngine]:
    ultimo_erro: Exception | None = None
    for tentativa in range(8):
        engine = create_async_engine(
            url_login_sessao_f13_a2,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=2,
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
    raise RuntimeError(f"Nao foi possivel abrir a engine de teste da F13/A2: {ultimo_erro}")


@pytest_asyncio.fixture
async def sessao_f13_a2(engine_f13_a2: AsyncEngine) -> AsyncIterator[AsyncSession]:
    fabrica = async_sessionmaker(engine_f13_a2, expire_on_commit=False, autoflush=False)
    async with fabrica() as sessao:
        yield sessao
        await sessao.rollback()


@pytest.fixture(scope="session")
def admin_engine_sync_f13_a2(url_login_sessao_f13_a2: URL) -> Iterator[sa.engine.Engine]:
    """Engine sincrona ADMINISTRATIVA contra o banco exclusivo desta fase/
    agente. Uso exclusivo do teste que precisa inspecionar `nsr_emissoes`/
    `webhook_entregas` de OUTRO tenant sem estar sob o `app.tenant_id` de
    ninguem (RLS bloquearia; aqui a verificacao E que a linha nao existe,
    entao precisa enxergar alem do proprio tenant)."""
    url_admin = _url_administrativa().set(database=_NOME_BANCO, drivername="postgresql+psycopg")
    dsn = url_admin.render_as_string(hide_password=False)
    engine = sa.create_engine(dsn, future=True)
    try:
        yield engine
    finally:
        engine.dispose()
