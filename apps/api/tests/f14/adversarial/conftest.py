"""Fixtures da F14/A4 (verificacao adversarial). Territorio exclusivo deste
agente (PCF F14 secao 3: `apps/api/tests/f14/adversarial/**`).

Banco de teste EXCLUSIVO deste agente (`ponto_f14_a4`). Mesma convencao que
`tests/f14/antifraude/conftest.py`/`tests/f14/lgpd/conftest.py` ja usam
(instrucao do orquestrador, repetida desde F13): `PONTO_TEST_DATABASE_URL` ja
aponta direto para o banco exclusivo -- `DATABASE_URL` deve ser identica, para
que a engine GLOBAL do processo (`app.db.sessao`, usada pelo `TestClient`
real) e a engine desta fixture apontem para o MESMO banco.

Self-contained de proposito (mesma nota que os outros dois `conftest.py` de
F14 ja registram): nao importa `tests.f14.antifraude.conftest` nem
`tests.f14.lgpd.conftest` -- ownership de arquivo desta fase e mutuamente
exclusivo (PCF F14 secao 3), cada agente semeia o proprio banco.

Diferenca central deste conftest em relacao aos de A1/A3: quase todo teste
adversarial precisa de DOIS tenants isolados (a fraude entre tenants e um dos
seis vetores do mandato de A4) -- `contexto_dois_tenants` semeia dois tenants
completos (empresa, unidade com geocerca, REP-P ativo, colaborador com
vinculo ativo, dispositivo com `chave_publica`, usuario com sessao web
reautenticada) na MESMA sessao/transacao, cada bloco de INSERT precedido do
`SET LOCAL app.tenant_id` correto -- a RLS `WITH CHECK` recusaria a insercao
se o tenant corrente nao bater com o `tenant_id` da linha.
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

_URL_PADRAO_LOCAL = "postgresql+asyncpg://ponto:ponto@localhost:5432/ponto_f14_a4_local"

# Praca Civica, Goiania/GO -- mesma referencia de `tests/f5/conftest.py` e
# `tests/f14/antifraude/conftest.py`, para os testes poderem calcular
# distancia/velocidade com numeros ja conhecidos pela suite.
GEOCERCA_LATITUDE = -16.6799
GEOCERCA_LONGITUDE = -49.255
GEOCERCA_RAIO_METROS = 100
GEOCERCA_TOLERANCIA_METROS = 50

# Ponto bem distante (Manaus/AM) -- ~2000km da sede, usado por testes que
# precisam de velocidade implicita impossivel.
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
            "alembic upgrade head falhou ao preparar o banco de teste da F14/A4:\n"
            f"--- stdout ---\n{resultado.stdout}\n--- stderr ---\n{resultado.stderr}"
        )


@pytest.fixture(scope="session")
def url_login_sessao_f14a4() -> URL:
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
async def engine_f14a4(url_login_sessao_f14a4: URL) -> AsyncIterator[AsyncEngine]:
    ultimo_erro: Exception | None = None
    for tentativa in range(8):
        engine = create_async_engine(
            url_login_sessao_f14a4,
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
    raise RuntimeError(f"Nao foi possivel abrir a engine de teste da F14/A4: {ultimo_erro}")


@pytest_asyncio.fixture
async def sessao_f14a4(engine_f14a4: AsyncEngine) -> AsyncIterator[AsyncSession]:
    fabrica = async_sessionmaker(engine_f14a4, expire_on_commit=False, autoflush=False)
    async with fabrica() as sessao:
        yield sessao
        await sessao.rollback()


# =============================================================================
# Role de LOGIN sem BYPASSRLS (ADR-001 regra 4: "a aplicacao conecta com uma
# role SEM BYPASSRLS. Migrations e rotinas de plataforma usam outra role, com
# credencial separada.") -- mesmo padrao ja usado por `tests/f1/conftest.py`
# (`PAPEL_LOGIN`) e `tests/f14/lgpd/conftest.py` (`_ROLE_LOGIN`).
#
# **Por que isto e OBRIGATORIO para qualquer teste adversarial de RLS.**
# `PONTO_TEST_DATABASE_URL` (instrucao do orquestrador para esta sessao,
# usuario `ponto`) e o MESMO usuario administrativo que cria bancos/roles --
# na instancia de teste desta VPS ele e SUPERUSUARIO com `BYPASSRLS=true`
# (confirmado por `SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname
# = 'ponto'`). Row Level Security do PostgreSQL **nunca** se aplica a um
# superusuario ou a uma role com `BYPASSRLS`, mesmo com `FORCE ROW LEVEL
# SECURITY` na tabela -- um teste de isolamento cross-tenant que consulta o
# banco conectado como `ponto` sempre vai "ver tudo", nao porque a policy
# esteja quebrada, mas porque a policy nunca chega a ser avaliada para essa
# conexao. Ver `test_bypass_rls.py` para a prova completa e o achado real que
# isto revelou sobre `infra/docker-compose.yml`.
# =============================================================================

_ROLE_LOGIN_A4 = "ponto_f14_a4_teste_login"


@pytest.fixture(scope="session")
def url_role_sem_bypassrls_f14a4(url_login_sessao_f14a4: URL) -> URL:
    """Cria (ou reaproveita) uma role de LOGIN, membro de `ponto_app`
    (`NOLOGIN` por si so, criada por `0001_inicial`), SEM `BYPASSRLS` -- a
    UNICA forma de exercitar RLS de verdade neste banco de teste."""
    url_super = url_login_sessao_f14a4
    senha = secrets.token_urlsafe(24)
    dsn_super = url_super.set(drivername="postgresql").render_as_string(hide_password=False)
    with psycopg.connect(dsn_super, autocommit=True) as conexao, conexao.cursor() as cursor:
        cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (_ROLE_LOGIN_A4,))
        if cursor.fetchone():
            cursor.execute(
                sql.SQL("ALTER ROLE {} WITH LOGIN PASSWORD {}").format(
                    sql.Identifier(_ROLE_LOGIN_A4), sql.Literal(senha)
                )
            )
        else:
            cursor.execute(
                sql.SQL("CREATE ROLE {} LOGIN PASSWORD {} IN ROLE ponto_app").format(
                    sql.Identifier(_ROLE_LOGIN_A4), sql.Literal(senha)
                )
            )
        # Confirmacao ativa (nao so "confiar que CREATE ROLE...IN ROLE fez o
        # certo"): a role recem-criada/alterada realmente NAO tem BYPASSRLS
        # nem e superusuario. Se isto falhar, o restante do arquivo de teste
        # estaria testando a coisa errada de novo -- falha alto e cedo.
        cursor.execute(
            "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = %s",
            (_ROLE_LOGIN_A4,),
        )
        rolsuper, rolbypassrls = cursor.fetchone()
        if rolsuper or rolbypassrls:
            raise RuntimeError(
                f"{_ROLE_LOGIN_A4} tem rolsuper={rolsuper}/rolbypassrls={rolbypassrls} -- "
                "nao serve para testar RLS. Verifique se algum GRANT/ALTER concedeu "
                "privilegio demais a esta role em execucoes anteriores."
            )

    return url_super.set(drivername="postgresql+asyncpg", username=_ROLE_LOGIN_A4, password=senha)


@pytest_asyncio.fixture
async def engine_role_f14a4(url_role_sem_bypassrls_f14a4: URL) -> AsyncIterator[AsyncEngine]:
    ultimo_erro: Exception | None = None
    for tentativa in range(8):
        engine = create_async_engine(
            url_role_sem_bypassrls_f14a4,
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
    raise RuntimeError(
        f"Nao foi possivel abrir a engine da role sem BYPASSRLS da F14/A4: {ultimo_erro}"
    )


@pytest_asyncio.fixture
async def sessao_role_f14a4(engine_role_f14a4: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """Sessao conectada pela role SEM `BYPASSRLS` -- usar exclusivamente para
    LER dado ja commitado por `sessao_f14a4` (conexao/role diferente: nada
    escrito e nao commitado do lado `ponto` e visivel aqui)."""
    fabrica = async_sessionmaker(engine_role_f14a4, expire_on_commit=False, autoflush=False)
    async with fabrica() as sessao:
        yield sessao
        await sessao.rollback()


async def aplicar_tenant_teste(sessao: AsyncSession, tenant_id: uuid.UUID) -> None:
    """Publica `app.tenant_id` na sessao Postgres (mesmo mecanismo de
    `app.db.sessao.aplicar_tenant`). Precisa ser chamado de novo apos
    qualquer `commit()`/`rollback()` na mesma sessao -- RLS so vale para a
    transacao corrente (achado F13/A3, 2026-08-03, `docs/backlog.md`)."""
    await sessao.execute(
        text("SELECT set_config('app.tenant_id', :tenant, true)"),
        {"tenant": str(tenant_id)},
    )


def gerar_idempotency_key() -> str:
    return f"idem-f14a4-{secrets.token_hex(8)}"


def _digitos(quantidade: int) -> str:
    return str(uuid.uuid4().int)[:quantidade].zfill(quantidade)


@dataclass(frozen=True, slots=True)
class ContextoTenant:
    tenant_id: uuid.UUID
    tenant_slug: str
    empresa_id: uuid.UUID
    empresa_cnpj: str
    unidade_id: uuid.UUID
    rep_p_id: uuid.UUID
    colaborador_id: uuid.UUID
    colaborador_cpf: str
    colaborador_matricula: str
    vinculo_id: uuid.UUID
    dispositivo_id: uuid.UUID
    dispositivo_chave_publica: str
    usuario_id: uuid.UUID


async def _semear_tenant(sessao: AsyncSession, *, rotulo: str) -> ContextoTenant:
    """Semeia UM tenant completo: empresa, unidade com geocerca, REP-P ativo,
    colaborador com vinculo ativo, dispositivo celular vinculado (com
    `chave_publica`, para os testes de fila offline) e um usuario com sessao
    `web` reautenticada (para os testes que exigem `canal=web`). Publica
    `app.tenant_id` do proprio tenant ANTES de cada bloco de INSERT -- a
    policy `WITH CHECK` (RLS) recusaria a insercao de outra forma."""
    sufixo = f"{rotulo}-{uuid.uuid4().hex[:10]}"
    tenant_id = uuid.uuid4()
    tenant_slug = f"f14a4-{sufixo}"

    await aplicar_tenant_teste(sessao, tenant_id)

    await sessao.execute(
        text(
            "INSERT INTO tenants (id, slug, razao_social, nome_exibicao, status) "
            "VALUES (:id, :slug, :razao, :nome, 'ativo')"
        ),
        {
            "id": tenant_id,
            "slug": tenant_slug,
            "razao": f"Tenant adversarial {rotulo}",
            "nome": f"Tenant F14 A4 {rotulo}",
        },
    )

    empresa_id = uuid.uuid4()
    empresa_cnpj = _digitos(14)
    await sessao.execute(
        text(
            "INSERT INTO empresas "
            "(id, tenant_id, tipo, cnpj, razao_social, nome_fantasia, uf, codigo_ibge_municipio) "
            "VALUES (:id, :tenant_id, 'matriz', :cnpj, :razao, :fantasia, 'GO', '5208707')"
        ),
        {
            "id": empresa_id,
            "tenant_id": tenant_id,
            "cnpj": empresa_cnpj,
            "razao": f"Empresa adversarial {rotulo} Ltda",
            "fantasia": f"Empresa Teste F14 A4 {rotulo}",
        },
    )

    unidade_id = uuid.uuid4()
    await sessao.execute(
        text(
            "INSERT INTO unidades "
            "(id, tenant_id, empresa_id, codigo, nome, tipo, uf, codigo_ibge_municipio, "
            " geocerca_latitude, geocerca_longitude, geocerca_raio_metros, "
            " geocerca_tolerancia_metros, geocerca_obrigatoria) "
            "VALUES (:id, :tenant_id, :empresa_id, 'SEDE', :nome, 'sede', 'GO', "
            "        '5208707', :lat, :lon, :raio, :tolerancia, TRUE)"
        ),
        {
            "id": unidade_id,
            "tenant_id": tenant_id,
            "empresa_id": empresa_id,
            "nome": f"Sede adversarial {rotulo}",
            "lat": GEOCERCA_LATITUDE,
            "lon": GEOCERCA_LONGITUDE,
            "raio": GEOCERCA_RAIO_METROS,
            "tolerancia": GEOCERCA_TOLERANCIA_METROS,
        },
    )

    rep_p_id = uuid.uuid4()
    hoje = dt.date.today()
    await sessao.execute(
        text(
            "INSERT INTO rep_ps "
            "(id, tenant_id, empresa_id, identificador, tipo, numero_inpi, "
            " cnpj_desenvolvedor, razao_social_desenvolvedor, cnpj_empregador, "
            " razao_social_empregador, versao_programa, data_inicio_operacao, status) "
            "VALUES (:id, :tenant_id, :empresa_id, :identificador, 'rep_p', '12345678', "
            "        '60258502000149', 'SEEG Sistemas Ltda', :cnpj_empregador, "
            "        :razao_empregador, '1.0.0-teste', :inicio, 'ativo')"
        ),
        {
            "id": rep_p_id,
            "tenant_id": tenant_id,
            "empresa_id": empresa_id,
            "identificador": f"REP-{sufixo}",
            "cnpj_empregador": empresa_cnpj,
            "razao_empregador": f"Empresa adversarial {rotulo} Ltda",
            "inicio": hoje,
        },
    )
    await sessao.execute(
        text(
            "INSERT INTO nsr_sequencias (id, tenant_id, rep_p_id, proximo_nsr, ultimo_nsr_emitido) "
            "VALUES (:id, :tenant_id, :rep_p_id, 1, 0)"
        ),
        {"id": uuid.uuid4(), "tenant_id": tenant_id, "rep_p_id": rep_p_id},
    )

    colaborador_id = uuid.uuid4()
    colaborador_cpf = _digitos(11)
    colaborador_matricula = sufixo[:10]
    await sessao.execute(
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
            "nome": f"Colaborador adversarial {rotulo}",
            "admissao": hoje - dt.timedelta(days=365),
        },
    )

    vinculo_id = uuid.uuid4()
    await sessao.execute(
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
    # `chave_publica` deliberadamente um valor SIMPLES e PREVISIVEL: o proprio
    # nome da coluna diz "publica" -- os testes de replica offline usam este
    # valor para provar que QUALQUER pessoa que o conheça (por definicao, uma
    # chave publica nao e segredo) consegue forjar o HMAC stub do item.
    dispositivo_chave_publica = f"chave-publica-{sufixo}"
    await sessao.execute(
        text(
            "INSERT INTO dispositivos "
            "(id, tenant_id, empresa_id, unidade_id, tipo, plataforma, identificador, "
            " nome, chave_publica, status, attestation_status) "
            "VALUES (:id, :tenant_id, :empresa_id, :unidade_id, 'celular', 'android', "
            "        :identificador, :nome, :chave_publica, 'ativo', 'aprovado')"
        ),
        {
            "id": dispositivo_id,
            "tenant_id": tenant_id,
            "empresa_id": empresa_id,
            "unidade_id": unidade_id,
            "identificador": f"android-{sufixo}",
            "nome": f"Celular adversarial {rotulo}",
            "chave_publica": dispositivo_chave_publica,
        },
    )
    await sessao.execute(
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

    usuario_id = uuid.uuid4()
    await sessao.execute(
        text(
            "INSERT INTO usuarios (id, tenant_id, email, nome_completo, status) "
            "VALUES (:id, :tenant_id, :email, :nome, 'ativo')"
        ),
        {
            "id": usuario_id,
            "tenant_id": tenant_id,
            "email": f"usuario-{sufixo}@adversarial.f14a4.local",
            "nome": f"Usuario adversarial {rotulo}",
        },
    )
    await sessao.execute(
        text(
            "INSERT INTO sessoes "
            "(id, tenant_id, usuario_id, canal, iniciada_em, ultima_atividade_em, "
            " expira_em, reautenticado_em) "
            "VALUES (:id, :tenant_id, :usuario_id, 'web', now(), now(), "
            " now() + interval '1 hour', now())"
        ),
        {"id": uuid.uuid4(), "tenant_id": tenant_id, "usuario_id": usuario_id},
    )

    return ContextoTenant(
        tenant_id=tenant_id,
        tenant_slug=tenant_slug,
        empresa_id=empresa_id,
        empresa_cnpj=empresa_cnpj,
        unidade_id=unidade_id,
        rep_p_id=rep_p_id,
        colaborador_id=colaborador_id,
        colaborador_cpf=colaborador_cpf,
        colaborador_matricula=colaborador_matricula,
        vinculo_id=vinculo_id,
        dispositivo_id=dispositivo_id,
        dispositivo_chave_publica=dispositivo_chave_publica,
        usuario_id=usuario_id,
    )


@dataclass(frozen=True, slots=True)
class ContextoDoisTenants:
    tenant_a: ContextoTenant
    tenant_b: ContextoTenant


@pytest_asyncio.fixture
async def contexto_dois_tenants(sessao_f14a4: AsyncSession) -> ContextoDoisTenants:
    """Semeia DOIS tenants completos e isolados na mesma sessao/transacao,
    deixando `app.tenant_id` publicado como o do tenant A ao final (o caso
    comum: a maioria dos testes cross-tenant ataca "autenticado como A,
    tentando alcancar B"). Cada teste que precisar do contexto de B publica
    `aplicar_tenant_teste(sessao, tenant_b.tenant_id)` explicitamente."""
    tenant_a = await _semear_tenant(sessao_f14a4, rotulo="a")
    tenant_b = await _semear_tenant(sessao_f14a4, rotulo="b")

    await sessao_f14a4.commit()
    await aplicar_tenant_teste(sessao_f14a4, tenant_a.tenant_id)

    return ContextoDoisTenants(tenant_a=tenant_a, tenant_b=tenant_b)
