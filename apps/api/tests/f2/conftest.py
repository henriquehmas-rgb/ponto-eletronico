"""Fixture da Fase F2 (T1 -- parte do agente A1).

Uma unica fixture, usada pelos tres agentes da fase (A1, A2 e A3): ela sobe o
banco de teste, roda `alembic upgrade head`, cria a role de LOGIN sob a qual
todo teste da fase roda (Row Level Security so tem sentido testado por uma
role que nao seja superusuario) e semeia 1 tenant, 1 empresa matriz, 1 filial
e 2 unidades (uma com geocerca de ponto+raio, outra com poligono).

Duas camadas de fixture, de proposito:

1. `_url_login` (escopo `session`, sincrona): migra o banco e cria a role de
   login. Roda uma unica vez por sessao de pytest, com ferramental 100%
   sincrono (`psycopg` + `subprocess` do Alembic) -- a suite roda com
   `asyncio_default_fixture_loop_scope = "function"` (ver `pyproject.toml`),
   entao um recurso assincrono (conexao asyncpg, engine) criado no escopo de
   sessao nao sobreviveria ate o proximo teste, cujo event loop e outro.
2. `sessao_f2` / `contexto_organizacional` (escopo `function`, assincronas):
   cada teste ganha sua propria engine/sessao SQLAlchemy assincrona, ligada ao
   event loop daquele teste, autenticada como a role de LOGIN.

Isolamento entre testes: cada chamada de `contexto_organizacional` semeia um
tenant **novo** (slug e CNPJ aleatorios), nunca reaproveita nem limpa dado de
outro teste. Não há necessidade de truncar nada entre testes -- o RLS garante
que um tenant nunca enxerga a semente de outro, e a role de LOGIN nao tem
sequer o privilegio de TRUNCATE (so SELECT/INSERT/UPDATE/DELETE, herdado de
`ponto_app`).

Variavel de ambiente lida: `PONTO_TEST_DATABASE_URL` (string de conexao
`postgresql+asyncpg://usuario:senha@host:porta/base` de um Postgres 16 **ja
existente e vazio**, sob superusuario ou usuario com privilegio de criar
roles). Sem a variavel, cai no default de desenvolvimento local -- nunca o
banco de nenhum ambiente real.
"""

from __future__ import annotations

import asyncio
import json
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

RAIZ_API = Path(__file__).resolve().parents[2]

#: Default de desenvolvimento local. So usado quando `PONTO_TEST_DATABASE_URL`
#: nao esta definida -- nunca aponta para banco de ambiente real.
_URL_PADRAO_LOCAL = "postgresql+asyncpg://ponto:ponto@localhost:5432/ponto"

#: Role de LOGIN criada para os testes da fase. Membra de `ponto_app`
#: (criada por `0001_inicial`, NOLOGIN por si so) para herdar exatamente os
#: privilegios de tabela que a aplicacao usa em producao -- nem mais
#: (superusuario ignoraria RLS), nem menos.
_ROLE_LOGIN = "ponto_f2_teste_login"


def _url_superusuario() -> URL:
    bruta = os.environ.get("PONTO_TEST_DATABASE_URL", _URL_PADRAO_LOCAL)
    return make_url(bruta)


