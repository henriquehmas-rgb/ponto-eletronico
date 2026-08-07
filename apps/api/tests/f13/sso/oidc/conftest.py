"""Fixture do subarvore `sso/oidc` da fase F13 (A9, T20/T21 -- ownership
exclusivo de A9, `apps/api/tests/f13/sso/oidc/**`). Deliberadamente SEPARADA
de `apps/api/tests/f13/conftest.py` (compartilhada da fase, criacao exclusiva
de A1, PCF F13 secao 5.2) -- mesmo padrao ja usado por
`apps/api/tests/f13/webhooks/conftest.py` (A3) e
`apps/api/tests/f13/folha/conftest.py` (A5): banco/role de teste exclusivos
deste agente, para nao ficar bloqueado esperando a fixture compartilhada.

Banco de teste EXCLUSIVO deste agente (`ponto_f13_a9`), criado sob demanda a
partir de `PONTO_TEST_DATABASE_URL` (conexao administrativa). Role de LOGIN
propria (`ponto_f13_a9_login`, membro de `ponto_app`, nunca superusuario) --
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
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from pathlib import Path

import psycopg
import pytest
import pytest_asyncio
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)
from psycopg import sql
from sqlalchemy import text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

RAIZ_API = Path(__file__).resolve().parents[4]

_URL_PADRAO_LOCAL = "postgresql+asyncpg://ponto:ponto@localhost:5432/postgres"
_NOME_BANCO = "ponto_f13_a9"
_ROLE_LOGIN = "ponto_f13_a9_login"


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
    # alembic/env.py prioriza DATABASE_URL_SYNC sobre DATABASE_URL --
    # sem isto, o subprocess herda o DATABASE_URL_SYNC do ambiente (setado
    # pelo job do CI apontando para outro banco) e a migracao silenciosamente
    # aplica no banco ERRADO -- achado real, 2026-08-07, descoberto ao investigar
    # "relation ... does not exist" na primeira execucao real do CI.
    ambiente["DATABASE_URL_SYNC"] = url_admin_banco.set(
        drivername="postgresql+psycopg"
    ).render_as_string(hide_password=False)
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
            "alembic upgrade head falhou ao preparar o banco de teste da F13/A9:\n"
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
def url_login_sessao_f13a9() -> URL:
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
async def engine_f13a9(url_login_sessao_f13a9: URL) -> AsyncIterator[AsyncEngine]:
    ultimo_erro: Exception | None = None
    for tentativa in range(8):
        engine = create_async_engine(
            url_login_sessao_f13a9,
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
    raise RuntimeError(f"Nao foi possivel abrir a engine de teste da F13/A9: {ultimo_erro}")


@pytest_asyncio.fixture
async def sessao_f13a9(engine_f13a9: AsyncEngine) -> AsyncIterator[AsyncSession]:
    fabrica = async_sessionmaker(engine_f13a9, expire_on_commit=False, autoflush=False)
    async with fabrica() as sessao:
        yield sessao
        await sessao.rollback()


async def aplicar_tenant_teste(sessao: AsyncSession, tenant_id: uuid.UUID) -> None:
    await sessao.execute(
        text("SELECT set_config('app.tenant_id', :tenant, true)"), {"tenant": str(tenant_id)}
    )


@pytest.fixture(scope="session", autouse=True)
def _chaves_rs256_sso_oidc(tmp_path_factory: pytest.TempPathFactory) -> Iterator[None]:
    """Par RS256 descartavel para `app.identidade.tokens.jwt` (o login OIDC
    emite o MESMO access/refresh token que `autenticar` -- ver `resolucao.py`).

    Mesma receita de `apps/api/tests/f1/autenticacao/conftest.py::_chaves_rs256`
    (duplicada de proposito: fixture de sessao de OUTRO subarvore de teste,
    fora do ownership desta fase/agente)."""
    from app.identidade.tokens import chaves as jwt_chaves

    diretorio = tmp_path_factory.mktemp("jwt-f13a9")
    chave_privada = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    caminho_privada = diretorio / "private.pem"
    caminho_publica = diretorio / "public.pem"
    caminho_privada.write_bytes(
        chave_privada.private_bytes(
            encoding=Encoding.PEM,
            format=PrivateFormat.PKCS8,
            encryption_algorithm=NoEncryption(),
        )
    )
    caminho_publica.write_bytes(
        chave_privada.public_key().public_bytes(
            encoding=Encoding.PEM, format=PublicFormat.SubjectPublicKeyInfo
        )
    )
    os.environ["JWT_PRIVATE_KEY_PATH"] = str(caminho_privada)
    os.environ["JWT_PUBLIC_KEY_PATH"] = str(caminho_publica)
    jwt_chaves.limpar_cache()
    yield
    jwt_chaves.limpar_cache()


#: Chave HS256 fixa para os testes -- nunca usada fora deste processo.
CHAVE_ESTADO_TESTE = secrets.token_hex(32)

#: Dominio de e-mail permitido para o provedor `google` no tenant semeado.
DOMINIO_GOOGLE_PERMITIDO = "empresa-teste-f13a9.com.br"

#: `tenant_id` (GUID) do Entra ID permitido no tenant semeado.
ENTRA_TENANT_ID_PERMITIDO = "11111111-2222-3333-4444-555555555555"


@dataclass(frozen=True, slots=True)
class ContextoSsoOidcF13:
    tenant_id: uuid.UUID
    usuario_id: uuid.UUID
    usuario_email: str


@pytest_asyncio.fixture
async def contexto_sso_oidc_f13a9(
    sessao_f13a9: AsyncSession, url_login_sessao_f13a9: URL, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[ContextoSsoOidcF13]:
    """Semeia 1 tenant, 1 usuario `ativo` (SEM credencial `sso` previa -- e o
    que os testes de `resolucao.py` vinculam) e a allowlist de SSO
    (`tenant_configuracoes`) para os dois provedores OIDC.

    Publica `DATABASE_URL`/`SSO_ESTADO_CHAVE_SECRETA` no ambiente e limpa o
    cache de `obter_configuracao` (mesma receita de
    `apps/api/tests/f13/webhooks/conftest.py::contexto_webhooks_f13a3`) --
    necessario porque `app.identidade.sso.oidc.estado`/`resolucao` leem a
    `Configuracao` do processo, nao um parametro de teste.

    `monkeypatch.setenv` (nunca `os.environ[...] =` direto): reverte
    `DATABASE_URL` automaticamente no teardown deste teste. Achado real ao
    rodar `pytest tests/f13` inteiro (nunca com este arquivo isolado): uma
    atribuicao direta sobrevive ao teste e "vaza" para qualquer arquivo que
    rode depois no MESMO processo (ex.: `tests/f13/sso/saml`, alfabeticamente
    apos `oidc`) -- a app global passaria a consultar o banco per-agente
    `ponto_f13_a9` em vez do banco que o teste seguinte realmente semeou,
    devolvendo "tenant nao encontrado" para um tenant que existe de verdade.
    """
    monkeypatch.setenv("DATABASE_URL", url_login_sessao_f13a9.render_as_string(hide_password=False))
    os.environ.setdefault("SSO_ESTADO_CHAVE_SECRETA", CHAVE_ESTADO_TESTE)
    os.environ.setdefault("SSO_GOOGLE_CLIENT_ID", "cliente-google-teste-f13a9")
    os.environ.setdefault("SSO_GOOGLE_CLIENT_SECRET", "segredo-google-teste-f13a9")
    os.environ.setdefault("SSO_ENTRA_CLIENT_ID", "cliente-entra-teste-f13a9")
    os.environ.setdefault("SSO_ENTRA_CLIENT_SECRET", "segredo-entra-teste-f13a9")

    from app.core.config import obter_configuracao

    obter_configuracao.cache_clear()

    sufixo = uuid.uuid4().hex[:10]
    tenant_id = uuid.uuid4()
    await aplicar_tenant_teste(sessao_f13a9, tenant_id)

    await sessao_f13a9.execute(
        text(
            "INSERT INTO tenants (id, slug, razao_social, nome_exibicao, status) "
            "VALUES (:id, :slug, :razao, :nome, 'ativo')"
        ),
        {
            "id": tenant_id,
            "slug": f"f13a9-{sufixo}",
            "razao": "Tenant de teste F13/A9",
            "nome": "Tenant F13 A9",
        },
    )

    usuario_id = uuid.uuid4()
    usuario_email = f"colaborador.{sufixo}@{DOMINIO_GOOGLE_PERMITIDO}"
    await sessao_f13a9.execute(
        text(
            "INSERT INTO usuarios (id, tenant_id, email, nome_completo, tipo, status) "
            "VALUES (:id, :tenant_id, :email, :nome, 'humano', 'ativo')"
        ),
        {
            "id": usuario_id,
            "tenant_id": tenant_id,
            "email": usuario_email,
            "nome": "Colaborador Teste F13 A9",
        },
    )

    for chave, valor, categoria in (
        ("sso.google.dominios_permitidos", f'["{DOMINIO_GOOGLE_PERMITIDO}"]', "integracao"),
        ("sso.entra_id.tenant_id", f'"{ENTRA_TENANT_ID_PERMITIDO}"', "integracao"),
    ):
        await sessao_f13a9.execute(
            text(
                "INSERT INTO tenant_configuracoes (tenant_id, categoria, chave, valor) "
                "VALUES (:tenant_id, :categoria, :chave, CAST(:valor AS jsonb))"
            ),
            {"tenant_id": tenant_id, "categoria": categoria, "chave": chave, "valor": valor},
        )

    await sessao_f13a9.commit()
    await aplicar_tenant_teste(sessao_f13a9, tenant_id)

    yield ContextoSsoOidcF13(
        tenant_id=tenant_id, usuario_id=usuario_id, usuario_email=usuario_email
    )
