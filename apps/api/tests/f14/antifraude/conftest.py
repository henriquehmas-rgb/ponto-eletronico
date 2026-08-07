"""Fixture da F14/A1 (score de confianca). Territorio exclusivo deste agente
(PCF F14 secao 3: `apps/api/tests/f14/antifraude/**`).

Banco de teste EXCLUSIVO deste agente (`ponto_f14_a1`). Convencao desta
sessao (instrucao do orquestrador, mesma de F13): `PONTO_TEST_DATABASE_URL`
JA aponta direto para o banco exclusivo (nao para uma conexao administrativa
em `postgres`) -- `DATABASE_URL` deve ser identica, para que a engine GLOBAL
do processo (`app.db.sessao`, usada pelo `TestClient` real em
`test_explicabilidade_http.py`) e a engine desta fixture apontem para o MESMO
banco.

Duas camadas de fixture, mesmo motivo que F2/F5/F13 ja documentaram: a suite
roda com `asyncio_default_fixture_loop_scope = "function"`
(`pyproject.toml`), e um recurso assincrono criado em escopo `session` nao
sobrevive ao proximo event loop.

1. `url_login_sessao_f14a1` (escopo `session`, sincrona): garante o banco e
   roda `alembic upgrade head`. Uma unica vez por sessao de pytest.
2. `engine_f14a1`/`sessao_f14a1` (escopo `function`, assincronas): cada teste
   ganha sua propria engine/sessao, presa ao event loop daquele teste.
3. `contexto_f14a1` (escopo `function`): semeia 1 tenant + 1 empresa + 1
   unidade (geocerca de ponto+raio, sede em Goiania/GO -- mesmas coordenadas
   de referencia que `tests/f5/conftest.py` ja usa, para os testes poderem
   calcular distancia/velocidade com numeros conhecidos) + 1 REP-P `ativo` +
   1 colaborador com vinculo `apura_ponto=true` ativo + 1 dispositivo
   `celular` com `dispositivo_vinculos` ativo.
"""

from __future__ import annotations

import asyncio
import datetime as dt
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

_URL_PADRAO_LOCAL = "postgresql+asyncpg://ponto:ponto@localhost:5432/ponto_f14_a1_local"

# Praca Civica, Goiania/GO -- mesma referencia de `tests/f5/conftest.py`.
GEOCERCA_LATITUDE = -16.6799
GEOCERCA_LONGITUDE = -49.255
GEOCERCA_RAIO_METROS = 100
GEOCERCA_TOLERANCIA_METROS = 50

# Ponto bem distante (Manaus/AM) -- usado pelos testes de velocidade
# impossivel: ~2000km da sede em poucos minutos.
LATITUDE_DISTANTE = -3.1190
LONGITUDE_DISTANTE = -60.0217


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
    # alembic/env.py prioriza DATABASE_URL_SYNC sobre DATABASE_URL --
    # sem isto, o subprocess herda o DATABASE_URL_SYNC do ambiente (setado
    # pelo job do CI apontando para outro banco) e a migracao silenciosamente
    # aplica no banco ERRADO -- achado real, 2026-08-07, descoberto ao investigar
    # "relation ... does not exist" na primeira execucao real do CI.
    ambiente["DATABASE_URL_SYNC"] = url_banco.set(
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
            "alembic upgrade head falhou ao preparar o banco de teste da F14/A1:\n"
            f"--- stdout ---\n{resultado.stdout}\n--- stderr ---\n{resultado.stderr}"
        )


@pytest.fixture(scope="session")
def url_login_sessao_f14a1() -> URL:
    url_banco = _url_banco_teste()
    _garantir_banco_existe(url_banco)
    _aplica_migracao(url_banco)

    dsn = url_banco.set(drivername="postgresql").render_as_string(hide_password=False)
    ultimo_erro: Exception | None = None
    for tentativa in range(5):
        try:
            with psycopg.connect(dsn, connect_timeout=5):
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
async def engine_f14a1(url_login_sessao_f14a1: URL) -> AsyncIterator[AsyncEngine]:
    ultimo_erro: Exception | None = None
    for tentativa in range(8):
        engine = create_async_engine(
            url_login_sessao_f14a1,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=4,
            connect_args={"timeout": 8},
        )
        try:
            async with asyncio.timeout(10), engine.connect():
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
    raise RuntimeError(f"Nao foi possivel abrir a engine de teste da F14/A1: {ultimo_erro}")


