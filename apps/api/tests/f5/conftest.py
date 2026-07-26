"""Fixture da Fase F5 (T1 -- exclusiva do agente A1; ninguem mais edita este
arquivo -- PCF da fase, secao 5).

Banco de teste EXCLUSIVO deste agente (`ponto_f5_a1`), criado sob demanda a
partir da conexao administrativa apontada por `PONTO_TEST_DATABASE_URL`
(o mesmo Postgres 16 da VPS compartilhado por todos os agentes da onda, mas
cada agente com o seu proprio banco -- nunca compartilhar banco nem entre
agentes da mesma fase, para nao colidir escrita de fixture durante a execucao
paralela). Role de LOGIN propria (`ponto_f5_a1_login`, membro de `ponto_app`,
NUNCA superusuario) -- e a role sob a qual TODO teste de RLS/imutabilidade
desta fase roda; testar como o usuario administrativo (que tem `BYPASSRLS`)
mascararia exatamente os defeitos que estes testes existem para achar.

Duas camadas de fixture, do mesmo motivo que a F2 documentou: a suite roda
com `asyncio_default_fixture_loop_scope = "function"` (`pyproject.toml`), e
um recurso assincrono criado em escopo `session` nao sobrevive ao proximo
event loop.

1. `url_login_sessao` (escopo `session`, sincrona): cria o banco se
   necessario, migra (`alembic upgrade head`) e cria/atualiza a role de
   LOGIN. Roda uma unica vez por sessao de pytest.
2. `engine_f5` / `sessao_f5` (escopo `function`, assincronas): cada teste
   ganha sua propria engine/sessao, presa ao event loop daquele teste.
3. `contexto_f5` (escopo `function`): semeia, a cada teste, um tenant novo
   com 1 empresa, 1 unidade (geocerca de ponto+raio + uma faixa em
   `redes_permitidas`), 1 REP-P `ativo` (com a linha correspondente de
   `nsr_sequencias`, que o cadastro de REP-P da F12 cria junto -- esta
   fixture reproduz isso porque semeia `rep_ps` direto, sem passar pela
   rota), 1 colaborador com vinculo `apura_ponto=true` ativo na data
   corrente, e 1 dispositivo `tipo='celular'` com `dispositivo_vinculos`
   ativo para esse colaborador.

`dsn_superusuario_f5` expoe o DSN sincrono da conexao ADMINISTRATIVA (a
mesma que cria o banco e a role) para os dois testes adversariais da T4 que
precisam contornar o gatilho de imutabilidade para simular uma remocao
externa (`SET LOCAL session_replication_role = 'replica'`, nunca a role da
aplicacao) -- nunca usada para os testes de RLS/imutabilidade em si, que
sempre conectam como `ponto_f5_a1_login`.

Variavel de ambiente lida: `PONTO_TEST_DATABASE_URL` (string de conexao
`postgresql+asyncpg://usuario:senha@host:porta/postgres` de um Postgres 16
com privilegio de `CREATEDB`/`CREATEROLE`). Sem a variavel, cai no default de
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
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from pathlib import Path

import psycopg
import pytest
import pytest_asyncio
import sqlalchemy as sa
from psycopg import sql
from sqlalchemy import text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

RAIZ_API = Path(__file__).resolve().parents[2]

#: Default de desenvolvimento local. So usado quando `PONTO_TEST_DATABASE_URL`
#: nao esta definida -- nunca aponta para banco de ambiente real.
_URL_PADRAO_LOCAL = "postgresql+asyncpg://ponto:ponto@localhost:5432/postgres"

#: Banco EXCLUSIVO deste agente (F5/A1). Nunca compartilhado.
_NOME_BANCO = "ponto_f5_a1"

#: Role de LOGIN exclusiva desta fase/agente. Nomeada com o agente porque
#: roles sao objetos de CLUSTER (nao por banco): mesmo o banco sendo
#: exclusivo, o nome da role precisa ser unico entre todos os agentes
#: rodando em paralelo no mesmo Postgres.
_ROLE_LOGIN = "ponto_f5_a1_login"


def _url_administrativa() -> URL:
    bruta = os.environ.get("PONTO_TEST_DATABASE_URL", _URL_PADRAO_LOCAL)
    return make_url(bruta)


def _garantir_banco_exclusivo(url_admin: URL) -> URL:
    """`CREATE DATABASE ponto_f5_a1` se ainda nao existir (conectando ao banco
    de manutencao indicado pela URL administrativa, normalmente `postgres`).
    Devolve a URL administrativa apontando para o banco exclusivo."""
    dsn_manutencao = url_admin.set(drivername="postgresql").render_as_string(hide_password=False)
    with psycopg.connect(dsn_manutencao, autocommit=True) as conexao, conexao.cursor() as cursor:
        cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", (_NOME_BANCO,))
        if cursor.fetchone() is None:
            cursor.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(_NOME_BANCO)))
    return url_admin.set(database=_NOME_BANCO)


def _aplica_migracao(url_admin_banco_f5: URL) -> None:
    """`alembic upgrade head` contra o banco exclusivo, via subprocess (mesmo
    padrao da F2): evita prender um recurso assincrono ao event loop da
    fixture de sessao, que a suite nao reaproveita entre modulos de teste."""
    ambiente = dict(os.environ)
    ambiente["DATABASE_URL"] = url_admin_banco_f5.render_as_string(hide_password=False)
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
            "alembic upgrade head falhou ao preparar o banco de teste da F5/A1:\n"
            f"--- stdout ---\n{resultado.stdout}\n--- stderr ---\n{resultado.stderr}"
        )


def _cria_ou_atualiza_role_login(url_admin_banco_f5: URL, senha: str) -> None:
    dsn_admin = url_admin_banco_f5.set(drivername="postgresql").render_as_string(
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
def url_login_sessao() -> URL:
    """Garante o banco exclusivo, migra e devolve a `URL` assincrona da role
    de LOGIN desta fase/agente."""
    url_admin = _url_administrativa()
    url_admin_banco_f5 = _garantir_banco_exclusivo(url_admin)

    _aplica_migracao(url_admin_banco_f5)

    senha = secrets.token_urlsafe(24)
    _cria_ou_atualiza_role_login(url_admin_banco_f5, senha)

    url_login = url_admin_banco_f5.set(
        drivername="postgresql+asyncpg", username=_ROLE_LOGIN, password=senha
    )
    dsn_login = url_login.set(drivername="postgresql").render_as_string(hide_password=False)

    # Aquecimento com retentativa curta: a primeira conexao com a role recem
    # criada, atraves do tunel SSH ate a VPS, ocasionalmente falha uma vez por
    # latencia de rede (confirmado manualmente: a mesma senha reconectada logo
    # em seguida funciona) -- mesma causa e mesma mitigacao documentadas na
    # fixture da F2.
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
def dsn_superusuario_f5(url_login_sessao: URL) -> str:
    """DSN sincrono da conexao ADMINISTRATIVA contra o banco exclusivo desta
    fase/agente. Uso exclusivo dos testes adversariais da T4 que precisam
    contornar o gatilho de imutabilidade para simular remocao externa de uma
    linha. NUNCA para os testes de RLS/imutabilidade em si -- esses sempre
    conectam como `ponto_f5_a1_login` (`engine_f5`/`sessao_f5`), nunca como
    superusuario, porque o proprio `REVOKE`/gatilho nao se aplicaria a ele."""
    url_admin = _url_administrativa()
    url_admin_banco_f5 = url_admin.set(database=_NOME_BANCO, drivername="postgresql+psycopg")
    return url_admin_banco_f5.render_as_string(hide_password=False)


@pytest.fixture(scope="session")
def admin_engine_sync_f5(dsn_superusuario_f5: str) -> Iterator[sa.engine.Engine]:
    """Engine sincrona ADMINISTRATIVA (superusuario) contra o banco exclusivo
    desta fase/agente. Uso exclusivo dos testes adversariais da T4
    (`ALTER TABLE ... DISABLE/ENABLE TRIGGER ...` para simular remocao
    externa) -- mesmo padrao de `admin_engine_sync` em `tests/f1/rbac`."""
    engine = sa.create_engine(dsn_superusuario_f5, future=True)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest_asyncio.fixture
async def engine_f5(url_login_sessao: URL) -> AsyncIterator[AsyncEngine]:
    """Engine assincrona por teste, autenticada como a role de LOGIN da fase.

    `pool_size` modesto (T9 faz 10.000 chamadas concorrentes, mas a instancia
    de teste da VPS tem `max_connections=100` compartilhado por TODOS os
    agentes rodando em paralelo agora -- nao e limite por-agente. A
    corretude do NSR vem do bloqueio de linha no banco, nao do grau de
    paralelismo do teste; T9 limita a concorrencia efetiva do lado do teste
    com `asyncio.Semaphore`.
    """
    ultimo_erro: Exception | None = None
    for tentativa in range(8):
        engine = create_async_engine(
            url_login_sessao,
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
    raise RuntimeError(f"Nao foi possivel abrir a engine de teste da F5/A1: {ultimo_erro}")


@pytest_asyncio.fixture
async def sessao_f5(engine_f5: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """Sessao assincrona por teste. O teste decide quando commitar.

    Cuidado com `SET LOCAL` + `commit()`: `aplicar_tenant_teste` usa `SET
    LOCAL`, valido so ate o fim da transacao corrente (mesmo mecanismo de
    `app/db/sessao.py` em producao). Commitar no meio do teste e continuar
    exige chamar `aplicar_tenant_teste` de novo -- senao a policy de RLS
    deixa de enxergar `app.tenant_id` e toda consulta seguinte devolve vazio
    (nao erro).
    """
    fabrica = async_sessionmaker(engine_f5, expire_on_commit=False, autoflush=False)
    async with fabrica() as sessao:
        yield sessao
        await sessao.rollback()


async def aplicar_tenant_teste(sessao: AsyncSession, tenant_id: uuid.UUID) -> None:
    """Publica `app.tenant_id` na transacao corrente, como `app/db/sessao.py`
    faz em producao."""
    await sessao.execute(
        text("SELECT set_config('app.tenant_id', :tenant, true)"),
        {"tenant": str(tenant_id)},
    )


@dataclass(frozen=True, slots=True)
class ContextoF5:
    """IDs da semente minima da fase, usada pelos tres agentes (A1, A2, A3)."""

    tenant_id: uuid.UUID
    tenant_slug: str
    empresa_id: uuid.UUID
    empresa_cnpj: str
    unidade_id: uuid.UUID
    rep_p_id: uuid.UUID
    rep_p_identificador: str
    colaborador_id: uuid.UUID
    colaborador_cpf: str
    colaborador_matricula: str
    vinculo_id: uuid.UUID
    dispositivo_id: uuid.UUID
    dispositivo_vinculo_id: uuid.UUID
    #: Faixa CIDR ativa em `redes_permitidas` para a unidade (todos os canais).
    rede_permitida_cidr: str
    #: Centro e raio da geocerca da unidade, para os testes montarem pontos
    #: dentro/fora sem reler o banco.
    geocerca_latitude: float
    geocerca_longitude: float
    geocerca_raio_metros: int
    geocerca_tolerancia_metros: int


@pytest_asyncio.fixture
async def contexto_f5(sessao_f5: AsyncSession) -> ContextoF5:
    """Semeia, a cada teste, 1 tenant, 1 empresa, 1 unidade (geocerca
    ponto+raio + allowlist CIDR), 1 REP-P ativo (+ `nsr_sequencias`), 1
    colaborador com vinculo `apura_ponto=true` ativo hoje, e 1 dispositivo
    `celular` com `dispositivo_vinculos` ativo. Cada chamada gera identificadores
    novos -- nenhum teste compartilha semente com outro.
    """
    sufixo = uuid.uuid4().hex[:12]
    tenant_id = uuid.uuid4()
    tenant_slug = f"f5-{sufixo}"

    def _digitos(quantidade: int) -> str:
        """`quantidade` digitos decimais aleatorios -- `dom_cpf`/`dom_cnpj`
        exigem so-digito; `sufixo` (hex) contem letras a-f e nao serve aqui."""
        return str(uuid.uuid4().int)[:quantidade].zfill(quantidade)

    await aplicar_tenant_teste(sessao_f5, tenant_id)

    await sessao_f5.execute(
        text(
            "INSERT INTO tenants (id, slug, razao_social, nome_exibicao, status) "
            "VALUES (:id, :slug, :razao, :nome, 'ativo')"
        ),
        {
            "id": tenant_id,
            "slug": tenant_slug,
            "razao": "Tenant de teste da fase F5",
            "nome": "Tenant F5",
        },
    )

    empresa_id = uuid.uuid4()
    # 14 digitos, sem checksum real -- o dominio desta fase (`dom_cnpj`) so
    # valida formato, e a insercao e direta via SQL, sem passar pela validacao
    # de digito verificador da aplicacao.
    empresa_cnpj = _digitos(14)
    await sessao_f5.execute(
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
            "razao": "Empresa de teste F5 Ltda",
            "fantasia": "Empresa Teste F5",
        },
    )

    # Praca Civica, Goiania/GO, aproximadamente.
    unidade_id = uuid.uuid4()
    geocerca_latitude = -16.6799
    geocerca_longitude = -49.255
    geocerca_raio_metros = 100
    geocerca_tolerancia_metros = 50
    await sessao_f5.execute(
        text(
            "INSERT INTO unidades "
            "(id, tenant_id, empresa_id, codigo, nome, tipo, uf, codigo_ibge_municipio, "
            " geocerca_latitude, geocerca_longitude, geocerca_raio_metros, "
            " geocerca_tolerancia_metros, geocerca_obrigatoria) "
            "VALUES (:id, :tenant_id, :empresa_id, 'SEDE', 'Sede de teste F5', 'sede', 'GO', "
            "        '5208707', :lat, :lon, :raio, :tolerancia, TRUE)"
        ),
        {
            "id": unidade_id,
            "tenant_id": tenant_id,
            "empresa_id": empresa_id,
            "lat": geocerca_latitude,
            "lon": geocerca_longitude,
            "raio": geocerca_raio_metros,
            "tolerancia": geocerca_tolerancia_metros,
        },
    )

    rede_permitida_cidr = "203.0.113.0/24"
    await sessao_f5.execute(
        text(
            "INSERT INTO redes_permitidas "
            "(id, tenant_id, empresa_id, unidade_id, cidr, descricao, canal, ativo) "
            "VALUES (:id, :tenant_id, :empresa_id, :unidade_id, CAST(:cidr AS CIDR), "
            "        'Faixa de teste F5', NULL, TRUE)"
        ),
        {
            "id": uuid.uuid4(),
            "tenant_id": tenant_id,
            "empresa_id": empresa_id,
            "unidade_id": unidade_id,
            "cidr": rede_permitida_cidr,
        },
    )

    rep_p_id = uuid.uuid4()
    rep_p_identificador = f"REP-{sufixo}"
    hoje = dt.date.today()
    await sessao_f5.execute(
        text(
            "INSERT INTO rep_ps "
            "(id, tenant_id, empresa_id, identificador, tipo, numero_inpi, "
            " cnpj_desenvolvedor, razao_social_desenvolvedor, cnpj_empregador, "
            " razao_social_empregador, versao_programa, data_inicio_operacao, status) "
            "VALUES (:id, :tenant_id, :empresa_id, :identificador, 'rep_p', '12345678', "
            "        '60258502000149', 'SEEG Sistemas Ltda', :cnpj_empregador, "
            "        'Empresa de teste F5 Ltda', '1.0.0-teste', :inicio, 'ativo')"
        ),
        {
            "id": rep_p_id,
            "tenant_id": tenant_id,
            "empresa_id": empresa_id,
            "identificador": rep_p_identificador,
            "cnpj_empregador": empresa_cnpj,
            "inicio": hoje,
        },
    )
    # O cadastro de REP-P (F12, `POST /v1/fiscal/rep-ps`) cria a linha de
    # `nsr_sequencias` junto -- esta fixture reproduz o mesmo par porque
    # semeia `rep_ps` direto, sem passar pela rota daquela fase.
    await sessao_f5.execute(
        text(
            "INSERT INTO nsr_sequencias (id, tenant_id, rep_p_id, proximo_nsr, ultimo_nsr_emitido) "
            "VALUES (:id, :tenant_id, :rep_p_id, 1, 0)"
        ),
        {"id": uuid.uuid4(), "tenant_id": tenant_id, "rep_p_id": rep_p_id},
    )

    colaborador_id = uuid.uuid4()
    colaborador_cpf = _digitos(11)
    colaborador_matricula = sufixo[:10]
    await sessao_f5.execute(
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
            "nome": "Colaborador de Teste F5",
            "admissao": hoje - dt.timedelta(days=365),
        },
    )

    vinculo_id = uuid.uuid4()
    await sessao_f5.execute(
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
    await sessao_f5.execute(
        text(
            "INSERT INTO dispositivos "
            "(id, tenant_id, empresa_id, unidade_id, tipo, plataforma, identificador, "
            " nome, status, attestation_status) "
            "VALUES (:id, :tenant_id, :empresa_id, :unidade_id, 'celular', 'android', "
            "        :identificador, 'Celular de teste F5', 'ativo', 'aprovado')"
        ),
        {
            "id": dispositivo_id,
            "tenant_id": tenant_id,
            "empresa_id": empresa_id,
            "unidade_id": unidade_id,
            "identificador": f"android-{sufixo}",
        },
    )

    dispositivo_vinculo_id = uuid.uuid4()
    await sessao_f5.execute(
        text(
            "INSERT INTO dispositivo_vinculos "
            "(id, tenant_id, dispositivo_id, colaborador_id, status, aprovado_em) "
            "VALUES (:id, :tenant_id, :dispositivo_id, :colaborador_id, 'ativo', now())"
        ),
        {
            "id": dispositivo_vinculo_id,
            "tenant_id": tenant_id,
            "dispositivo_id": dispositivo_id,
            "colaborador_id": colaborador_id,
        },
    )

    await sessao_f5.commit()
    await aplicar_tenant_teste(sessao_f5, tenant_id)

    return ContextoF5(
        tenant_id=tenant_id,
        tenant_slug=tenant_slug,
        empresa_id=empresa_id,
        empresa_cnpj=empresa_cnpj,
        unidade_id=unidade_id,
        rep_p_id=rep_p_id,
        rep_p_identificador=rep_p_identificador,
        colaborador_id=colaborador_id,
        colaborador_cpf=colaborador_cpf,
        colaborador_matricula=colaborador_matricula,
        vinculo_id=vinculo_id,
        dispositivo_id=dispositivo_id,
        dispositivo_vinculo_id=dispositivo_vinculo_id,
        rede_permitida_cidr=rede_permitida_cidr,
        geocerca_latitude=geocerca_latitude,
        geocerca_longitude=geocerca_longitude,
        geocerca_raio_metros=geocerca_raio_metros,
        geocerca_tolerancia_metros=geocerca_tolerancia_metros,
    )
