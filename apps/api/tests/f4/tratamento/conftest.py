"""Fixture local dos testes de `apuracao.tratamento` (T8/T9/T10, agente A3).

`apps/api/tests/f4/conftest.py` (a fixture COMPARTILHADA da fase inteira,
ownership exclusivo de A4, PCF §5) ainda não existe no momento em que este
módulo foi escrito -- os quatro agentes rodam em paralelo e T1 (A4) pode
concluir antes ou depois deste arquivo. Para não bloquear a suíte de A3 na
ordem de chegada, este `conftest.py` é uma cópia **local e independente**,
território exclusivo de `apps/api/tests/f4/tratamento/**` (ownership de A3),
que nunca edita nem substitui o arquivo compartilhado de A4. Ela replica
apenas a FORMA de bootstrap já estabelecida por `tests/f3/conftest.py`
(migração + role de LOGIN derivada do nome do banco + sessão por teste sob
RLS), nunca a lógica de negócio de outra fase.

Semente mínima por teste (escopo `function`, nunca reaproveitada entre
testes): 1 tenant, 1 empresa, 1 unidade (`America/Sao_Paulo`), 1 colaborador
com vínculo `apura_ponto=true`, e 1 `tipo_tratamento` de exemplo (categoria
`justificativa`) -- o suficiente para os testes de CRUD de tratamento (T8),
decisão (T9) e recálculo (T10) desta fase, sem depender de jornada/escala
(F3) nem de marcação real (F5): os testes que precisam de um resultado de
`apurar_dia` usam um substituto (`_apurar_dia_fake.py`, também território de
A3) em vez do motor real de A1, que é testado pelo golden dataset de A4.
"""

from __future__ import annotations

import asyncio
import os
import re
import secrets
import subprocess
import sys
import time
import uuid
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from datetime import date
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

_URL_PADRAO_LOCAL = "postgresql+asyncpg://ponto:ponto@localhost:5432/ponto"


def _url_superusuario() -> URL:
    bruta = os.environ.get("PONTO_TEST_DATABASE_URL", _URL_PADRAO_LOCAL)
    return make_url(bruta)


def _nome_role_login(url_super: URL) -> str:
    base = re.sub(r"[^a-z0-9_]", "_", (url_super.database or "ponto").lower())
    return f"ponto_f4_login_{base}"


