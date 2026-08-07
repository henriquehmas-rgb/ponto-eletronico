"""Fixture compartilhada da Fase F13 (A1, T1 -- único criador deste arquivo,
PCF `docs/fases/F13-api-publica-webhooks-integracoes.md` §5.2). Os outros
nove agentes da fase importam daqui; nenhum outro edita este arquivo --
fixtures específicas de um subgrupo (ex.: uma `webhooks_entregas` de
exemplo) vivem no `conftest.py` do próprio subdiretório (`tests/f13/
webhooks/conftest.py` etc.), que o pytest já compõe automaticamente com
este.

**Banco de teste: convenção desta sessão, diferente de F5/F12.** As fases
anteriores liam `PONTO_TEST_DATABASE_URL` como uma conexão ADMINISTRATIVA
(porta de entrada em `postgres`) e criavam um banco exclusivo com nome fixo
dentro da própria fixture. Nesta fase, com dez agentes rodando em paralelo
no MESMO working tree, cada um com o PRÓPRIO banco (`ponto_f13_<agente>`,
instrução do orquestrador para cada agente), `PONTO_TEST_DATABASE_URL` já
aponta direto para o banco exclusivo de quem está rodando o teste --
idêntica a `DATABASE_URL` (mesma instrução). Esta fixture funciona para
qualquer um dos dez: extrai o nome do banco da própria URL, garante que ele
existe (cria se faltar, contra a conexão de manutenção `postgres` do mesmo
servidor) e roda `alembic upgrade head` contra ele -- sem hardcodar nome de
agente nenhum.

Duas camadas de fixture, mesmo motivo que F2/F5/F12 já documentaram: a
suíte roda com `asyncio_default_fixture_loop_scope = "function"`
(`pyproject.toml`), e um recurso assíncrono criado em escopo `session` não
sobrevive ao próximo event loop.

1. `url_login_sessao_f13` (escopo `session`, síncrona): garante o banco e
   migra. Roda uma única vez por sessão de pytest.
2. `engine_f13`/`sessao_f13` (escopo `function`, assíncronas): cada teste
   ganha sua própria engine/sessão, presa ao event loop daquele teste.
3. `contexto_f13` (escopo `function`): semeia 1 tenant + 1 empresa + 1
   unidade mínimos -- só o que é genuinamente comum a QUALQUER teste desta
   fase (autenticação de cliente, webhooks, folha, importador, SSO). Dado
   de domínio específico (colaborador, marcação, REP-P, integração de
   folha) fica com o conftest do próprio subgrupo, que recebe `contexto_f13`
   como base.
4. Fábricas de cliente/credencial (`criar_api_client_teste`,
   `emitir_oauth_token_teste`, `criar_api_key_teste`,
   `cabecalhos_cliente_teste`): qualquer subgrupo cujas rotas usem
   `app.comum.autenticacao_cliente.exigir_escopo` (webhooks, integrações,
   e as três rotas novas de `admin`) monta a credencial de teste por aqui,
   nunca reimplementando geração de token/hash.

Variáveis de ambiente lidas: `PONTO_TEST_DATABASE_URL` (string de conexão
`postgresql+asyncpg://usuario:senha@host:porta/ponto_f13_<agente>`, o MESMO
banco de `DATABASE_URL`) e `PONTO_TEST_REDIS_URL` (para quem exercitar
`app.comum.limitador_taxa`, T4). Sem elas, cai em defaults de
desenvolvimento local -- nunca o banco/redis de nenhum ambiente real.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import hashlib
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
from ponto_contracts import ApiClient, ApiKey, OauthToken
from psycopg import sql
from sqlalchemy import text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

import app.db.sessao as _db_sessao
from app.identidade.tokens import oauth as oauth_mod

RAIZ_API = Path(__file__).resolve().parents[2]

#: Nome de env var que `app.db.sessao`/`app.core.config.Configuracao` leem
#: para a engine GLOBAL do processo (`DATABASE_URL`). Qualquer dependencia
#: que a propria aplicacao usaria em producao (`exigir_escopo`, T1, via
#: `app.identidade.autenticacao.tenant.sessao_com_tenant_resolvido`, que por
#: sua vez chama `app.db.sessao.fabrica_de_sessoes()`) passa por essa engine
#: singleton -- nunca pela `engine_f13`/`sessao_f13` desta fixture, que sao
#: so para o SETUP dos dados de teste. As duas PRECISAM apontar para o MESMO
#: banco (garantido pela instrucao operacional desta sessao: exportar
#: `DATABASE_URL` identica a `PONTO_TEST_DATABASE_URL`).

#: Default de desenvolvimento local. So usado quando `PONTO_TEST_DATABASE_URL`
#: nao esta definida -- nunca aponta para banco de ambiente real.
_URL_PADRAO_LOCAL = "postgresql+asyncpg://ponto:ponto@localhost:5432/ponto_f13_local"

_URL_REDIS_PADRAO_LOCAL = "redis://localhost:6379/1"


def _url_banco_teste() -> URL:
    bruta = os.environ.get("PONTO_TEST_DATABASE_URL", _URL_PADRAO_LOCAL)
    return make_url(bruta)


def _garantir_banco_existe(url_banco: URL) -> None:
    """Cria o banco de `url_banco` se ele ainda nao existir, contra a
    conexao de manutencao `postgres` do mesmo servidor/credenciais."""
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
    ambiente["DATABASE_URL_SYNC"] = url_banco.set(drivername="postgresql+psycopg").render_as_string(
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
            "alembic upgrade head falhou ao preparar o banco de teste da F13:\n"
            f"--- stdout ---\n{resultado.stdout}\n--- stderr ---\n{resultado.stderr}"
        )


@pytest.fixture(scope="session")
def url_login_sessao_f13() -> URL:
    """Garante o banco (cria se faltar) e migra. Devolve a `URL` assincrona
    de conexao -- a mesma role de `PONTO_TEST_DATABASE_URL` (nao cria role
    de LOGIN separada: cada agente ja recebeu credencial direta e exclusiva
    de banco pelo orquestrador desta sessao, diferente de F5/F12)."""
    url_banco = _url_banco_teste()
    _garantir_banco_existe(url_banco)
    _aplica_migracao(url_banco)

    dsn_sync = url_banco.set(drivername="postgresql").render_as_string(hide_password=False)
    ultimo_erro: Exception | None = None
    for tentativa in range(5):
        try:
            with psycopg.connect(dsn_sync, connect_timeout=5):
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


@pytest.fixture(scope="session")
def dsn_superusuario_f13(url_login_sessao_f13: URL) -> str:
    """DSN sincrono da conexao ADMINISTRATIVA contra o banco de teste desta
    fase/agente. Uso restrito a testes adversariais que precisam contornar
    um gatilho/constraint (ex.: forcar um cenario de corrida) -- nunca para
    os testes de negocio em si."""
    url_admin = url_login_sessao_f13.set(drivername="postgresql+psycopg")
    return url_admin.render_as_string(hide_password=False)


@pytest.fixture(scope="session")
def admin_engine_sync_f13(dsn_superusuario_f13: str) -> Iterator[sa.engine.Engine]:
    engine = sa.create_engine(dsn_superusuario_f13, future=True)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest_asyncio.fixture
async def engine_f13(url_login_sessao_f13: URL) -> AsyncIterator[AsyncEngine]:
    ultimo_erro: Exception | None = None
    for tentativa in range(8):
        engine = create_async_engine(
            url_login_sessao_f13,
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
    raise RuntimeError(f"Nao foi possivel abrir a engine de teste da F13: {ultimo_erro}")


@pytest_asyncio.fixture
async def sessao_f13(engine_f13: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """Sessao assincrona por teste. O teste decide quando commitar. Cuidado
    com `SET LOCAL` + `commit()`: `aplicar_tenant_teste` usa `SET LOCAL`,
    valido so ate o fim da transacao corrente -- commitar no meio do teste
    exige chamar `aplicar_tenant_teste` de novo."""
    fabrica = async_sessionmaker(engine_f13, expire_on_commit=False, autoflush=False)
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
class ContextoF13:
    """IDs da semente minima da fase, comuns a qualquer subgrupo (A1-A10)."""

    tenant_id: uuid.UUID
    tenant_slug: str
    empresa_id: uuid.UUID
    empresa_cnpj: str
    unidade_id: uuid.UUID


def _digitos(quantidade: int) -> str:
    """`quantidade` digitos decimais aleatorios -- `dom_cpf`/`dom_cnpj`
    exigem so digito."""
    return str(uuid.uuid4().int)[:quantidade].zfill(quantidade)


@pytest_asyncio.fixture
async def contexto_f13(sessao_f13: AsyncSession) -> ContextoF13:
    """Semeia, a cada teste, 1 tenant + 1 empresa + 1 unidade minimos. Cada
    chamada gera identificadores novos -- nenhum teste compartilha semente
    com outro."""
    sufixo = uuid.uuid4().hex[:12]
    tenant_id = uuid.uuid4()
    tenant_slug = f"f13-{sufixo}"

    await aplicar_tenant_teste(sessao_f13, tenant_id)

    await sessao_f13.execute(
        text(
            "INSERT INTO tenants (id, slug, razao_social, nome_exibicao, status) "
            "VALUES (:id, :slug, :razao, :nome, 'ativo')"
        ),
        {
            "id": tenant_id,
            "slug": tenant_slug,
            "razao": "Tenant de teste da fase F13",
            "nome": "Tenant F13",
        },
    )

    empresa_id = uuid.uuid4()
    empresa_cnpj = _digitos(14)
    await sessao_f13.execute(
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
            "razao": "Empresa de teste F13 Ltda",
            "fantasia": "Empresa Teste F13",
        },
    )

    unidade_id = uuid.uuid4()
    await sessao_f13.execute(
        text(
            "INSERT INTO unidades "
            "(id, tenant_id, empresa_id, codigo, nome, tipo, uf, codigo_ibge_municipio) "
            "VALUES (:id, :tenant_id, :empresa_id, 'SEDE', 'Sede de teste F13', 'sede', 'GO', "
            "        '5208707')"
        ),
        {"id": unidade_id, "tenant_id": tenant_id, "empresa_id": empresa_id},
    )

    await sessao_f13.commit()
    await aplicar_tenant_teste(sessao_f13, tenant_id)

    return ContextoF13(
        tenant_id=tenant_id,
        tenant_slug=tenant_slug,
        empresa_id=empresa_id,
        empresa_cnpj=empresa_cnpj,
        unidade_id=unidade_id,
    )


@pytest_asyncio.fixture(autouse=True)
async def _engine_global_isolada_por_teste() -> AsyncIterator[None]:
    """Zera a engine GLOBAL de `app.db.sessao` a cada teste (mesmo padrao
    que `tests/f1/autenticacao/conftest.py::_engine_isolada_por_teste` ja
    estabeleceu): sem isto, qualquer teste que exercite um caminho de
    producao que abre sessao pela fabrica singleton (`exigir_escopo`
    (T1) via `sessao_com_tenant_resolvido`, ou qualquer rota HTTP via
    TestClient) reusa uma engine/pool de conexao presa ao event loop do
    teste ANTERIOR (`asyncio_default_fixture_loop_scope = "function"`) e
    quebra com `RuntimeError: Event loop is closed` no meio do teste --
    facil de confundir com bug real (nota da sessao de build). `autouse`
    porque qualquer teste de qualquer subgrupo desta fase pode acionar essa
    engine sem declarar a fixture explicitamente."""
    from app.core.config import obter_configuracao

    obter_configuracao.cache_clear()
    _db_sessao._engine = None  # type: ignore[attr-defined]
    _db_sessao._fabrica = None  # type: ignore[attr-defined]
    _db_sessao._engine_loop = None  # type: ignore[attr-defined]
    yield
    if _db_sessao._engine is not None:  # type: ignore[attr-defined]
        await _db_sessao.encerrar_engine()


# =============================================================================
# Fabricas de cliente de API / credencial (para exercitar
# `app.comum.autenticacao_cliente.exigir_escopo` e afins sem reimplementar
# geracao/hash de token -- reaproveita `app.identidade.tokens.oauth`).
# =============================================================================


async def criar_api_client_teste(
    sessao: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    nome: str | None = None,
    ambiente: str = "producao",
    escopos: list[str] | None = None,
    ips_permitidos: list[str] | None = None,
    rate_limit_por_minuto: int = 600,
) -> ApiClient:
    """Insere um `ApiClient` de teste (INSERT direto: a criacao por HTTP e
    testada a parte em `tests/f13/nucleo/test_clientes_servico.py`; esta
    fabrica so precisa de uma linha valida para autenticar contra ela)."""
    sufixo = uuid.uuid4().hex[:10]
    _, hash_segredo = oauth_mod.gerar_client_secret()
    cliente = ApiClient(
        tenant_id=tenant_id,
        nome=nome or f"Cliente de teste {sufixo}",
        client_id=f"client_teste_{sufixo}",
        client_secret_hash=hash_segredo,
        tipo="confidencial",
        ambiente=ambiente,
        escopos=escopos if escopos is not None else ["webhooks:ler", "webhooks:escrever"],
        ips_permitidos=ips_permitidos,
        rate_limit_por_minuto=rate_limit_por_minuto,
        status="ativo",
    )
    sessao.add(cliente)
    await sessao.flush()
    return cliente


async def emitir_oauth_token_teste(
    sessao: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    cliente: ApiClient,
    escopos: list[str] | None = None,
    expira_em: dt.datetime | None = None,
    revogado_em: dt.datetime | None = None,
) -> str:
    """Insere um `OauthToken` `access` valido (ou ja expirado/revogado, se
    os parametros pedirem) e devolve o token EM CLARO -- so existe aqui,
    nunca persistido."""
    bruto = secrets.token_urlsafe(48)
    agora = dt.datetime.now(dt.UTC)
    token = OauthToken(
        tenant_id=tenant_id,
        api_client_id=cliente.id,
        tipo="access",
        token_hash=hashlib.sha256(bruto.encode("utf-8")).hexdigest(),
        escopos=escopos if escopos is not None else list(cliente.escopos or []),
        emitido_em=agora,
        expira_em=expira_em or (agora + dt.timedelta(hours=1)),
        revogado_em=revogado_em,
    )
    sessao.add(token)
    await sessao.flush()
    return bruto


async def criar_api_key_teste(
    sessao: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    cliente: ApiClient,
    escopos: list[str] | None = None,
    ambiente: str | None = None,
    expira_em: dt.datetime | None = None,
    revogada_em: dt.datetime | None = None,
) -> str:
    """Insere uma `ApiKey` valida (ou ja expirada/revogada) e devolve a
    chave EM CLARO -- so existe aqui, nunca persistida."""
    bruto, prefixo, hash_ = oauth_mod.gerar_api_key(
        prefixo_ambiente="prd" if (ambiente or cliente.ambiente) == "producao" else "sbx"
    )
    chave = ApiKey(
        tenant_id=tenant_id,
        api_client_id=cliente.id,
        prefixo=prefixo,
        hash=hash_,
        ambiente=ambiente or cliente.ambiente,
        escopos=escopos if escopos is not None else list(cliente.escopos or []),
        expira_em=expira_em,
        revogada_em=revogada_em,
    )
    sessao.add(chave)
    await sessao.flush()
    return bruto


def cabecalhos_cliente_teste(
    *, tenant_slug: str, token_bearer: str | None = None, api_key: str | None = None
) -> dict[str, str]:
    """Monta os cabecalhos HTTP de uma requisicao de cliente de integracao
    (`X-Tenant` + `Authorization: Bearer` OU `X-API-Key`). Passe exatamente
    um dos dois -- nunca os dois, para o teste exercitar um caminho por vez."""
    cabecalhos = {"X-Tenant": tenant_slug}
    if token_bearer:
        cabecalhos["Authorization"] = f"Bearer {token_bearer}"
    if api_key:
        cabecalhos["X-API-Key"] = api_key
    return cabecalhos