@pytest.fixture(scope="session")
def url_login_sessao() -> URL:
    """Migra o banco de teste e devolve a `URL` de conexao da role de LOGIN."""
    url_super = _url_superusuario()

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
            "alembic upgrade head falhou ao preparar o banco de teste da F2:\n"
            f"--- stdout ---\n{resultado.stdout}\n--- stderr ---\n{resultado.stderr}"
        )

    senha = secrets.token_urlsafe(24)
    dsn_super = url_super.set(drivername="postgresql").render_as_string(hide_password=False)
    with psycopg.connect(dsn_super, autocommit=True) as conexao, conexao.cursor() as cursor:
        cursor.execute(sql.SQL("SELECT 1 FROM pg_roles WHERE rolname = %s"), (_ROLE_LOGIN,))
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

    url_login = url_super.set(drivername="postgresql+asyncpg", username=_ROLE_LOGIN, password=senha)
    dsn_login = url_login.set(drivername="postgresql").render_as_string(hide_password=False)

    # Verificacao de aquecimento: a primeira conexao com a role de LOGIN logo
    # apos ALTER/CREATE ROLE, atraves do tunel SSH ate a VPS, ocasionalmente
    # falha uma vez por latencia de rede -- nao por senha errada (confirmado
    # manualmente: a mesma senha reconectada logo em seguida funciona).
    # Poucas tentativas curtas aqui evitam que essa instabilidade externa
    # apareca como falha aleatoria no meio da suite, num teste qualquer.
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
async def engine_f2(url_login_sessao: URL) -> AsyncIterator[AsyncEngine]:
    """Engine assincrona por teste, autenticada como a role de LOGIN da fase.

    A primeira conexao de cada engine nova, feita atraves do tunel SSH ate a
    VPS, falha ocasionalmente com um `InvalidPasswordError` espurio (a mesma
    credencial reconectada logo em seguida funciona -- nao e senha errada; o
    Postgres da VPS e compartilhado por varios agentes de fase rodando em
    paralelo agora, cada um com seu proprio banco, e a instabilidade e desse
    contexto de carga concorrente no cluster, nao do cadastro desta fase).
    Recriar a engine e tentar de novo algumas vezes evita que essa
    instabilidade externa apareca como falha de teste de negocio.
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
    raise RuntimeError(f"Nao foi possivel abrir a engine de teste da F2: {ultimo_erro}")


@pytest_asyncio.fixture
async def sessao_f2(engine_f2: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """Sessao assincrona por teste. O teste decide quando commitar.

    **Cuidado com `SET LOCAL` + `commit()`.** `aplicar_tenant_teste` usa
    `SET LOCAL`, que vale so ate o fim da transacao corrente -- exatamente
    como `app/db/sessao.py` faz em producao (uma transacao por requisicao,
    commit unico no fim). Se o SEU teste commitar no meio (`await
    sessao.commit()`) e continuar operando na mesma sessao depois, a policy de
    RLS deixa de enxergar `app.tenant_id` (volta a NULL) e toda consulta
    seguinte devolve vazio -- nao um erro, um sumico silencioso de linha. Ou
    evite commit no meio do teste (o `flush()` que os services desta fase
    fazem ja torna a escrita visivel dentro da mesma transacao), ou chame
    `aplicar_tenant_teste` de novo logo depois de cada commit.
    """
    fabrica = async_sessionmaker(engine_f2, expire_on_commit=False, autoflush=False)
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
class ContextoOrganizacional:
    """IDs da semente organizacional minima usada pelos testes da fase."""

    tenant_id: uuid.UUID
    tenant_slug: str
    empresa_matriz_id: uuid.UUID
    empresa_matriz_cnpj: str
    empresa_filial_id: uuid.UUID
    empresa_filial_cnpj: str
    unidade_ponto_raio_id: uuid.UUID
    unidade_poligono_id: uuid.UUID


@pytest_asyncio.fixture
async def contexto_organizacional(sessao_f2: AsyncSession) -> ContextoOrganizacional:
    """Semeia 1 tenant, 1 empresa matriz, 1 filial e 2 unidades.

    Uma unidade tem geocerca de ponto mais raio (Av. Paulista, 1000 - Sao
    Paulo/SP); a outra tem geocerca poligonal (um quadrilatero simples em
    volta do mesmo ponto). Cada chamada gera tenant e CNPJs novos -- nenhum
    teste compartilha semente com outro.
    """
    sufixo = uuid.uuid4().hex[:12]
    tenant_id = uuid.uuid4()
    tenant_slug = f"f2-{sufixo}"

    await aplicar_tenant_teste(sessao_f2, tenant_id)

    await sessao_f2.execute(
        text(
            "INSERT INTO tenants (id, slug, razao_social, nome_exibicao, status) "
            "VALUES (:id, :slug, :razao, :nome, 'ativo')"
        ),
        {
            "id": tenant_id,
            "slug": tenant_slug,
            "razao": "Tenant de teste da fase F2",
            "nome": "Tenant F2",
        },
    )

    empresa_matriz_id = uuid.uuid4()
    empresa_matriz_cnpj = "11222333000181"
    await sessao_f2.execute(
        text(
            "INSERT INTO empresas "
            "(id, tenant_id, tipo, cnpj, razao_social, nome_fantasia, uf, "
            " codigo_ibge_municipio) "
            "VALUES (:id, :tenant_id, 'matriz', :cnpj, :razao, :fantasia, 'SP', '3550308')"
        ),
        {
            "id": empresa_matriz_id,
            "tenant_id": tenant_id,
            "cnpj": empresa_matriz_cnpj,
            "razao": "Empresa Matriz de Teste F2 Ltda",
            "fantasia": "Matriz Teste F2",
        },
    )

    empresa_filial_id = uuid.uuid4()
    empresa_filial_cnpj = "11222333000262"
    await sessao_f2.execute(
        text(
            "INSERT INTO empresas "
            "(id, tenant_id, matriz_id, tipo, cnpj, razao_social, nome_fantasia, uf, "
            " codigo_ibge_municipio) "
            "VALUES (:id, :tenant_id, :matriz_id, 'filial', :cnpj, :razao, :fantasia, 'RJ', "
            "        '3304557')"
        ),
        {
            "id": empresa_filial_id,
            "tenant_id": tenant_id,
            "matriz_id": empresa_matriz_id,
            "cnpj": empresa_filial_cnpj,
            "razao": "Empresa Matriz de Teste F2 Ltda - Filial 1",
            "fantasia": "Filial Teste F2",
        },
    )

    # Av. Paulista, 1000 - Sao Paulo/SP, aproximadamente.
    unidade_ponto_raio_id = uuid.uuid4()
    await sessao_f2.execute(
        text(
            "INSERT INTO unidades "
            "(id, tenant_id, empresa_id, codigo, nome, tipo, uf, codigo_ibge_municipio, "
            " geocerca_latitude, geocerca_longitude, geocerca_raio_metros, "
            " geocerca_tolerancia_metros) "
            "VALUES (:id, :tenant_id, :empresa_id, 'SEDE', 'Sede Av. Paulista', 'sede', 'SP', "
            "        '3550308', -23.5613, -46.6558, 100, 50)"
        ),
        {
            "id": unidade_ponto_raio_id,
            "tenant_id": tenant_id,
            "empresa_id": empresa_matriz_id,
        },
    )

    # Quadrilatero simples (~140 m de lado) em volta do mesmo ponto.
    poligono = {
        "type": "Polygon",
        "coordinates": [
            [
                [-46.6570, -23.5605],
                [-46.6546, -23.5605],
                [-46.6546, -23.5621],
                [-46.6570, -23.5621],
                [-46.6570, -23.5605],
            ]
        ],
    }
    unidade_poligono_id = uuid.uuid4()
    await sessao_f2.execute(
        text(
            "INSERT INTO unidades "
            "(id, tenant_id, empresa_id, codigo, nome, tipo, uf, codigo_ibge_municipio, "
            " geocerca_poligono, geocerca_tolerancia_metros) "
            "VALUES (:id, :tenant_id, :empresa_id, 'FILIAL-POL', 'Filial com poligono', "
            "        'filial', 'RJ', '3304557', CAST(:poligono AS JSONB), 50)"
        ),
        {
            "id": unidade_poligono_id,
            "tenant_id": tenant_id,
            "empresa_id": empresa_filial_id,
            "poligono": json.dumps(poligono),
        },
    )

    await sessao_f2.commit()
    await aplicar_tenant_teste(sessao_f2, tenant_id)

    return ContextoOrganizacional(
        tenant_id=tenant_id,
        tenant_slug=tenant_slug,
        empresa_matriz_id=empresa_matriz_id,
        empresa_matriz_cnpj=empresa_matriz_cnpj,
        empresa_filial_id=empresa_filial_id,
        empresa_filial_cnpj=empresa_filial_cnpj,
        unidade_ponto_raio_id=unidade_ponto_raio_id,
        unidade_poligono_id=unidade_poligono_id,
    )
