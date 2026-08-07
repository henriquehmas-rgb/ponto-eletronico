"""Fixture do teste de performance (T12, agente A4).

Bootstrap PROPRIO deste subpacote (`apps/api/tests/f4/performance/**`,
ownership exclusivo de A4), mesma FORMA de bootstrap do resto da fase
(migracao + role de LOGIN nao-superusuario derivada do nome do banco +
sessao sob RLS). Reaproveita a mesma jornada fixa simples de `tests/f4/
propriedade/conftest.py` (08:00-17:00, 1h de intervalo, seg-sex util,
sabado folga, domingo DSR), replicada aqui em vez de importada: sao
subpacotes irmaos, cada um autossuficiente por desenho desta fase (mesmo
raciocinio documentado no proprio conftest de `propriedade`).

`gerar_vinculos_em_massa` insere N colaboradores + N vinculos + N
`vinculo_jornadas` (todos apontando para a MESMA jornada, ja que o PCF (T12)
pede "dados sinteticos, jornada fixa simples") em INSERTs multi-linha
(`sessao.execute(text(...), lista_de_dicionarios)`), nunca um INSERT por
linha em loop Python -- a massa em si nao e o que esta sendo medido, so
`recalcular_periodo`.
"""

from __future__ import annotations

import asyncio
import datetime as _dt
import os
import re
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
_URL_PADRAO_LOCAL = "postgresql+asyncpg://ponto:ponto@localhost:5432/ponto"


def _url_superusuario() -> URL:
    bruta = os.environ.get("PONTO_TEST_DATABASE_URL", _URL_PADRAO_LOCAL)
    return make_url(bruta)


def _nome_role_login(url_super: URL) -> str:
    base = re.sub(r"[^a-z0-9_]", "_", (url_super.database or "ponto").lower())
    return f"ponto_f4_login_{base}"


@pytest.fixture(scope="session")
def url_login_sessao_performance() -> URL:
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
            "alembic upgrade head falhou ao preparar o banco de teste da F4/A4 "
            f"(performance):\n--- stdout ---\n{resultado.stdout}\n"
            f"--- stderr ---\n{resultado.stderr}"
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
async def engine_performance(url_login_sessao_performance: URL) -> AsyncIterator[AsyncEngine]:
    ultimo_erro: Exception | None = None
    for tentativa in range(8):
        engine = create_async_engine(
            url_login_sessao_performance, pool_pre_ping=True, connect_args={"timeout": 8}
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
    raise RuntimeError(f"Nao foi possivel abrir a engine de teste da F4/A4: {ultimo_erro}")


@pytest_asyncio.fixture
async def sessao_performance(engine_performance: AsyncEngine) -> AsyncIterator[AsyncSession]:
    fabrica = async_sessionmaker(engine_performance, expire_on_commit=False, autoflush=False)
    async with fabrica() as sessao:
        yield sessao
        await sessao.rollback()


async def aplicar_tenant_teste(sessao: AsyncSession, tenant_id: uuid.UUID) -> None:
    await sessao.execute(
        text("SELECT set_config('app.tenant_id', :tenant, true)"),
        {"tenant": str(tenant_id)},
    )


@dataclass(frozen=True, slots=True)
class ContextoPerformance:
    tenant_id: uuid.UUID
    empresa_id: uuid.UUID
    unidade_id: uuid.UUID
    jornada_id: uuid.UUID


@pytest_asyncio.fixture
async def contexto_performance(sessao_performance: AsyncSession) -> ContextoPerformance:
    """Semeia tenant/empresa/unidade e 1 jornada fixa simples (08:00-17:00,
    1h de intervalo, seg-sex util, sabado folga, domingo DSR) -- os
    vinculos em massa sao gerados por `gerar_vinculos_em_massa`, chamado
    explicitamente pelo teste (nao por esta fixture), porque a QUANTIDADE e
    parametro do teste de performance, nao da fixture."""
    sufixo = uuid.uuid4().hex[:10]
    tenant_id = uuid.uuid4()
    await aplicar_tenant_teste(sessao_performance, tenant_id)

    await sessao_performance.execute(
        text(
            "INSERT INTO tenants (id, slug, razao_social, nome_exibicao, status) "
            "VALUES (:id, :slug, :razao, :nome, 'ativo')"
        ),
        {
            "id": tenant_id,
            "slug": f"f4-a4-perf-{sufixo}",
            "razao": "Tenant de teste F4/A4 (performance)",
            "nome": "Tenant F4 A4 Performance",
        },
    )

    empresa_id = uuid.uuid4()
    cnpj = f"{secrets.randbelow(10**14):014d}"
    await sessao_performance.execute(
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
            "razao": "Empresa de Teste F4 A4 Performance Ltda",
            "fantasia": "Empresa Teste F4 A4 Performance",
        },
    )

    unidade_id = uuid.uuid4()
    await sessao_performance.execute(
        text(
            "INSERT INTO unidades "
            "(id, tenant_id, empresa_id, codigo, nome, tipo, uf, codigo_ibge_municipio, "
            " fuso_horario, geocerca_obrigatoria) "
            "VALUES (:id, :tenant_id, :empresa_id, 'SEDE', 'Sede de Teste', 'sede', "
            "        'SP', '3550308', 'America/Sao_Paulo', FALSE)"
        ),
        {"id": unidade_id, "tenant_id": tenant_id, "empresa_id": empresa_id},
    )

    horario_id = uuid.uuid4()
    await sessao_performance.execute(
        text(
            "INSERT INTO horarios "
            "(id, tenant_id, empresa_id, codigo, nome, entrada, saida, "
            " intervalo_inicio, intervalo_fim, duracao_intervalo_minutos, carga_minutos) "
            "VALUES (:id, :tenant_id, :empresa_id, :codigo, 'Horario padrao 08-17', "
            "        '08:00', '17:00', '12:00', '13:00', 60, 480)"
        ),
        {
            "id": horario_id,
            "tenant_id": tenant_id,
            "empresa_id": empresa_id,
            "codigo": f"HOR-PERF-{sufixo}",
        },
    )
    jornada_id = uuid.uuid4()
    await sessao_performance.execute(
        text(
            "INSERT INTO jornadas "
            "(id, tenant_id, empresa_id, codigo, nome, tipo, vigencia_inicio, "
            " carga_diaria_minutos) "
            "VALUES (:id, :tenant_id, :empresa_id, :codigo, 'Jornada fixa de performance', "
            "        'fixa', :vigencia_inicio, 480)"
        ),
        {
            "id": jornada_id,
            "tenant_id": tenant_id,
            "empresa_id": empresa_id,
            "codigo": f"JOR-PERF-{sufixo}",
            "vigencia_inicio": _dt.date(2025, 1, 1),
        },
    )
    for dow in range(0, 7):
        if dow == 0:
            tipo_dia, horario_dia, carga = "dsr", None, 0
        elif dow == 6:
            tipo_dia, horario_dia, carga = "folga", None, 0
        else:
            tipo_dia, horario_dia, carga = "util", horario_id, 480
        await sessao_performance.execute(
            text(
                "INSERT INTO jornada_dias "
                "(id, tenant_id, jornada_id, dia_semana, tipo_dia, horario_id, carga_minutos) "
                "VALUES (:id, :tenant_id, :jornada_id, :dow, :tipo_dia, :horario_id, :carga)"
            ),
            {
                "id": uuid.uuid4(),
                "tenant_id": tenant_id,
                "jornada_id": jornada_id,
                "dow": dow,
                "tipo_dia": tipo_dia,
                "horario_id": horario_dia,
                "carga": carga,
            },
        )

    await sessao_performance.commit()
    await aplicar_tenant_teste(sessao_performance, tenant_id)

    return ContextoPerformance(
        tenant_id=tenant_id, empresa_id=empresa_id, unidade_id=unidade_id, jornada_id=jornada_id
    )