@pytest_asyncio.fixture
async def sessao_f14a1(engine_f14a1: AsyncEngine) -> AsyncIterator[AsyncSession]:
    fabrica = async_sessionmaker(engine_f14a1, expire_on_commit=False, autoflush=False)
    async with fabrica() as sessao:
        yield sessao
        await sessao.rollback()


async def aplicar_tenant_teste(sessao: AsyncSession, tenant_id: uuid.UUID) -> None:
    await sessao.execute(
        text("SELECT set_config('app.tenant_id', :tenant, true)"),
        {"tenant": str(tenant_id)},
    )


@dataclass(frozen=True, slots=True)
class ContextoF14A1:
    tenant_id: uuid.UUID
    tenant_slug: str
    empresa_id: uuid.UUID
    unidade_id: uuid.UUID
    rep_p_id: uuid.UUID
    colaborador_id: uuid.UUID
    colaborador_cpf: str
    colaborador_matricula: str
    vinculo_id: uuid.UUID
    dispositivo_id: uuid.UUID


@pytest_asyncio.fixture
async def contexto_f14a1(sessao_f14a1: AsyncSession) -> ContextoF14A1:
    """Semente minima: 1 tenant, 1 empresa, 1 unidade com geocerca, 1 REP-P
    ativo, 1 colaborador com vinculo ativo, 1 dispositivo celular vinculado.
    Cada chamada gera identificadores novos."""
    sufixo = uuid.uuid4().hex[:12]
    tenant_id = uuid.uuid4()
    tenant_slug = f"f14a1-{sufixo}"

    def _digitos(quantidade: int) -> str:
        return str(uuid.uuid4().int)[:quantidade].zfill(quantidade)

    await aplicar_tenant_teste(sessao_f14a1, tenant_id)

    await sessao_f14a1.execute(
        text(
            "INSERT INTO tenants (id, slug, razao_social, nome_exibicao, status) "
            "VALUES (:id, :slug, :razao, :nome, 'ativo')"
        ),
        {
            "id": tenant_id,
            "slug": tenant_slug,
            "razao": "Tenant de teste da F14/A1",
            "nome": "Tenant F14 A1",
        },
    )

    empresa_id = uuid.uuid4()
    empresa_cnpj = _digitos(14)
    await sessao_f14a1.execute(
        text(
            "INSERT INTO empresas "
            "(id, tenant_id, tipo, cnpj, razao_social, nome_fantasia, uf, codigo_ibge_municipio) "
            "VALUES (:id, :tenant_id, 'matriz', :cnpj, :razao, :fantasia, 'GO', '5208707')"
        ),
        {
            "id": empresa_id,
            "tenant_id": tenant_id,
            "cnpj": empresa_cnpj,
            "razao": "Empresa de teste F14/A1 Ltda",
            "fantasia": "Empresa Teste F14 A1",
        },
    )

    unidade_id = uuid.uuid4()
    await sessao_f14a1.execute(
        text(
            "INSERT INTO unidades "
            "(id, tenant_id, empresa_id, codigo, nome, tipo, uf, codigo_ibge_municipio, "
            " geocerca_latitude, geocerca_longitude, geocerca_raio_metros, "
            " geocerca_tolerancia_metros, geocerca_obrigatoria) "
            "VALUES (:id, :tenant_id, :empresa_id, 'SEDE', 'Sede de teste F14/A1', 'sede', 'GO', "
            "        '5208707', :lat, :lon, :raio, :tolerancia, TRUE)"
        ),
        {
            "id": unidade_id,
            "tenant_id": tenant_id,
            "empresa_id": empresa_id,
            "lat": GEOCERCA_LATITUDE,
            "lon": GEOCERCA_LONGITUDE,
            "raio": GEOCERCA_RAIO_METROS,
            "tolerancia": GEOCERCA_TOLERANCIA_METROS,
        },
    )

    rep_p_id = uuid.uuid4()
    hoje = dt.date.today()
    await sessao_f14a1.execute(
        text(
            "INSERT INTO rep_ps "
            "(id, tenant_id, empresa_id, identificador, tipo, numero_inpi, "
            " cnpj_desenvolvedor, razao_social_desenvolvedor, cnpj_empregador, "
            " razao_social_empregador, versao_programa, data_inicio_operacao, status) "
            "VALUES (:id, :tenant_id, :empresa_id, :identificador, 'rep_p', '12345678', "
            "        '60258502000149', 'SEEG Sistemas Ltda', :cnpj_empregador, "
            "        'Empresa de teste F14/A1 Ltda', '1.0.0-teste', :inicio, 'ativo')"
        ),
        {
            "id": rep_p_id,
            "tenant_id": tenant_id,
            "empresa_id": empresa_id,
            "identificador": f"REP-{sufixo}",
            "cnpj_empregador": empresa_cnpj,
            "inicio": hoje,
        },
    )
    await sessao_f14a1.execute(
        text(
            "INSERT INTO nsr_sequencias (id, tenant_id, rep_p_id, proximo_nsr, ultimo_nsr_emitido) "
            "VALUES (:id, :tenant_id, :rep_p_id, 1, 0)"
        ),
        {"id": uuid.uuid4(), "tenant_id": tenant_id, "rep_p_id": rep_p_id},
    )

    colaborador_id = uuid.uuid4()
    colaborador_cpf = _digitos(11)
    colaborador_matricula = sufixo[:10]
    await sessao_f14a1.execute(
        text(
            "INSERT INTO colaboradores "
            "(id, tenant_id, empresa_id, matricula, cpf, nome_completo, status, data_admissao) "
            "VALUES (:id, :tenant_id, :empresa_id, :matricula, :cpf, :nome, 'ativo', :admissao)"
        ),
        {
            "id": colaborador_id,
            "tenant_id": tenant_id,
            "empresa_id": empresa_id,
            "matricula": colaborador_matricula,
            "cpf": colaborador_cpf,
            "nome": "Colaborador de Teste F14/A1",
            "admissao": hoje - dt.timedelta(days=365),
        },
    )

    vinculo_id = uuid.uuid4()
    await sessao_f14a1.execute(
        text(
            "INSERT INTO vinculos "
            "(id, tenant_id, colaborador_id, empresa_id, matricula_esocial, tipo_vinculo, "
            " unidade_id, data_inicio, principal, apura_ponto, status) "
            "VALUES (:id, :tenant_id, :colaborador_id, :empresa_id, :matricula, 'empregado', "
            "        :unidade_id, :inicio, TRUE, TRUE, 'ativo')"
        ),
        {
            "id": vinculo_id,
            "tenant_id": tenant_id,
            "colaborador_id": colaborador_id,
            "empresa_id": empresa_id,
            "matricula": colaborador_matricula,
            "unidade_id": unidade_id,
            "inicio": hoje - dt.timedelta(days=365),
        },
    )

    dispositivo_id = uuid.uuid4()
    await sessao_f14a1.execute(
        text(
            "INSERT INTO dispositivos "
            "(id, tenant_id, empresa_id, unidade_id, tipo, plataforma, identificador, "
            " nome, status, attestation_status) "
            "VALUES (:id, :tenant_id, :empresa_id, :unidade_id, 'celular', 'android', "
            "        :identificador, 'Celular de teste F14/A1', 'ativo', 'aprovado')"
        ),
        {
            "id": dispositivo_id,
            "tenant_id": tenant_id,
            "empresa_id": empresa_id,
            "unidade_id": unidade_id,
            "identificador": f"android-{sufixo}",
        },
    )
    await sessao_f14a1.execute(
        text(
            "INSERT INTO dispositivo_vinculos "
            "(id, tenant_id, dispositivo_id, colaborador_id, status, aprovado_em) "
            "VALUES (:id, :tenant_id, :dispositivo_id, :colaborador_id, 'ativo', now())"
        ),
        {
            "id": uuid.uuid4(),
            "tenant_id": tenant_id,
            "dispositivo_id": dispositivo_id,
            "colaborador_id": colaborador_id,
        },
    )

    await sessao_f14a1.commit()
    await aplicar_tenant_teste(sessao_f14a1, tenant_id)

    return ContextoF14A1(
        tenant_id=tenant_id,
        tenant_slug=tenant_slug,
        empresa_id=empresa_id,
        unidade_id=unidade_id,
        rep_p_id=rep_p_id,
        colaborador_id=colaborador_id,
        colaborador_cpf=colaborador_cpf,
        colaborador_matricula=colaborador_matricula,
        vinculo_id=vinculo_id,
        dispositivo_id=dispositivo_id,
    )


def gerar_idempotency_key() -> str:
    return f"idem-f14a1-{secrets.token_hex(8)}"
