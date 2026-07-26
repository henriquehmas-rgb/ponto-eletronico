"""Fixture da Fase F3 (T1 -- unica tarefa de A4 que toca este arquivo).

Unico arquivo desta fase que qualquer um dos quatro agentes edita, e e
EXCLUSIVAMENTE o agente A4 quem o edita (PCF da fase, secao 5). E consumido
por A1, A2 e A3 tambem -- se voce e um deles e precisa de mais alguma coisa
daqui, peca no relatorio, nao edite este arquivo.

O que esta fixture entrega, por teste (`contexto_f3`, escopo `function` --
cada teste semeia seu PROPRIO tenant, nunca reaproveita nem limpa dado de
outro teste, exatamente como `tests/f2/conftest.py`; e o que permite os 40+
cenarios do golden dataset conviverem sem colidir em nenhuma das constraints
`EXCLUDE` de vigencia de `vinculo_jornadas`/`escala_atribuicoes`):

* 1 tenant, 1 empresa.
* **Duas unidades em municipios de UFs diferentes** -- Sao Paulo/SP e
  Salvador/BA -- para provar que feriado municipal de uma nunca vaza para a
  outra (criterio de aceite 5 do PCF).
* 3 colaboradores e 3 vinculos, todos com `apura_ponto = TRUE`:
  - `vinculo_sp` (colaborador em `unidade_sp`);
  - `vinculo_ba` (colaborador em `unidade_ba`);
  - `vinculo_sem_unidade` (colaborador SEM unidade -- `vinculos.unidade_id`
    NULL -- caso de borda explicitamente decidido na secao 2 do PCF: sem
    unidade, o fuso efetivo cai para `empresas.fuso_horario` e nao ha nenhum
    `feriado_conjunto` aplicavel).

Duas camadas de fixture, de proposito (mesma razao de `tests/f2/conftest.py`):

1. `url_login_sessao` (escopo `session`, sincrona): migra o banco e cria a
   role de login. Roda uma unica vez por sessao de pytest.
2. `sessao_f3` / `contexto_f3` (escopo `function`, assincronas): cada teste
   ganha sua propria engine/sessao SQLAlchemy assincrona, ligada ao event
   loop daquele teste, autenticada como a role de LOGIN.

Nome da role de LOGIN derivado do nome do banco de
`PONTO_TEST_DATABASE_URL` (nunca hardcoded para um agente especifico): cada
agente da fase roda contra seu PROPRIO banco exclusivo (`ponto_f3_a1`,
`ponto_f3_a4`, ...), e a role e cluster-wide no Postgres -- derivar o nome da
role a partir do banco evita colisao de ALTER ROLE PASSWORD entre agentes
rodando em paralelo contra o mesmo cluster, sem exigir que este arquivo
compartilhado saiba qual agente esta rodando.

Variavel de ambiente lida: `PONTO_TEST_DATABASE_URL` (string de conexao
`postgresql+asyncpg://usuario:senha@host:porta/base` de um Postgres 16 **ja
existente e vazio**, sob superusuario ou usuario com privilegio de criar
roles). Sem a variavel, cai no default de desenvolvimento local -- nunca o
banco de nenhum ambiente real.

Nenhum `docker compose` aqui pelo mesmo motivo de F1/F2: o banco e um
PostgreSQL 16 real na VPS, alcancado por um tunel SSH ja aberto.
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

RAIZ_API = Path(__file__).resolve().parents[2]

#: Default de desenvolvimento local. So usado quando `PONTO_TEST_DATABASE_URL`
#: nao esta definida -- nunca aponta para banco de ambiente real.
_URL_PADRAO_LOCAL = "postgresql+asyncpg://ponto:ponto@localhost:5432/ponto"


def _url_superusuario() -> URL:
    bruta = os.environ.get("PONTO_TEST_DATABASE_URL", _URL_PADRAO_LOCAL)
    return make_url(bruta)


def _nome_role_login(url_super: URL) -> str:
    """Deriva o nome da role de LOGIN do nome do banco -- ver docstring do
    modulo (evita colisao entre agentes de F3 rodando contra bancos
    exclusivos distintos no mesmo cluster)."""
    base = re.sub(r"[^a-z0-9_]", "_", (url_super.database or "ponto").lower())
    return f"ponto_f3_login_{base}"


@pytest.fixture(scope="session")
def url_login_sessao() -> URL:
    """Migra o banco de teste e devolve a `URL` de conexao da role de LOGIN."""
    url_super = _url_superusuario()
    role_login = _nome_role_login(url_super)

    ambiente = dict(os.environ)
    ambiente["DATABASE_URL"] = url_super.render_as_string(hide_password=False)
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
            "alembic upgrade head falhou ao preparar o banco de teste da F3:\n"
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

    # Verificacao de aquecimento: a primeira conexao com a role de LOGIN logo
    # apos ALTER/CREATE ROLE, atraves do tunel SSH ate a VPS, ocasionalmente
    # falha uma vez por latencia de rede -- nao por senha errada. Poucas
    # tentativas curtas aqui evitam que essa instabilidade externa apareca
    # como falha aleatoria no meio da suite, num teste qualquer.
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
async def engine_f3(url_login_sessao: URL) -> AsyncIterator[AsyncEngine]:
    """Engine assincrona por teste, autenticada como a role de LOGIN da fase.

    A primeira conexao de cada engine nova, feita atraves do tunel SSH ate a
    VPS, falha ocasionalmente com um erro de autenticacao espurio (a mesma
    credencial reconectada logo em seguida funciona -- o Postgres da VPS e
    compartilhado por varios agentes de fase rodando em paralelo agora, cada
    um com seu proprio banco). Recriar a engine e tentar de novo algumas
    vezes evita que essa instabilidade externa apareca como falha de teste
    de negocio.
    """
    ultimo_erro: Exception | None = None
    for tentativa in range(8):
        engine = create_async_engine(
            url_login_sessao, pool_pre_ping=True, connect_args={"timeout": 8}
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
    raise RuntimeError(f"Nao foi possivel abrir a engine de teste da F3: {ultimo_erro}")


@pytest_asyncio.fixture
async def sessao_f3(engine_f3: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """Sessao assincrona por teste. O teste decide quando commitar.

    **Cuidado com `SET LOCAL` + `commit()`.** `aplicar_tenant_teste` usa
    `SET LOCAL`, que vale so ate o fim da transacao corrente -- exatamente
    como `app/db/sessao.py` faz em producao. Se o SEU teste commitar no meio
    e continuar operando na mesma sessao depois, a policy de RLS deixa de
    enxergar `app.tenant_id` (volta a NULL) e toda consulta seguinte devolve
    vazio -- nao um erro, um sumico silencioso de linha. Ou evite commit no
    meio do teste, ou chame `aplicar_tenant_teste` de novo logo depois.
    """
    fabrica = async_sessionmaker(engine_f3, expire_on_commit=False, autoflush=False)
    async with fabrica() as sessao:
        yield sessao
        await sessao.rollback()


async def aplicar_tenant_teste(sessao: AsyncSession, tenant_id: uuid.UUID) -> None:
    """Publica `app.tenant_id` na transacao corrente, como `app/db/sessao.py`
    faz em producao. Reexposta aqui para os testes nao precisarem lembrar do
    literal `SET LOCAL` nem da conversao de tipo."""
    await sessao.execute(
        text("SELECT set_config('app.tenant_id', :tenant, true)"),
        {"tenant": str(tenant_id)},
    )


@dataclass(frozen=True, slots=True)
class ContextoF3:
    """IDs da semente organizacional minima usada pelos testes da fase.

    `unidade_sp` (Sao Paulo/SP) e `unidade_ba` (Salvador/BA) sao os dois
    municipios de UFs diferentes exigidos pelo PCF (T1) -- o golden dataset
    (T8) associa um `feriado_conjunto` municipal so a uma delas para provar
    que o feriado municipal nao vaza para a outra unidade da mesma empresa
    (criterio de aceite 5).
    """

    tenant_id: uuid.UUID
    tenant_slug: str
    empresa_id: uuid.UUID
    empresa_fuso_horario: str
    unidade_sp_id: uuid.UUID
    unidade_sp_codigo_ibge: str
    unidade_sp_uf: str
    unidade_sp_fuso_horario: str
    unidade_ba_id: uuid.UUID
    unidade_ba_codigo_ibge: str
    unidade_ba_uf: str
    unidade_ba_fuso_horario: str
    colaborador_sp_id: uuid.UUID
    colaborador_ba_id: uuid.UUID
    colaborador_sem_unidade_id: uuid.UUID
    vinculo_sp_id: uuid.UUID
    vinculo_ba_id: uuid.UUID
    vinculo_sem_unidade_id: uuid.UUID


@pytest_asyncio.fixture
async def contexto_f3(sessao_f3: AsyncSession) -> ContextoF3:
    """Semeia 1 tenant, 1 empresa, 2 unidades (SP e BA) e 3 vinculos.

    Cada chamada gera tenant, CNPJ, CPFs e matriculas novos -- nenhum teste
    compartilha semente com outro (mesma isolacao de `tests/f2/conftest.py`).
    """
    sufixo = uuid.uuid4().hex[:10]
    tenant_id = uuid.uuid4()
    tenant_slug = f"f3-{sufixo}"

    await aplicar_tenant_teste(sessao_f3, tenant_id)

    await sessao_f3.execute(
        text(
            "INSERT INTO tenants (id, slug, razao_social, nome_exibicao, status) "
            "VALUES (:id, :slug, :razao, :nome, 'ativo')"
        ),
        {
            "id": tenant_id,
            "slug": tenant_slug,
            "razao": "Tenant de teste da fase F3",
            "nome": "Tenant F3",
        },
    )

    empresa_id = uuid.uuid4()
    empresa_fuso = "America/Sao_Paulo"
    cnpj = f"{secrets.randbelow(10**14):014d}"  # 14 digitos, sem checagem de DV
    await sessao_f3.execute(
        text(
            "INSERT INTO empresas "
            "(id, tenant_id, tipo, cnpj, razao_social, nome_fantasia, uf, "
            " codigo_ibge_municipio, fuso_horario) "
            "VALUES (:id, :tenant_id, 'matriz', :cnpj, :razao, :fantasia, 'SP', "
            "        '3550308', :fuso)"
        ),
        {
            "id": empresa_id,
            "tenant_id": tenant_id,
            "cnpj": cnpj,
            "razao": "Empresa de Teste F3 Ltda",
            "fantasia": "Empresa Teste F3",
            "fuso": empresa_fuso,
        },
    )

    # Sao Paulo/SP.
    unidade_sp_id = uuid.uuid4()
    unidade_sp_ibge = "3550308"
    unidade_sp_uf = "SP"
    unidade_sp_fuso = "America/Sao_Paulo"
    await sessao_f3.execute(
        text(
            "INSERT INTO unidades "
            "(id, tenant_id, empresa_id, codigo, nome, tipo, uf, codigo_ibge_municipio, "
            " fuso_horario, geocerca_obrigatoria) "
            "VALUES (:id, :tenant_id, :empresa_id, 'SEDE-SP', 'Sede Sao Paulo', 'sede', "
            "        :uf, :ibge, :fuso, FALSE)"
        ),
        {
            "id": unidade_sp_id,
            "tenant_id": tenant_id,
            "empresa_id": empresa_id,
            "uf": unidade_sp_uf,
            "ibge": unidade_sp_ibge,
            "fuso": unidade_sp_fuso,
        },
    )

    # Salvador/BA -- UF e municipio diferentes de SP de proposito (T1: "duas
    # unidades em municipios diferentes de UFs diferentes").
    unidade_ba_id = uuid.uuid4()
    unidade_ba_ibge = "2927408"
    unidade_ba_uf = "BA"
    unidade_ba_fuso = "America/Bahia"
    await sessao_f3.execute(
        text(
            "INSERT INTO unidades "
            "(id, tenant_id, empresa_id, codigo, nome, tipo, uf, codigo_ibge_municipio, "
            " fuso_horario, geocerca_obrigatoria) "
            "VALUES (:id, :tenant_id, :empresa_id, 'FILIAL-BA', 'Filial Salvador', 'filial', "
            "        :uf, :ibge, :fuso, FALSE)"
        ),
        {
            "id": unidade_ba_id,
            "tenant_id": tenant_id,
            "empresa_id": empresa_id,
            "uf": unidade_ba_uf,
            "ibge": unidade_ba_ibge,
            "fuso": unidade_ba_fuso,
        },
    )

    colaborador_sp_id = uuid.uuid4()
    colaborador_ba_id = uuid.uuid4()
    colaborador_sem_unidade_id = uuid.uuid4()
    for cid, matricula, nome in (
        (colaborador_sp_id, f"MAT-SP-{sufixo}", "Colaborador de Teste SP"),
        (colaborador_ba_id, f"MAT-BA-{sufixo}", "Colaborador de Teste BA"),
        (colaborador_sem_unidade_id, f"MAT-SU-{sufixo}", "Colaborador de Teste Sem Unidade"),
    ):
        cpf = f"{secrets.randbelow(10**11):011d}"
        await sessao_f3.execute(
            text(
                "INSERT INTO colaboradores "
                "(id, tenant_id, empresa_id, matricula, cpf, nome_completo, status) "
                "VALUES (:id, :tenant_id, :empresa_id, :matricula, :cpf, :nome, 'ativo')"
            ),
            {
                "id": cid,
                "tenant_id": tenant_id,
                "empresa_id": empresa_id,
                "matricula": matricula,
                "cpf": cpf,
                "nome": nome,
            },
        )

    vinculo_sp_id = uuid.uuid4()
    vinculo_ba_id = uuid.uuid4()
    vinculo_sem_unidade_id = uuid.uuid4()
    data_inicio_vinculo = _dt.date(2020, 1, 1)
    for vid, colaborador_id, unidade_id, esocial in (
        (vinculo_sp_id, colaborador_sp_id, unidade_sp_id, f"ESOC-SP-{sufixo}"),
        (vinculo_ba_id, colaborador_ba_id, unidade_ba_id, f"ESOC-BA-{sufixo}"),
        (vinculo_sem_unidade_id, colaborador_sem_unidade_id, None, f"ESOC-SU-{sufixo}"),
    ):
        await sessao_f3.execute(
            text(
                "INSERT INTO vinculos "
                "(id, tenant_id, colaborador_id, empresa_id, matricula_esocial, "
                " tipo_vinculo, unidade_id, data_inicio, apura_ponto, status) "
                "VALUES (:id, :tenant_id, :colaborador_id, :empresa_id, :esocial, "
                "        'empregado', :unidade_id, :data_inicio, TRUE, 'ativo')"
            ),
            {
                "id": vid,
                "tenant_id": tenant_id,
                "colaborador_id": colaborador_id,
                "empresa_id": empresa_id,
                "esocial": esocial,
                "unidade_id": unidade_id,
                "data_inicio": data_inicio_vinculo,
            },
        )

    await sessao_f3.commit()
    await aplicar_tenant_teste(sessao_f3, tenant_id)

    return ContextoF3(
        tenant_id=tenant_id,
        tenant_slug=tenant_slug,
        empresa_id=empresa_id,
        empresa_fuso_horario=empresa_fuso,
        unidade_sp_id=unidade_sp_id,
        unidade_sp_codigo_ibge=unidade_sp_ibge,
        unidade_sp_uf=unidade_sp_uf,
        unidade_sp_fuso_horario=unidade_sp_fuso,
        unidade_ba_id=unidade_ba_id,
        unidade_ba_codigo_ibge=unidade_ba_ibge,
        unidade_ba_uf=unidade_ba_uf,
        unidade_ba_fuso_horario=unidade_ba_fuso,
        colaborador_sp_id=colaborador_sp_id,
        colaborador_ba_id=colaborador_ba_id,
        colaborador_sem_unidade_id=colaborador_sem_unidade_id,
        vinculo_sp_id=vinculo_sp_id,
        vinculo_ba_id=vinculo_ba_id,
        vinculo_sem_unidade_id=vinculo_sem_unidade_id,
    )