async def gerar_vinculos_em_massa(
    sessao: AsyncSession, contexto: ContextoPerformance, *, quantidade: int
) -> list[uuid.UUID]:
    """Insere `quantidade` colaboradores + vinculos + `vinculo_jornadas`
    (todos na MESMA jornada fixa simples) em tres INSERTs multi-linha --
    nunca um `INSERT` por linha em loop Python. Devolve os `vinculo_id`."""
    colaboradores = []
    vinculos = []
    atribuicoes = []
    vinculo_ids: list[uuid.UUID] = []
    for indice in range(quantidade):
        colaborador_id = uuid.uuid4()
        vinculo_id = uuid.uuid4()
        vinculo_ids.append(vinculo_id)
        colaboradores.append(
            {
                "id": colaborador_id,
                "tenant_id": contexto.tenant_id,
                "empresa_id": contexto.empresa_id,
                "matricula": f"PERF-{indice:06d}",
                "cpf": f"{(10**10 + indice):011d}",
                "nome": f"Colaborador de Performance {indice:06d}",
            }
        )
        vinculos.append(
            {
                "id": vinculo_id,
                "tenant_id": contexto.tenant_id,
                "colaborador_id": colaborador_id,
                "empresa_id": contexto.empresa_id,
                "unidade_id": contexto.unidade_id,
                "esocial": f"ESOC-PERF-{indice:06d}",
                "data_inicio": _dt.date(2020, 1, 1),
            }
        )
        atribuicoes.append(
            {
                "id": uuid.uuid4(),
                "tenant_id": contexto.tenant_id,
                "vinculo_id": vinculo_id,
                "jornada_id": contexto.jornada_id,
                "vigencia_inicio": _dt.date(2025, 1, 1),
            }
        )

    await sessao.execute(
        text(
            "INSERT INTO colaboradores "
            "(id, tenant_id, empresa_id, matricula, cpf, nome_completo, status) "
            "VALUES (:id, :tenant_id, :empresa_id, :matricula, :cpf, :nome, 'ativo')"
        ),
        colaboradores,
    )
    await sessao.execute(
        text(
            "INSERT INTO vinculos "
            "(id, tenant_id, colaborador_id, empresa_id, unidade_id, matricula_esocial, "
            " tipo_vinculo, data_inicio, apura_ponto, status) "
            "VALUES (:id, :tenant_id, :colaborador_id, :empresa_id, :unidade_id, :esocial, "
            "        'empregado', :data_inicio, TRUE, 'ativo')"
        ),
        vinculos,
    )
    await sessao.execute(
        text(
            "INSERT INTO vinculo_jornadas "
            "(id, tenant_id, vinculo_id, jornada_id, vigencia_inicio) "
            "VALUES (:id, :tenant_id, :vinculo_id, :jornada_id, :vigencia_inicio)"
        ),
        atribuicoes,
    )
    await sessao.flush()
    return vinculo_ids
