"""Fixtures dos testes de autenticacao (F1/A1).

Ownership exclusivo deste arquivo: `apps/api/tests/f1/autenticacao/**`. NAO e
`apps/api/tests/f1/conftest.py` -- esse e exclusivo do agente A2 (fixture de
DOIS tenants para os testes de isolamento de RLS, T1 do PCF). Este conftest e
autossuficiente para os testes de autenticacao rodarem sozinhos
(`pytest apps/api/tests/f1/autenticacao -q`), inclusive antes da T1 do A2
existir -- e por isso repete, em miniatura, a mesma receita (migrar, criar a
role de LOGIN nao-superusuario, semear dado minimo).

**Ambiente.** Testes rodam contra um PostgreSQL 16 real (VPS, tunel SSH ja
aberto nesta maquina). A URL do SUPERUSUARIO de teste vem de
`PONTO_TEST_DATABASE_URL` (nunca hardcoded fora do default de conveniencia
local, e nunca versionada de verdade -- e um banco de teste descartavel).
Conectar como superusuario so acontece UMA VEZ, para criar a role de LOGIN sem
`BYPASSRLS` que os testes de verdade usam: testar RLS conectado como
superusuario nao prova nada, porque superusuario ignora a policy mesmo com
`FORCE ROW LEVEL SECURITY`.
"""

from __future__ import annotations

import datetime as dt
import os
import secrets
import uuid
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass

import asyncpg
import pytest
import pytest_asyncio
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from ponto_contracts import Credencial, Tenant, Usuario
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.db.sessao as db_sessao
from app.identidade.autenticacao.senha import gerar_hash
from app.identidade.mfa import cifra as mfa_cifra
from app.identidade.tokens import chaves as jwt_chaves

VARIAVEL_URL_TESTE = "PONTO_TEST_DATABASE_URL"
#: Mesmo default documentado no prompt de execucao do agente: banco de teste
#: exclusivo desta sessao, vazio, EXCLUSIVO deste agente.
_URL_PADRAO_LOCAL = (
    "postgresql+asyncpg://ponto:26d7258fc78331421f0ab6a021f3fba086f757b36b325fb7"
    "@127.0.0.1:15432/ponto_f1_a1"
)
NOME_ROLE_LOGIN = "ponto_app_login_f1_autenticacao"
SENHA_PADRAO_TESTE = "SenhaForteDeTeste123!"


def _url_superusuario() -> str:
    return os.environ.get(VARIAVEL_URL_TESTE, _URL_PADRAO_LOCAL)


def _asyncpg_dsn(url_sqlalchemy: str) -> str:
    """Converte `postgresql+asyncpg://...` no DSN puro que `asyncpg.connect` aceita."""
    return url_sqlalchemy.replace("postgresql+asyncpg://", "postgresql://", 1)


@pytest.fixture(scope="session")
def _url_role_app() -> Iterator[str]:
    """Cria (se preciso) a role de LOGIN nao-superusuario com `ponto_app` concedido.

    A senha e gerada por execucao (nunca hardcoded/versionada) e a role e
    reaproveitada entre execucoes -- `ALTER ROLE ... PASSWORD` reseta a senha
    para o valor desta execucao, e o `GRANT ponto_app` e idempotente.
    """
    dsn_super = _asyncpg_dsn(_url_superusuario())
    senha_role = secrets.token_urlsafe(24)

    async def _preparar() -> None:
        conexao = await asyncpg.connect(dsn_super)
        try:
            existe = await conexao.fetchval(
                "SELECT 1 FROM pg_roles WHERE rolname = $1", NOME_ROLE_LOGIN
            )
            # `ALTER/CREATE ROLE ... PASSWORD` e DDL: nao aceita parametro
            # vinculado ($1). A senha e gerada por `secrets.token_urlsafe`
            # (alfabeto seguro, sem aspas), entao a interpolacao aqui nao abre
            # brecha de injecao -- ainda assim usamos `quote_literal` do
            # proprio Postgres para nunca depender dessa premissa.
            senha_literal = await conexao.fetchval("SELECT quote_literal($1)", senha_role)
            if existe:
                await conexao.execute(
                    f'ALTER ROLE "{NOME_ROLE_LOGIN}" WITH LOGIN PASSWORD {senha_literal} '
                    "NOSUPERUSER NOBYPASSRLS"
                )
            else:
                await conexao.execute(
                    f'CREATE ROLE "{NOME_ROLE_LOGIN}" WITH LOGIN PASSWORD {senha_literal} '
                    "NOSUPERUSER NOBYPASSRLS"
                )
            await conexao.execute(f'GRANT ponto_app TO "{NOME_ROLE_LOGIN}"')
        finally:
            await conexao.close()

    import asyncio

    asyncio.run(_preparar())

    partes_super = _url_superusuario().split("@", 1)[1]  # host:porta/banco
    yield f"postgresql+asyncpg://{NOME_ROLE_LOGIN}:{senha_role}@{partes_super}"


@pytest.fixture(scope="session", autouse=True)
def _migrar_banco() -> None:
    """`alembic upgrade head` uma vez por sessao de teste, contra o banco exclusivo."""
    import subprocess
    import sys

    raiz_api = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    url_super = _url_superusuario()
    url_sync = url_super.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)
    ambiente = dict(os.environ)
    ambiente["DATABASE_URL_SYNC"] = url_sync
    ambiente["DATABASE_URL"] = url_super
    resultado = subprocess.run(  # noqa: S603 - comando fixo, sem entrada externa
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=raiz_api,
        env=ambiente,
        capture_output=True,
        text=True,
        check=False,
    )
    if resultado.returncode != 0:
        raise RuntimeError(
            "alembic upgrade head falhou:\n" f"stdout={resultado.stdout}\nstderr={resultado.stderr}"
        )