@pytest.fixture(scope="session")
def url_login_sessao_tratamento() -> URL:
    """Migra o banco de teste e devolve a `URL` de conexão da role de LOGIN.

    Escopo `session` compartilhado por todo o subpacote `tests/f4/tratamento`
    -- `alembic upgrade head` só precisa rodar uma vez por sessão de pytest.
    """
    url_super = _url_superusuario()
    role_login = _nome_role_login(url_super)

    ambiente = dict(os.environ)
    ambiente["DATABASE_URL"] = url_super.render_as_string(hide_password=False)
    # alembic/env.py prioriza DATABASE_URL_SYNC sobre DATABASE_URL --
    # sem isto, o subprocess herda o DATABASE_URL_SYNC do ambiente (setado
    # pelo job do CI apontando para outro banco) e a migracao silenciosamente
    # aplica no banco ERRADO -- achado real, 2026-08-07, descoberto ao investigar
    # "relation ... does not exist" na primeira execucao real do CI.
    ambiente["DATABASE_URL_SYNC"] = url_super.set(
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
            "alembic upgrade head falhou ao preparar o banco de teste da F4/A3:\n"
            f"--- stdout ---\n{resultado.stdout}\n--- stderr ---\n{resultado.stderr}"
        )

    senha = secrets.token_urlsafe(24)
    dsn_super = url_super.set(drivername="postgresql").render_as_string(hide_password=False)
    with psycopg.connect(dsn_super, autocommit=True) as conexao, conexao.cursor() as cursor:
        cursor.execute(sql.SQL("SELECT 1 FROM pg_roles WHERE rolname = %s"), (role_login,))
        if cursor.fetchone():
            cursor.execute(
                sql.SQL("ALTER ROLE {} WITH LOGIN PASSWORD {}").format(
                    sql.Identifier(role_login), sql.Literal(senha)
                )
            )
        else:
            cursor.execute(
                sql.SQL("CREATE ROLE {} LOGIN PASSWORD {} IN ROLE ponto_app").format(
                    sql.Identifier(role_login), sql.Literal(senha)
                )
            )

    url_login = url_super.set(drivername="postgresql+asyncpg", username=role_login, password=senha)
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
async def engine_tratamento(url_login_sessao_tratamento: URL) -> AsyncIterator[AsyncEngine]:
    ultimo_erro: Exception | None = None
    for tentativa in range(8):
        engine = create_async_engine(
            url_login_sessao_tratamento, pool_pre_ping=True, connect_args={"timeout": 8}
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
    raise RuntimeError(f"Nao foi possivel abrir a engine de teste da F4/A3: {ultimo_erro}")


@pytest_asyncio.fixture
async def sessao_tratamento(engine_tratamento: AsyncEngine) -> AsyncIterator[AsyncSession]:
    fabrica = async_sessionmaker(engine_tratamento, expire_on_commit=False, autoflush=False)
    async with fabrica() as sessao:
        yield sessao
        await sessao.rollback()


async def aplicar_tenant_teste(sessao: AsyncSession, tenant_id: uuid.UUID) -> None:
    await sessao.execute(
        text("SELECT set_config('app.tenant_id', :tenant, true)"),
        {"tenant": str(tenant_id)},
    )


@dataclass(frozen=True, slots=True)
class ContextoTratamento:
    tenant_id: uuid.UUID
    empresa_id: uuid.UUID
    unidade_id: uuid.UUID
    colaborador_id: uuid.UUID
    vinculo_id: uuid.UUID
    tipo_tratamento_id: uuid.UUID


@pytest_asyncio.fixture
async def contexto_tratamento(sessao_tratamento: AsyncSession) -> ContextoTratamento:
    """Semeia 1 tenant, 1 empresa, 1 unidade, 1 colaborador+vínculo
    (`apura_ponto=true`) e 1 tipo de tratamento -- via `INSERT` direto,
    nunca pela API (mesmo padrão de `tests/f3/conftest.py`)."""
    sufixo = uuid.uuid4().hex[:10]
    tenant_id = uuid.uuid4()

    await aplicar_tenant_teste(sessao_tratamento, tenant_id)

    await sessao_tratamento.execute(
        text(
            "INSERT INTO tenants (id, slug, razao_social, nome_exibicao, status) "
            "VALUES (:id, :slug, :razao, :nome, 'ativo')"
        ),
        {
            "id": tenant_id,
            "slug": f"f4-a3-{sufixo}",
            "razao": "Tenant de teste F4/A3",
            "nome": "Tenant F4 A3",
        },
    )

    empresa_id = uuid.uuid4()
    cnpj = f"{secrets.randbelow(10**14):014d}"
    await sessao_tratamento.execute(
        text(
            "INSERT INTO empresas "
            "(id, tenant_id, tipo, cnpj, razao_social, nome_fantasia, uf, "
            " codigo_ibge_municipio, fuso_horario) "
            "VALUES (:id, :tenant_id, 'matriz', :cnpj, :razao, :fantasia, 'SP', "
            "        '3550308', 'America/Sao_Paulo')"
        ),
        {
            "id": empresa_id,
            "tenant_id": tenant_id,
            "cnpj": cnpj,
            "razao": "Empresa de Teste F4 A3 Ltda",
            "fantasia": "Empresa Teste F4 A3",
        },
    )

    unidade_id = uuid.uuid4()
    await sessao_tratamento.execute(
        text(
            "INSERT INTO unidades "
            "(id, tenant_id, empresa_id, codigo, nome, tipo, uf, codigo_ibge_municipio, "
            " fuso_horario, geocerca_obrigatoria) "
            "VALUES (:id, :tenant_id, :empresa_id, 'SEDE', 'Sede de Teste', 'sede', "
            "        'SP', '3550308', 'America/Sao_Paulo', FALSE)"
        ),
        {"id": unidade_id, "tenant_id": tenant_id, "empresa_id": empresa_id},
    )

    colaborador_id = uuid.uuid4()
    cpf = f"{secrets.randbelow(10**11):011d}"
    await sessao_tratamento.execute(
        text(
            "INSERT INTO colaboradores "
            "(id, tenant_id, empresa_id, matricula, cpf, nome_completo, status) "
            "VALUES (:id, :tenant_id, :empresa_id, :matricula, :cpf, :nome, 'ativo')"
        ),
        {
            "id": colaborador_id,
            "tenant_id": tenant_id,
            "empresa_id": empresa_id,
            "matricula": f"MAT-{sufixo}",
            "cpf": cpf,
            "nome": "Colaborador de Teste F4 A3",
        },
    )

    vinculo_id = uuid.uuid4()
    await sessao_tratamento.execute(
        text(
            "INSERT INTO vinculos "
            "(id, tenant_id, colaborador_id, empresa_id, unidade_id, matricula_esocial, "
            " tipo_vinculo, data_inicio, apura_ponto, status) "
            "VALUES (:id, :tenant_id, :colaborador_id, :empresa_id, :unidade_id, :esocial, "
            "        'empregado', :data_inicio, TRUE, 'ativo')"
        ),
        {
            "id": vinculo_id,
            "tenant_id": tenant_id,
            "colaborador_id": colaborador_id,
            "empresa_id": empresa_id,
            "unidade_id": unidade_id,
            "esocial": f"ESOC-{sufixo}",
            "data_inicio": date(2020, 1, 1),
        },
    )

    tipo_tratamento_id = uuid.uuid4()
    await sessao_tratamento.execute(
        text(
            "INSERT INTO tipos_tratamento "
            "(id, tenant_id, codigo, nome, categoria, exige_aprovacao, ativo) "
            "VALUES (:id, :tenant_id, :codigo, 'Justificativa de teste', 'justificativa', "
            "        TRUE, TRUE)"
        ),
        {"id": tipo_tratamento_id, "tenant_id": tenant_id, "codigo": f"JUST-{sufixo}"},
    )

    await sessao_tratamento.commit()
    await aplicar_tenant_teste(sessao_tratamento, tenant_id)

    return ContextoTratamento(
        tenant_id=tenant_id,
        empresa_id=empresa_id,
        unidade_id=unidade_id,
        colaborador_id=colaborador_id,
        vinculo_id=vinculo_id,
        tipo_tratamento_id=tipo_tratamento_id,
    )


_URL_REDIS_PADRAO_LOCAL = "redis://localhost:6379/0"


@pytest.fixture(scope="session")
def redis_teste_url() -> str:
    """`PONTO_TEST_REDIS_URL` (mesmo padrão de `tests/f2/importadores/conftest.py`,
    A3/F2) -- default local, nunca um ambiente real."""
    return os.environ.get("PONTO_TEST_REDIS_URL", _URL_REDIS_PADRAO_LOCAL)


@pytest.fixture
def apurar_dia_falso() -> Iterator[None]:
    """Ativa o substituto de `app.apuracao.dominio.servico.apurar_dia`
    (`_apurar_dia_fake.py`) pela duração do teste -- ver docstring daquele
    módulo sobre por que isto é necessário enquanto A1 roda em paralelo."""
    from tests.f4.tratamento._apurar_dia_fake import instalar_modulo_falso

    yield from instalar_modulo_falso()
