"""Fixture local dos testes de `app.apuracao.banco_horas` (T5/T6/T7, A2).

`apps/api/tests/f4/conftest.py` (a fixture COMPARTILHADA da fase inteira,
ownership exclusivo de A4, PCF §5) ainda nao existe no momento em que este
modulo foi escrito -- os quatro agentes rodam em paralelo e T1 (A4) pode
concluir antes ou depois deste arquivo (mesma situacao documentada por
`tests/f4/tratamento/conftest.py`, A3, que chegou a mesma solucao). Para
nao bloquear a suite de A2 na ordem de chegada, este `conftest.py` e uma
copia LOCAL e INDEPENDENTE, territorio exclusivo de
`apps/api/tests/f4/banco_horas/**` (ownership de A2), que nunca edita nem
substitui o arquivo compartilhado de A4. Ela replica apenas a FORMA de
bootstrap ja estabelecida por `tests/f3/conftest.py` (migracao + role de
LOGIN derivada do nome do banco + sessao por teste sob RLS), nunca a logica
de negocio de outra fase.

Semente minima por teste (escopo `function`, nunca reaproveitada entre
testes): 1 tenant, 1 empresa, 1 unidade (`America/Sao_Paulo`), 1
colaborador com vinculo `apura_ponto=true`, 1 `bh_politicas` (regime
`individual`, `periodo_meses=6`) e 1 `bh_contas` (`codigo='normal'`,
`status='aberta'`) -- o suficiente para os testes de politicas/contas
(T5), extrato/lancamentos/consumo FIFO-LIFO (T6) e quitacao/tetos/
vencimento (T7) desta fase.
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
from collections.abc import AsyncIterator
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

#: Default de desenvolvimento local. So usado quando `PONTO_TEST_DATABASE_URL`
#: nao esta definida -- nunca aponta para banco de ambiente real.
_URL_PADRAO_LOCAL = "postgresql+asyncpg://ponto:ponto@localhost:5432/ponto"


def _url_superusuario() -> URL:
    bruta = os.environ.get("PONTO_TEST_DATABASE_URL", _URL_PADRAO_LOCAL)
    return make_url(bruta)


def _nome_role_login(url_super: URL) -> str:
    """Deriva o nome da role de LOGIN do nome do banco -- evita colisao de
    `ALTER ROLE PASSWORD` entre agentes da fase rodando em paralelo contra
    o mesmo cluster (cada um com seu proprio banco exclusivo)."""
    base = re.sub(r"[^a-z0-9_]", "_", (url_super.database or "ponto").lower())
    return f"ponto_f4_login_{base}"


@pytest.fixture(scope="session")
def url_login_sessao_banco_horas() -> URL:
    """Migra o banco de teste e devolve a `URL` de conexao da role de
    LOGIN. Escopo `session`: `alembic upgrade head` roda uma unica vez por
    sessao de pytest."""
    url_super = _url_superusuario()
    role_login = _nome_role_login(url_super)

    ambiente = dict(os.environ)
    ambiente["DATABASE_URL"] = url_super.render_as_string(hide_password=False)
    # alembic/env.py prioriza DATABASE_URL_SYNC sobre DATABASE_URL --
    # sem isto, o subprocess herda o DATABASE_URL_SYNC do ambiente (setado
    # pelo job do CI apontando para outro banco) e a migracao silenciosamente
    # aplica no banco ERRADO -- achado real, 2026-08-07, descoberto ao investigar
    # "relation ... does not exist" na primeira execucao real do CI.
    ambiente["DATABASE_URL_SYNC"] = url_super.set(drivername="postgresql+psycopg").render_as_string(
        hide_password=False
    )
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
            "alembic upgrade head falhou ao preparar o banco de teste da F4/A2:\n"
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
async def engine_banco_horas(url_login_sessao_banco_horas: URL) -> AsyncIterator[AsyncEngine]:
    """Engine assincrona por teste, autenticada como a role de LOGIN da
    fase. Reconecta algumas vezes: a primeira conexao de uma engine nova,
    atraves do tunel SSH ate a VPS, ocasionalmente falha uma vez por
    latencia de rede (mesmo padrao de `tests/f3/conftest.py`)."""
    ultimo_erro: Exception | None = None
    for tentativa in range(8):
        engine = create_async_engine(
            url_login_sessao_banco_horas, pool_pre_ping=True, connect_args={"timeout": 8}
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
    raise RuntimeError(f"Nao foi possivel abrir a engine de teste da F4/A2: {ultimo_erro}")


@pytest_asyncio.fixture
async def sessao_banco_horas(engine_banco_horas: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """Sessao assincrona por teste, autenticada como a role de LOGIN
    (nunca superusuario) -- RLS sempre ativa. O teste decide quando
    commitar."""
    fabrica = async_sessionmaker(engine_banco_horas, expire_on_commit=False, autoflush=False)
    async with fabrica() as sessao:
        yield sessao
        await sessao.rollback()


async def aplicar_tenant_teste(sessao: AsyncSession, tenant_id: uuid.UUID) -> None:
    """Publica `app.tenant_id` na transacao corrente, como
    `app/db/sessao.py` faz em producao."""
    await sessao.execute(
        text("SELECT set_config('app.tenant_id', :tenant, true)"),
        {"tenant": str(tenant_id)},
    )


@dataclass(frozen=True, slots=True)
class ContextoBancoHoras:
    """IDs da semente minima usada pelos testes de banco de horas."""

    tenant_id: uuid.UUID
    empresa_id: uuid.UUID
    unidade_id: uuid.UUID
    colaborador_id: uuid.UUID
    vinculo_id: uuid.UUID
    bh_politica_id: uuid.UUID
    bh_conta_id: uuid.UUID


async def semear_tenant_minimo(
    sessao: AsyncSession, *, sufixo: str | None = None
) -> ContextoBancoHoras:
    """Semeia 1 tenant, 1 empresa, 1 unidade, 1 colaborador+vinculo
    (`apura_ponto=true`), 1 `bh_politicas` (`individual`, 6 meses) e 1
    `bh_contas` (`normal`, `aberta`, periodo 2026-01-01..2026-06-30) -- via
    `INSERT` direto, nunca pela API (mesmo padrao de `tests/f3/conftest.py`).

    Funcao (nao fixture) para o teste de `fn_bh_contas_para_verificacao_
    vencimento()` (T7) poder chama-la duas vezes na mesma sessao, com
    tenants diferentes, e provar a enumeracao cross-tenant.

    `sufixo`, quando informado, e um ROTULO (nao o sufixo final): sempre
    combinado com um hex aleatorio, para o teste do cross-tenant (que
    COMITA de verdade, ao contrario dos demais testes desta fase que
    contam com o rollback do teardown) nunca colidir com `uq_tenants_slug`
    numa reexecucao da suite."""
    rotulo = f"{sufixo}-" if sufixo else ""
    sufixo = f"{rotulo}{uuid.uuid4().hex[:10]}"
    tenant_id = uuid.uuid4()

    await aplicar_tenant_teste(sessao, tenant_id)

    await sessao.execute(
        text(
            "INSERT INTO tenants (id, slug, razao_social, nome_exibicao, status) "
            "VALUES (:id, :slug, :razao, :nome, 'ativo')"
        ),
        {
            "id": tenant_id,
            "slug": f"f4-a2-{sufixo}",
            "razao": "Tenant de teste F4/A2",
            "nome": "Tenant F4 A2",
        },
    )

    empresa_id = uuid.uuid4()
    cnpj = f"{secrets.randbelow(10**14):014d}"
    await sessao.execute(
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
            "razao": "Empresa de Teste F4 A2 Ltda",
            "fantasia": "Empresa Teste F4 A2",
        },
    )

    unidade_id = uuid.uuid4()
    await sessao.execute(
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
    await sessao.execute(
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
            "nome": "Colaborador de Teste F4 A2",
        },
    )

    vinculo_id = uuid.uuid4()
    await sessao.execute(
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

    bh_politica_id = uuid.uuid4()
    await sessao.execute(
        text(
            "INSERT INTO bh_politicas "
            "(id, tenant_id, empresa_id, codigo, nome, regime, periodo_meses, "
            " metodo_consumo, vigencia_inicio, ativo) "
            "VALUES (:id, :tenant_id, :empresa_id, :codigo, 'Politica de teste', "
            "        'individual', 6, 'fifo', :vigencia_inicio, TRUE)"
        ),
        {
            "id": bh_politica_id,
            "tenant_id": tenant_id,
            "empresa_id": empresa_id,
            "codigo": f"POL-{sufixo}",
            "vigencia_inicio": date(2020, 1, 1),
        },
    )

    bh_conta_id = uuid.uuid4()
    await sessao.execute(
        text(
            "INSERT INTO bh_contas "
            "(id, tenant_id, colaborador_id, vinculo_id, bh_politica_id, codigo, nome, "
            " periodo_inicio, periodo_fim, status) "
            "VALUES (:id, :tenant_id, :colaborador_id, :vinculo_id, :bh_politica_id, "
            "        'normal', 'Banco de horas normal', :periodo_inicio, :periodo_fim, 'aberta')"
        ),
        {
            "id": bh_conta_id,
            "tenant_id": tenant_id,
            "colaborador_id": colaborador_id,
            "vinculo_id": vinculo_id,
            "bh_politica_id": bh_politica_id,
            "periodo_inicio": date(2026, 1, 1),
            "periodo_fim": date(2026, 6, 30),
        },
    )

    return ContextoBancoHoras(
        tenant_id=tenant_id,
        empresa_id=empresa_id,
        unidade_id=unidade_id,
        colaborador_id=colaborador_id,
        vinculo_id=vinculo_id,
        bh_politica_id=bh_politica_id,
        bh_conta_id=bh_conta_id,
    )


@pytest_asyncio.fixture
async def contexto_banco_horas(sessao_banco_horas: AsyncSession) -> ContextoBancoHoras:
    """Semeia a massa minima (ver `semear_tenant_minimo`) e comita, deixando
    `app.tenant_id` publicado para o corpo do teste."""
    contexto = await semear_tenant_minimo(sessao_banco_horas)
    await sessao_banco_horas.commit()
    await aplicar_tenant_teste(sessao_banco_horas, contexto.tenant_id)
    return contexto
