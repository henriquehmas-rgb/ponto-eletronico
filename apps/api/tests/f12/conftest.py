"""Fixture da Fase F12 (T1 -- exclusiva do agente A1; ninguém mais edita
este arquivo -- PCF da fase, `docs/fases/F12-conformidade-rep-p.md` §5).

Banco de teste EXCLUSIVO deste agente (`ponto_f12_a1`), criado sob demanda a
partir da conexão administrativa apontada por `PONTO_TEST_DATABASE_URL`
(o mesmo Postgres compartilhado por todos os agentes da onda, mas cada
agente com o seu próprio banco -- nunca compartilhar banco nem entre
agentes da mesma fase). Role de LOGIN própria (`ponto_f12_a1_login`,
membro de `ponto_app`, NUNCA superusuário) -- mesmo padrão que
`apps/api/tests/f5/conftest.py` já estabeleceu, reproduzido aqui porque
cada fase mantém sua própria cópia da fixture (nunca importa a de outra
fase).

Duas camadas de fixture, do mesmo motivo que F2/F5 já documentaram: a suíte
roda com `asyncio_default_fixture_loop_scope = "function"`
(`pyproject.toml`), e um recurso assíncrono criado em escopo `session` não
sobrevive ao próximo event loop.

1. `url_login_sessao_f12` (escopo `session`, síncrona): garante o banco,
   migra e cria/atualiza a role de LOGIN. Roda uma única vez por sessão de
   pytest.
2. `engine_f12`/`sessao_f12` (escopo `function`, assíncronas): cada teste
   ganha sua própria engine/sessão, presa ao event loop daquele teste.
3. `contexto_f12` (escopo `function`): semeia, a cada teste, 1 tenant, 1
   empresa, 1 REP-P `ativo` (com `numeroInpi` preenchido -- diferente da
   fixture da F5, que não precisava disso) e sua `nsr_sequencias`, 1
   colaborador com vínculo ativo hoje. `rep_ps`/`nsr_sequencias` são
   semeados por `INSERT` direto (mesmo padrão que a fixture da F5 já
   estabeleceu para dados de cadastro que não são o foco desta fase) --
   **as MARCAÇÕES não são**: `gerar_marcacoes_reais` chama
   `app.marcacao.dominio.registro.persistir_marcacao` (F5, pipeline real),
   nunca `INSERT` direto, para que `nsr`/`crc16`/`hash_registro` sejam
   gerados de verdade e a fixture não minta sobre como uma marcação chega
   ao banco (`docs/fases/F12-conformidade-rep-p.md` §6/T1).

Variável de ambiente lida: `PONTO_TEST_DATABASE_URL` (string de conexão
`postgresql+asyncpg://usuario:senha@host:porta/postgres` de um Postgres com
privilégio de `CREATEDB`/`CREATEROLE`). Sem a variável, cai no default de
desenvolvimento local -- nunca o banco de nenhum ambiente real.
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
from collections.abc import AsyncIterator, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

import psycopg
import pytest
import pytest_asyncio
import sqlalchemy as sa
from ponto_contracts import Marcacao
from psycopg import sql
from sqlalchemy import text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.marcacao.dominio.registro import DadosMarcacao, persistir_marcacao

RAIZ_API = Path(__file__).resolve().parents[2]

#: Default de desenvolvimento local. Só usado quando `PONTO_TEST_DATABASE_URL`
#: não está definida -- nunca aponta para banco de ambiente real.
_URL_PADRAO_LOCAL = "postgresql+asyncpg://ponto:ponto@localhost:5432/postgres"

#: Banco EXCLUSIVO deste agente (F12/A1). Nunca compartilhado.
_NOME_BANCO = "ponto_f12_a1"

#: Role de LOGIN exclusiva desta fase/agente.
_ROLE_LOGIN = "ponto_f12_a1_login"


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


def _aplica_migracao(url_admin_banco_f12: URL) -> None:
    ambiente = dict(os.environ)
    ambiente["DATABASE_URL"] = url_admin_banco_f12.render_as_string(hide_password=False)
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
            "alembic upgrade head falhou ao preparar o banco de teste da F12/A1:\n"
            f"--- stdout ---\n{resultado.stdout}\n--- stderr ---\n{resultado.stderr}"
        )


def _cria_ou_atualiza_role_login(url_admin_banco_f12: URL, senha: str) -> None:
    dsn_admin = url_admin_banco_f12.set(drivername="postgresql").render_as_string(
        hide_password=False
    )
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
def url_login_sessao_f12() -> URL:
    """Garante o banco exclusivo, migra e devolve a `URL` assíncrona da role
    de LOGIN desta fase/agente."""
    url_admin = _url_administrativa()
    url_admin_banco_f12 = _garantir_banco_exclusivo(url_admin)

    _aplica_migracao(url_admin_banco_f12)

    senha = secrets.token_urlsafe(24)
    _cria_ou_atualiza_role_login(url_admin_banco_f12, senha)

    url_login = url_admin_banco_f12.set(
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


@pytest.fixture(scope="session")
def dsn_superusuario_f12(url_login_sessao_f12: URL) -> str:
    """DSN síncrono da conexão ADMINISTRATIVA contra o banco exclusivo desta
    fase/agente. Uso restrito a testes adversariais que precisam contornar
    um gatilho de imutabilidade (ex.: simular uma lacuna de NSR removendo
    uma linha via SQL direto, T5) -- nunca para os testes de negócio em si,
    que sempre conectam como `ponto_f12_a1_login`."""
    url_admin = _url_administrativa()
    url_admin_banco_f12 = url_admin.set(database=_NOME_BANCO, drivername="postgresql+psycopg")
    return url_admin_banco_f12.render_as_string(hide_password=False)


@pytest.fixture(scope="session")
def admin_engine_sync_f12(dsn_superusuario_f12: str) -> Iterator[sa.engine.Engine]:
    engine = sa.create_engine(dsn_superusuario_f12, future=True)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest_asyncio.fixture
async def engine_f12(url_login_sessao_f12: URL) -> AsyncIterator[AsyncEngine]:
    ultimo_erro: Exception | None = None
    for tentativa in range(8):
        engine = create_async_engine(
            url_login_sessao_f12,
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
    raise RuntimeError(f"Nao foi possivel abrir a engine de teste da F12/A1: {ultimo_erro}")


@pytest_asyncio.fixture
async def sessao_f12(engine_f12: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """Sessão assíncrona por teste. O teste decide quando commitar. Cuidado
    com `SET LOCAL` + `commit()`: `aplicar_tenant_teste` usa `SET LOCAL`,
    válido só até o fim da transação corrente -- commitar no meio do teste
    exige chamar `aplicar_tenant_teste` de novo."""
    fabrica = async_sessionmaker(engine_f12, expire_on_commit=False, autoflush=False)
    async with fabrica() as sessao:
        yield sessao
        await sessao.rollback()


async def aplicar_tenant_teste(sessao: AsyncSession, tenant_id: uuid.UUID) -> None:
    """Publica `app.tenant_id` na transação corrente, como `app/db/sessao.py`
    faz em produção."""
    await sessao.execute(
        text("SELECT set_config('app.tenant_id', :tenant, true)"),
        {"tenant": str(tenant_id)},
    )


@dataclass(frozen=True, slots=True)
class ContextoF12:
    """IDs da semente mínima da fase, usada pelos três agentes (A1, A2, A3)."""

    tenant_id: uuid.UUID
    tenant_slug: str
    empresa_id: uuid.UUID
    empresa_cnpj: str
    rep_p_id: uuid.UUID
    rep_p_identificador: str
    rep_p_numero_inpi: str
    rep_p_cnpj_desenvolvedor: str
    rep_p_razao_social_desenvolvedor: str
    rep_p_razao_social_empregador: str
    unidade_id: uuid.UUID
    colaborador_id: uuid.UUID
    colaborador_cpf: str
    colaborador_matricula: str
    vinculo_id: uuid.UUID


def _digitos(quantidade: int) -> str:
    """`quantidade` dígitos decimais aleatórios -- `dom_cpf`/`dom_cnpj`
    exigem só dígito."""
    return str(uuid.uuid4().int)[:quantidade].zfill(quantidade)


@pytest_asyncio.fixture
async def contexto_f12(sessao_f12: AsyncSession) -> ContextoF12:
    """Semeia, a cada teste, 1 tenant, 1 empresa, 1 unidade, 1 REP-P `ativo`
    (com `numeroInpi` preenchido + `nsr_sequencias` inicializada em 1), 1
    colaborador com vínculo `apura_ponto=true` ativo hoje. Cada chamada gera
    identificadores novos -- nenhum teste compartilha semente com outro.

    `rep_ps`/`nsr_sequencias` semeados por `INSERT` direto (mesmo padrão
    que a fixture da F5 já usa para dados de cadastro): `criarRepP`
    (`app.fiscal.rep_p.servico`) é testado à parte, em
    `tests/f12/rep_p/test_servico.py` -- esta fixture não precisa passar
    pela rota para ter um REP-P válido, do mesmo jeito que a fixture da F5
    não passava por ela para ter o REP-P que suas marcações precisavam.
    """
    sufixo = uuid.uuid4().hex[:12]
    tenant_id = uuid.uuid4()
    tenant_slug = f"f12-{sufixo}"

    await aplicar_tenant_teste(sessao_f12, tenant_id)

    await sessao_f12.execute(
        text(
            "INSERT INTO tenants (id, slug, razao_social, nome_exibicao, status) "
            "VALUES (:id, :slug, :razao, :nome, 'ativo')"
        ),
        {
            "id": tenant_id,
            "slug": tenant_slug,
            "razao": "Tenant de teste da fase F12",
            "nome": "Tenant F12",
        },
    )

    empresa_id = uuid.uuid4()
    empresa_cnpj = _digitos(14)
    await sessao_f12.execute(
        text(
            "INSERT INTO empresas "
            "(id, tenant_id, tipo, cnpj, razao_social, nome_fantasia, uf, "
            " codigo_ibge_municipio) "
            "VALUES (:id, :tenant_id, 'matriz', :cnpj, :razao, :fantasia, 'GO', '5208707')"
        ),
        {
            "id": empresa_id,
            "tenant_id": tenant_id,
            "cnpj": empresa_cnpj,
            "razao": "Empresa de teste F12 Ltda",
            "fantasia": "Empresa Teste F12",
        },
    )

    unidade_id = uuid.uuid4()
    await sessao_f12.execute(
        text(
            "INSERT INTO unidades "
            "(id, tenant_id, empresa_id, codigo, nome, tipo, uf, codigo_ibge_municipio) "
            "VALUES (:id, :tenant_id, :empresa_id, 'SEDE', 'Sede de teste F12', 'sede', 'GO', "
            "        '5208707')"
        ),
        {"id": unidade_id, "tenant_id": tenant_id, "empresa_id": empresa_id},
    )

    rep_p_id = uuid.uuid4()
    rep_p_identificador = f"REP-{sufixo}"
    rep_p_numero_inpi = str(uuid.uuid4().int)[:15].zfill(15)
    rep_p_cnpj_desenvolvedor = "60258502000149"  # SEEG, mesmo CNPJ dos exemplos do contrato
    rep_p_razao_social_desenvolvedor = "SEEG Servicos de Tecnologia da Informacao LTDA"
    rep_p_razao_social_empregador = "Empresa de teste F12 Ltda"
    hoje = dt.date.today()
    await sessao_f12.execute(
        text(
            "INSERT INTO rep_ps "
            "(id, tenant_id, empresa_id, identificador, tipo, numero_inpi, "
            " cnpj_desenvolvedor, razao_social_desenvolvedor, cnpj_empregador, "
            " razao_social_empregador, versao_programa, data_inicio_operacao, status) "
            "VALUES (:id, :tenant_id, :empresa_id, :identificador, 'rep_p', :numero_inpi, "
            "        :cnpj_desenvolvedor, :razao_social_desenvolvedor, :cnpj_empregador, "
            "        :razao_social_empregador, '1.0.0-teste', :inicio, 'ativo')"
        ),
        {
            "id": rep_p_id,
            "tenant_id": tenant_id,
            "empresa_id": empresa_id,
            "identificador": rep_p_identificador,
            "numero_inpi": rep_p_numero_inpi,
            "cnpj_desenvolvedor": rep_p_cnpj_desenvolvedor,
            "razao_social_desenvolvedor": rep_p_razao_social_desenvolvedor,
            "cnpj_empregador": empresa_cnpj,
            "razao_social_empregador": rep_p_razao_social_empregador,
            "inicio": hoje,
        },
    )
    await sessao_f12.execute(
        text(
            "INSERT INTO nsr_sequencias (id, tenant_id, rep_p_id, proximo_nsr, ultimo_nsr_emitido) "
            "VALUES (:id, :tenant_id, :rep_p_id, 1, 0)"
        ),
        {"id": uuid.uuid4(), "tenant_id": tenant_id, "rep_p_id": rep_p_id},
    )

    colaborador_id = uuid.uuid4()
    colaborador_cpf = _digitos(11)
    colaborador_matricula = sufixo[:10]
    await sessao_f12.execute(
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
            "nome": "Colaborador de Teste F12",
            "admissao": hoje - dt.timedelta(days=365),
        },
    )

    vinculo_id = uuid.uuid4()
    await sessao_f12.execute(
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

    await sessao_f12.commit()
    await aplicar_tenant_teste(sessao_f12, tenant_id)

    return ContextoF12(
        tenant_id=tenant_id,
        tenant_slug=tenant_slug,
        empresa_id=empresa_id,
        empresa_cnpj=empresa_cnpj,
        rep_p_id=rep_p_id,
        rep_p_identificador=rep_p_identificador,
        rep_p_numero_inpi=rep_p_numero_inpi,
        rep_p_cnpj_desenvolvedor=rep_p_cnpj_desenvolvedor,
        rep_p_razao_social_desenvolvedor=rep_p_razao_social_desenvolvedor,
        rep_p_razao_social_empregador=rep_p_razao_social_empregador,
        unidade_id=unidade_id,
        colaborador_id=colaborador_id,
        colaborador_cpf=colaborador_cpf,
        colaborador_matricula=colaborador_matricula,
        vinculo_id=vinculo_id,
    )


async def gerar_marcacoes_reais(
    sessao: AsyncSession,
    contexto: ContextoF12,
    *,
    quantidade: int,
    canal: str = "terminal",
    coletada_offline: bool = False,
    inicio: dt.datetime | None = None,
    intervalo: dt.timedelta = dt.timedelta(minutes=30),
) -> Sequence[Marcacao]:
    """Gera `quantidade` marcações reais através do pipeline real de F5
    (`app.marcacao.dominio.registro.persistir_marcacao`), NUNCA `INSERT`
    direto -- para que `nsr`/`crc16`/`hash_registro` sejam gerados de
    verdade e a fixture não minta sobre como uma marcação chega ao banco
    (`docs/fases/F12-conformidade-rep-p.md` §6/T1). Devolve as marcações na
    ordem em que foram criadas (== ordem de NSR, sequencial, sem lacuna).

    Cada chamada continua a sequência de NSR do REP-P de onde a chamada
    anterior parou (o alocador é transacional e cumulativo,
    `app.marcacao.dominio.nsr`) -- duas chamadas na mesma `contexto_f12`
    produzem uma única sequência contínua, não duas sequências separadas.
    """
    momento = inicio or dt.datetime.now(tz=dt.timezone(dt.timedelta(hours=-3)))
    criadas: list[Marcacao] = []
    for indice in range(quantidade):
        dados = DadosMarcacao(
            rep_p_id=contexto.rep_p_id,
            empresa_id=contexto.empresa_id,
            cpf=contexto.colaborador_cpf,
            canal=canal,
            datahora_marcacao=momento + indice * intervalo,
            unidade_id=contexto.unidade_id,
            colaborador_id=contexto.colaborador_id,
            vinculo_id=contexto.vinculo_id,
            tipo_registro="7",
            coletada_offline=coletada_offline,
        )
        marcacao = await persistir_marcacao(sessao, tenant_id=contexto.tenant_id, dados=dados)
        criadas.append(marcacao)
    await sessao.commit()
    await aplicar_tenant_teste(sessao, contexto.tenant_id)
    return criadas