@pytest.fixture(scope="session")
def _chaves_rs256(tmp_path_factory: pytest.TempPathFactory) -> Iterator[None]:
    """Gera um par RS256 descartavel em disco e aponta a configuracao para ele."""
    diretorio = tmp_path_factory.mktemp("jwt")
    chave_privada = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    caminho_privada = diretorio / "private.pem"
    caminho_publica = diretorio / "public.pem"
    caminho_privada.write_bytes(
        chave_privada.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    caminho_publica.write_bytes(
        chave_privada.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    os.environ["JWT_PRIVATE_KEY_PATH"] = str(caminho_privada)
    os.environ["JWT_PUBLIC_KEY_PATH"] = str(caminho_publica)
    jwt_chaves.limpar_cache()
    yield
    jwt_chaves.limpar_cache()


@pytest.fixture(scope="session")
def _mfa_chave_mestra() -> Iterator[None]:
    os.environ["PONTO_MFA_CHAVE_MESTRA"] = secrets.token_hex(32)
    mfa_cifra.limpar_cache()
    yield
    mfa_cifra.limpar_cache()


@pytest.fixture(scope="session", autouse=True)
def _configurar_ambiente(
    _migrar_banco: None,
    _url_role_app: str,
    _chaves_rs256: None,
    _mfa_chave_mestra: None,
) -> Iterator[None]:
    """Aponta `Configuracao` (env var `DATABASE_URL`) para o banco de teste, via role de LOGIN.

    So a variavel de ambiente e fixada aqui (uma vez por sessao). A ENGINE em
    si (tanto a do proprio teste quanto a interna de `app/db/sessao.py`) e
    recriada a CADA TESTE por `_engine_isolada_por_teste`, porque conexoes
    asyncpg sao presas ao event loop em que nasceram e
    `asyncio_default_fixture_loop_scope = "function"` (`pyproject.toml`) cria
    um loop novo por teste -- reaproveitar uma engine entre loops fecha a
    conexao e derruba o teste seguinte com "Event loop is closed".
    """
    os.environ["DATABASE_URL"] = _url_role_app
    yield


@pytest_asyncio.fixture(autouse=True)
async def _engine_isolada_por_teste() -> AsyncIterator[None]:
    """Garante uma engine (e portanto uma conexao) nova por teste, presa ao loop do teste."""
    from app.core.config import obter_configuracao

    obter_configuracao.cache_clear()
    db_sessao._engine = None  # type: ignore[attr-defined]
    db_sessao._fabrica = None  # type: ignore[attr-defined]
    yield
    if db_sessao._engine is not None:  # type: ignore[attr-defined]
        await db_sessao.encerrar_engine()


@pytest_asyncio.fixture
async def sessao_db(
    _engine_isolada_por_teste: None, _url_role_app: str
) -> AsyncIterator[AsyncSession]:
    """`AsyncSession` como a role de LOGIN (nunca superusuario), presa ao loop do teste."""
    engine = create_async_engine(_url_role_app, pool_pre_ping=True)
    fabrica = async_sessionmaker(bind=engine, expire_on_commit=False)
    try:
        async with fabrica() as sessao:
            yield sessao
    finally:
        await engine.dispose()


@dataclass(frozen=True, slots=True)
class IdentidadeDeTeste:
    tenant_id: uuid.UUID
    tenant_slug: str
    usuario_id: uuid.UUID
    email: str
    senha: str


@pytest_asyncio.fixture
async def identidade(sessao_db: AsyncSession) -> IdentidadeDeTeste:
    """Um tenant novo com um usuario ativo e senha conhecida (Argon2id)."""
    tenant_id = uuid.uuid4()
    slug = f"f1a1-{secrets.token_hex(4)}"
    email = f"user-{secrets.token_hex(6)}@exemplo.com.br"

    await db_sessao.aplicar_tenant(sessao_db, str(tenant_id))
    sessao_db.add(
        Tenant(
            id=tenant_id,
            slug=slug,
            razao_social="Empresa de Teste F1/A1",
            nome_exibicao="Empresa de Teste F1/A1",
            status="ativo",
        )
    )
    await sessao_db.flush()

    usuario = Usuario(
        tenant_id=tenant_id,
        email=email,
        nome_completo="Usuario de Teste",
        tipo="humano",
        status="ativo",
        mfa_obrigatorio=False,
    )
    sessao_db.add(usuario)
    await sessao_db.flush()

    sessao_db.add(
        Credencial(
            tenant_id=tenant_id,
            usuario_id=usuario.id,
            tipo="senha",
            hash=gerar_hash(SENHA_PADRAO_TESTE),
            algoritmo="argon2id",
            ativo=True,
            ultima_troca_em=dt.datetime.now(dt.UTC),
        )
    )
    await sessao_db.commit()

    return IdentidadeDeTeste(
        tenant_id=tenant_id,
        tenant_slug=slug,
        usuario_id=usuario.id,
        email=email,
        senha=SENHA_PADRAO_TESTE,
    )


@pytest.fixture
def cliente() -> Iterator[TestClient]:
    from app.main import app

    with TestClient(app, raise_server_exceptions=True) as cliente_de_teste:
        yield cliente_de_teste


def cabecalhos(tenant_slug: str, *, idempotencia: str | None = None) -> dict[str, str]:
    return {
        "X-Tenant": tenant_slug,
        "Idempotency-Key": idempotencia or secrets.token_urlsafe(16),
    }
