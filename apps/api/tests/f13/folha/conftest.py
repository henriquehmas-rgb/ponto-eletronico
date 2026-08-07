"""Fixture do subarvore `folha` da fase F13 (A5, T15/T16 -- ownership
exclusivo de A5, `apps/api/tests/f13/folha/**`). Deliberadamente SEPARADA
de `apps/api/tests/f13/conftest.py` (compartilhada da fase, criacao
exclusiva de A1, PCF F13 secao 5.2) -- este arquivo nao a substitui nem
depende dela; A5 e T1-first do subgrupo folha e nao pode ficar bloqueado
esperando A1 terminar T1 para começar a testar o motor generico.
Mesmo padrao ja usado por `apps/api/tests/f12/conftest.py` (banco/role
exclusivos por agente), reproduzido aqui em versao enxuta -- só o que o
motor de folha precisa (tenant, empresa, colaborador+vinculo,
departamento, `apuracoes_dia`/`apuracao_componentes`, `integracoes_folha`).

Banco de teste EXCLUSIVO deste agente (`ponto_f13_a5`), criado sob demanda
a partir de `PONTO_TEST_DATABASE_URL` (conexao administrativa). Role de
LOGIN propria (`ponto_f13_a5_login`, membro de `ponto_app`, nunca
superusuario) -- necessario para que RLS (Row Level Security) realmente se
aplique nos testes: a role usada para migrar (tipicamente dona das
tabelas) nao sofre RLS por padrao.
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

_URL_PADRAO_LOCAL = "postgresql+asyncpg://ponto:ponto@localhost:5432/postgres"
_NOME_BANCO = "ponto_f13_a5"
_ROLE_LOGIN = "ponto_f13_a5_login"


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
            "alembic upgrade head falhou ao preparar o banco de teste da F13/A5:\n"
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
def url_login_sessao_f13a5() -> URL:
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
async def engine_f13a5(url_login_sessao_f13a5: URL) -> AsyncIterator[AsyncEngine]:
    ultimo_erro: Exception | None = None
    for tentativa in range(8):
        engine = create_async_engine(
            url_login_sessao_f13a5,
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
    raise RuntimeError(f"Nao foi possivel abrir a engine de teste da F13/A5: {ultimo_erro}")


@pytest_asyncio.fixture
async def sessao_f13a5(engine_f13a5: AsyncEngine) -> AsyncIterator[AsyncSession]:
    fabrica = async_sessionmaker(engine_f13a5, expire_on_commit=False, autoflush=False)
    async with fabrica() as sessao:
        yield sessao
        await sessao.rollback()


async def aplicar_tenant_teste(sessao: AsyncSession, tenant_id: uuid.UUID) -> None:
    await sessao.execute(
        text("SELECT set_config('app.tenant_id', :tenant, true)"), {"tenant": str(tenant_id)}
    )


def _digitos(quantidade: int) -> str:
    return str(uuid.uuid4().int)[:quantidade].zfill(quantidade)


@dataclass(frozen=True, slots=True)
class LinhaSemente:
    apuracao_dia_id: uuid.UUID
    data: dt.date
    componente_id: uuid.UUID
    codigo: str
    categoria: str
    minutos: int


@dataclass(frozen=True, slots=True)
class ContextoFolhaF13:
    tenant_id: uuid.UUID
    empresa_id: uuid.UUID
    empresa_cnpj: str
    unidade_id: uuid.UUID
    departamento_id: uuid.UUID
    departamento_codigo: str
    colaborador_id: uuid.UUID
    colaborador_matricula: str
    colaborador_cpf: str
    colaborador_pis: str
    vinculo_id: uuid.UUID
    periodo_id: uuid.UUID
    periodo_inicio: dt.date
    periodo_fim: dt.date
    competencia_folha: str
    linhas: list[LinhaSemente]


@pytest_asyncio.fixture
async def contexto_folha_f13a5(sessao_f13a5: AsyncSession) -> ContextoFolhaF13:
    """Semeia 1 tenant, 1 empresa, 1 unidade, 1 departamento (codigo
    numerico), 1 colaborador com vinculo, 1 periodo mensal FECHADO e 2 dias
    de `apuracoes_dia` (status `fechado`) com componentes de apuracao --
    base minima para exercitar `dados.coletar_linhas_apuracao` e os
    exportadores (generico_csv/dominio/alterdata) de ponta a ponta."""
    sufixo = uuid.uuid4().hex[:10]
    tenant_id = uuid.uuid4()
    await aplicar_tenant_teste(sessao_f13a5, tenant_id)

    await sessao_f13a5.execute(
        text(
            "INSERT INTO tenants (id, slug, razao_social, nome_exibicao, status) "
            "VALUES (:id, :slug, :razao, :nome, 'ativo')"
        ),
        {
            "id": tenant_id,
            "slug": f"f13a5-{sufixo}",
            "razao": "Tenant de teste F13/A5",
            "nome": "Tenant F13 A5",
        },
    )

    empresa_id = uuid.uuid4()
    empresa_cnpj = _digitos(14)
    await sessao_f13a5.execute(
        text(
            "INSERT INTO empresas "
            "(id, tenant_id, tipo, cnpj, razao_social, nome_fantasia, uf, codigo_ibge_municipio) "
            "VALUES (:id, :tenant_id, 'matriz', :cnpj, :razao, :fantasia, 'GO', '5208707')"
        ),
        {
            "id": empresa_id,
            "tenant_id": tenant_id,
            "cnpj": empresa_cnpj,
            "razao": "Empresa de teste F13 A5 Ltda",
            "fantasia": "Empresa Teste F13 A5",
        },
    )

    unidade_id = uuid.uuid4()
    await sessao_f13a5.execute(
        text(
            "INSERT INTO unidades "
            "(id, tenant_id, empresa_id, codigo, nome, tipo, uf, codigo_ibge_municipio) "
            "VALUES (:id, :tenant_id, :empresa_id, 'SEDE', 'Sede de teste F13 A5', 'sede', 'GO', "
            "        '5208707')"
        ),
        {"id": unidade_id, "tenant_id": tenant_id, "empresa_id": empresa_id},
    )

    departamento_id = uuid.uuid4()
    departamento_codigo = _digitos(4)
    await sessao_f13a5.execute(
        text(
            "INSERT INTO departamentos (id, tenant_id, empresa_id, codigo, nome) "
            "VALUES (:id, :tenant_id, :empresa_id, :codigo, 'Departamento de teste F13 A5')"
        ),
        {
            "id": departamento_id,
            "tenant_id": tenant_id,
            "empresa_id": empresa_id,
            "codigo": departamento_codigo,
        },
    )

    hoje = dt.date.today()
    colaborador_id = uuid.uuid4()
    colaborador_matricula = _digitos(6)
    colaborador_cpf = _digitos(11)
    colaborador_pis = _digitos(11)
    await sessao_f13a5.execute(
        text(
            "INSERT INTO colaboradores "
            "(id, tenant_id, empresa_id, matricula, cpf, pis_nit, nome_completo, status, "
            " data_admissao) "
            "VALUES (:id, :tenant_id, :empresa_id, :matricula, :cpf, :pis, :nome, 'ativo', "
            "        :admissao)"
        ),
        {
            "id": colaborador_id,
            "tenant_id": tenant_id,
            "empresa_id": empresa_id,
            "matricula": colaborador_matricula,
            "cpf": colaborador_cpf,
            "pis": colaborador_pis,
            "nome": "Colaborador de Teste F13 A5",
            "admissao": hoje - dt.timedelta(days=365),
        },
    )

    vinculo_id = uuid.uuid4()
    await sessao_f13a5.execute(
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

    competencia = f"{hoje.year:04d}-{hoje.month:02d}"
    periodo_inicio = hoje.replace(day=1)
    if hoje.month == 12:
        proximo_mes = hoje.replace(year=hoje.year + 1, month=1, day=1)
    else:
        proximo_mes = hoje.replace(month=hoje.month + 1, day=1)
    periodo_fim = proximo_mes - dt.timedelta(days=1)

    periodo_id = uuid.uuid4()
    await sessao_f13a5.execute(
        text(
            "INSERT INTO periodos "
            "(id, tenant_id, empresa_id, codigo, tipo, data_inicio, data_fim, competencia_folha, "
            " status) "
            "VALUES (:id, :tenant_id, :empresa_id, :codigo, 'mensal', :inicio, :fim, "
            "        :competencia, 'fechado')"
        ),
        {
            "id": periodo_id,
            "tenant_id": tenant_id,
            "empresa_id": empresa_id,
            "codigo": competencia,
            "inicio": periodo_inicio,
            "fim": periodo_fim,
            "competencia": competencia,
        },
    )

    linhas: list[LinhaSemente] = []
    dias = [periodo_inicio, periodo_inicio + dt.timedelta(days=1)]
    componentes = [
        ("he_50", "extra", 60),
        ("adicional_noturno", "noturno", 30),
    ]
    for dia in dias:
        apuracao_dia_id = uuid.uuid4()
        await sessao_f13a5.execute(
            text(
                "INSERT INTO apuracoes_dia "
                "(id, tenant_id, vinculo_id, colaborador_id, data, empresa_id, unidade_id, "
                " departamento_id, tipo_dia, status) "
                "VALUES (:id, :tenant_id, :vinculo_id, :colaborador_id, :data, :empresa_id, "
                "        :unidade_id, :departamento_id, 'util', 'fechado')"
            ),
            {
                "id": apuracao_dia_id,
                "tenant_id": tenant_id,
                "vinculo_id": vinculo_id,
                "colaborador_id": colaborador_id,
                "data": dia,
                "empresa_id": empresa_id,
                "unidade_id": unidade_id,
                "departamento_id": departamento_id,
            },
        )
        for codigo, categoria, minutos in componentes:
            componente_id = uuid.uuid4()
            await sessao_f13a5.execute(
                text(
                    "INSERT INTO apuracao_componentes "
                    "(id, tenant_id, apuracao_dia_id, codigo, descricao, categoria, minutos, "
                    " fator, minutos_equivalentes, origem) "
                    "VALUES (:id, :tenant_id, :apuracao_dia_id, :codigo, :descricao, :categoria, "
                    "        :minutos, :fator, :minutos_equivalentes, 'marcacao')"
                ),
                {
                    "id": componente_id,
                    "tenant_id": tenant_id,
                    "apuracao_dia_id": apuracao_dia_id,
                    "codigo": codigo,
                    "descricao": codigo.replace("_", " ").title(),
                    "categoria": categoria,
                    "minutos": minutos,
                    "fator": "1.5000" if categoria == "extra" else "1.2000",
                    "minutos_equivalentes": round(minutos * (1.5 if categoria == "extra" else 1.2)),
                },
            )
            linhas.append(
                LinhaSemente(
                    apuracao_dia_id=apuracao_dia_id,
                    data=dia,
                    componente_id=componente_id,
                    codigo=codigo,
                    categoria=categoria,
                    minutos=minutos,
                )
            )

    await sessao_f13a5.commit()
    await aplicar_tenant_teste(sessao_f13a5, tenant_id)

    return ContextoFolhaF13(
        tenant_id=tenant_id,
        empresa_id=empresa_id,
        empresa_cnpj=empresa_cnpj,
        unidade_id=unidade_id,
        departamento_id=departamento_id,
        departamento_codigo=departamento_codigo,
        colaborador_id=colaborador_id,
        colaborador_matricula=colaborador_matricula,
        colaborador_cpf=colaborador_cpf,
        colaborador_pis=colaborador_pis,
        vinculo_id=vinculo_id,
        periodo_id=periodo_id,
        periodo_inicio=periodo_inicio,
        periodo_fim=periodo_fim,
        competencia_folha=competencia,
        linhas=linhas,
    )
