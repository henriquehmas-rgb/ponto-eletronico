"""Fixture de banco da Fase F1: dois tenants reais sob Row Level Security.

Unico arquivo desta fase que qualquer um dos tres agentes edita, e e
EXCLUSIVAMENTE o agente A2 quem o edita (PCF da fase, secao 5). E consumido
por A1 e A3 tambem -- se voce e um deles e precisa de mais alguma coisa
daqui, peca no relatorio, nao edite este arquivo.

O que esta fixture entrega:

* `contexto_f1` (sessao de teste, uma vez): aplica `alembic upgrade head`
  contra o banco apontado por `PONTO_TEST_DATABASE_URL`, cria (ou reaproveita,
  de forma idempotente) uma role de **LOGIN nao-superusuario**
  (`GRANT ponto_app TO <role>`) e semeia **dois tenants distintos**
  (`tenant-a`, `tenant-b`), cada um com usuarios, credencial, sessao,
  dispositivo MFA, perfil, permissao, atribuicao de perfil, delegacao,
  configuracao e uma estrutura organizacional minima (empresa, unidade,
  departamento) -- material suficiente para o teste de isolamento (T3)
  cruzar pelo menos 10 tabelas de dominio distintas.
* `engine_f1` / `fabrica_f1`: engine e fabrica de sessoes assincronas,
  conectadas como a role de LOGIN (nunca como o usuario administrativo do
  bootstrap -- superusuario ignora RLS, e testar como ele mascararia
  exatamente o defeito que estes testes existem para achar).
* `abrir_sessao_tenant`: fabrica de sessao assincrona ja com
  `app.tenant_id` publicado via `SET LOCAL` (o mesmo mecanismo de
  `app/db/sessao.py:aplicar_tenant`).
* `cliente`: `TestClient` da aplicacao real, apontado para o banco de teste
  (para os testes que exercitam a API de ponta a ponta).
* `identidade` / `IdentidadeDeTeste` / `cabecalhos`: uma identidade pronta
  para autenticar via `POST /v1/auth/login` (tenant `tenant-a`, senha
  conhecida, hash Argon2id real gerado por
  `app.identidade.autenticacao.senha.gerar_hash`) e o par de cabecalhos
  (`X-Tenant` + `Idempotency-Key`) que toda chamada de escrita do contrato
  exige -- consumidos pelos testes de autenticacao (A1) e RBAC (A3).
* `sessao_db`: sessao assincrona ja publicada para o tenant de `identidade`
  (`tenant-a`), para manipular estado direto no banco e observar o efeito
  pelo `cliente` HTTP em seguida.

Por que nao ha `docker compose` aqui: o daemon do Docker nao esta disponivel
nesta maquina de desenvolvimento. O banco e um PostgreSQL 16 real na VPS,
alcancado por um tunel SSH ja aberto -- ver o Pacote de Contexto da fase para
a variavel de ambiente esperada.
"""

from __future__ import annotations

import contextlib
import datetime as _dt
import os
import secrets
import uuid
from collections.abc import AsyncIterator, Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from ponto_contracts import (
    Credencial,
    Delegacao,
    Departamento,
    Empresa,
    MfaDispositivo,
    Perfil,
    PerfilPermissao,
    Permissao,
    Tenant,
    TenantConfiguracao,
    Unidade,
    Usuario,
    UsuarioPerfil,
)
from ponto_contracts import Sessao as SessaoModelo
from sqlalchemy import text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session as SessaoSincrona

from app.identidade.autenticacao.senha import gerar_hash

RAIZ_API = Path(__file__).resolve().parents[2]  # apps/api

VARIAVEL_URL = "PONTO_TEST_DATABASE_URL"
#: Mesmo default de `app/core/config.py:Configuracao.database_url` -- generico,
#: nao e segredo, e so serve para a fixture ter *algum* alvo quando a variavel
#: de ambiente nao foi definida (o banco real de teste nunca fica hardcoded
#: aqui, so em `PONTO_TEST_DATABASE_URL`, no ambiente de quem roda o teste).
URL_PADRAO_LOCAL = "postgresql+asyncpg://ponto:ponto@localhost:5432/ponto"

#: Role de LOGIN criada por esta fixture. Fixa (nunca interpolada a partir de
#: entrada externa) para nao abrir brecha de injecao de identificador SQL.
PAPEL_LOGIN = "ponto_teste_f1_a2"

#: Unica permissao global usada pelos testes desta fase (catalogo `permissoes`
#: nao tem `tenant_id` e a role da aplicacao NAO tem INSERT nela -- por isso
#: e semeada pela conexao administrativa, nunca pela role de login).
CODIGO_PERMISSAO_TESTE = "teste_f1_a2.ler"

#: Senha em claro do admin de `tenant-a` (fixture `identidade`). Segredo de
#: teste descartavel, existe so neste banco efemero de uso exclusivo do
#: agente A2 -- nunca versionado em lugar nenhum alem deste literal de teste.
SENHA_IDENTIDADE_TESTE = "Senha-de-Teste-F1A2!23"


def url_teste() -> str:
    """URL do banco de teste, lida do ambiente (nunca hardcoded aqui)."""
    return os.environ.get(VARIAVEL_URL, URL_PADRAO_LOCAL).strip()


def _normaliza_para_asyncpg(url: URL) -> URL:
    if url.drivername in ("postgresql+psycopg", "postgresql", "postgres"):
        return url.set(drivername="postgresql+asyncpg")
    return url


def _normaliza_para_psycopg(url: URL) -> URL:
    if url.drivername in ("postgresql+asyncpg", "postgres+asyncpg", "postgresql"):
        return url.set(drivername="postgresql+psycopg")
    return url


def _agora() -> _dt.datetime:
    return _dt.datetime.now(_dt.UTC)


def _obter_ou_criar(
    sessao: SessaoSincrona,
    modelo: type[Any],
    filtros: dict[str, Any],
    valores: dict[str, Any],
) -> tuple[Any, bool]:
    """Busca pela chave natural; cria quando nao existir. Devolve (objeto, criou).

    Mesmo padrao de `migrations/seed_dev.py`: e o que torna a semeadura desta
    fixture idempotente entre execucoes sucessivas de `pytest` contra o mesmo
    banco (nao derruba nem recria o banco a cada rodada).
    """
    consulta = sa.select(modelo).filter_by(**filtros)
    existente = sessao.scalars(consulta).first()
    if existente is not None:
        return existente, False
    objeto = modelo(**{**filtros, **valores})
    sessao.add(objeto)
    sessao.flush()
    return objeto, True


# =============================================================================
# Provisionamento administrativo: migracao, role de login, permissao global
# =============================================================================
def _aplica_migracao(url_sync_admin: URL) -> None:
    """`alembic upgrade head` programatico contra o banco de teste."""
    cfg = Config(str(RAIZ_API / "alembic.ini"))
    cfg.set_main_option("script_location", str(RAIZ_API / "migrations"))
    antigo = os.environ.get("DATABASE_URL_SYNC")
    os.environ["DATABASE_URL_SYNC"] = url_sync_admin.render_as_string(hide_password=False)
    try:
        command.upgrade(cfg, "head")
    finally:
        if antigo is None:
            os.environ.pop("DATABASE_URL_SYNC", None)
        else:
            os.environ["DATABASE_URL_SYNC"] = antigo


def _provisiona_como_administrador(url_sync_admin: URL, senha_login: str) -> None:
    """Cria/atualiza a role de LOGIN e semeia a permissao global de teste.

    Conecta como o usuario administrativo de `PONTO_TEST_DATABASE_URL`
    (superusuario nesta instancia de teste), usado SOMENTE para provisionar --
    nunca para os testes de isolamento em si, que conectam como `PAPEL_LOGIN`
    (secao 9.3 do PCF: "nao rode teste de RLS conectado como ponto -
    superusuario ignora RLS").
    """
    engine = sa.create_engine(url_sync_admin, future=True)
    try:
        with engine.begin() as conexao:
            existe = conexao.execute(
                text("SELECT 1 FROM pg_roles WHERE rolname = :nome"), {"nome": PAPEL_LOGIN}
            ).first()
            # `senha_login` vem de `secrets.token_urlsafe` (alfabeto url-safe,
            # nunca contem aspas), mas o escape abaixo e defesa adicional:
            # CREATE ROLE/ALTER ROLE nao aceitam parametro vinculado na
            # clausula PASSWORD (a gramatica do Postgres exige uma constante
            # literal ali, nao um placeholder de bind).
            senha_literal = senha_login.replace("'", "''")
            if existe is None:
                conexao.execute(text(f"CREATE ROLE {PAPEL_LOGIN} LOGIN PASSWORD '{senha_literal}'"))
            else:
                conexao.execute(
                    text(f"ALTER ROLE {PAPEL_LOGIN} WITH LOGIN PASSWORD '{senha_literal}'")
                )
            # `ponto_app` e NOLOGIN (criada pela migration inicial). A role de
            # teste herda os privilegios dela por membership, sem ganhar
            # BYPASSRLS nenhum -- e o requisito central do PCF (T1).
            conexao.execute(text(f"GRANT ponto_app TO {PAPEL_LOGIN}"))

        with SessaoSincrona(engine) as sessao, sessao.begin():
            # `permissoes` e o catalogo GLOBAL (sem tenant_id, sem RLS), mas a
            # role da aplicacao teve INSERT/UPDATE/DELETE revogados nela pela
            # migration inicial -- por isso semeada aqui, pela conexao
            # administrativa, nunca pela role de login usada pelos testes.
            _obter_ou_criar(
                sessao,
                Permissao,
                {"codigo": CODIGO_PERMISSAO_TESTE},
                {
                    "recurso": "teste_f1_a2",
                    "acao": "ler",
                    "descricao": "Permissao de uso exclusivo da fixture de teste da F1/A2.",
                    "modulo": "teste",
                },
            )
    finally:
        engine.dispose()


# =============================================================================
# Semeadura de tenant
# =============================================================================
@dataclass(frozen=True, slots=True)
class UsuarioSemeado:
    id: uuid.UUID
    email: str


@dataclass(frozen=True, slots=True)
class TenantSemeado:
    """O que cada tenant semeado expoe aos testes de isolamento (T3)."""

    id: uuid.UUID
    slug: str
    nome_exibicao: str
    admin: UsuarioSemeado
    colaborador: UsuarioSemeado
    empresa_id: uuid.UUID
    unidade_id: uuid.UUID
    departamento_id: uuid.UUID
    credencial_id: uuid.UUID
    perfil_id: uuid.UUID
    perfil_permissao_id: uuid.UUID
    usuario_perfil_id: uuid.UUID
    mfa_dispositivo_id: uuid.UUID
    sessao_id: uuid.UUID
    delegacao_id: uuid.UUID
    tenant_configuracao_id: uuid.UUID
    configuracao_chave: str

    def ids_por_tabela(self) -> dict[str, uuid.UUID]:
        """Uma linha por tabela de dominio semeada, para o teste de SQL direto
        (T3) cruzar pelo menos 10 tabelas distintas."""
        return {
            "usuarios": self.admin.id,
            "credenciais": self.credencial_id,
            "sessoes": self.sessao_id,
            "mfa_dispositivos": self.mfa_dispositivo_id,
            "perfis": self.perfil_id,
            "perfil_permissoes": self.perfil_permissao_id,
            "usuario_perfis": self.usuario_perfil_id,
            "delegacoes": self.delegacao_id,
            "empresas": self.empresa_id,
            "unidades": self.unidade_id,
            "departamentos": self.departamento_id,
            "tenant_configuracoes": self.tenant_configuracao_id,
        }


def _semear_tenant(sessao: SessaoSincrona, *, slug: str, rotulo: str, letra: str) -> TenantSemeado:
    """Semeia (ou reaproveita) um tenant com dado em pelo menos 10 tabelas.

    A ordem importa: `tenants` e a UNICA tabela isolada por `id` (nao por
    `tenant_id`) -- por isso o UUID e resolvido/gerado e `app.tenant_id`
    publicado ANTES do primeiro INSERT, exatamente como
    `migrations/seed_dev.py` faz. Resolver um tenant JA existente exige
    `fn_resolve_tenant` (SECURITY DEFINER): sem ela, uma consulta direta
    filtrada por `slug` sob a role de login devolveria zero linhas mesmo que
    o tenant exista, porque `app.tenant_id` ainda nao aponta pra ele.
    """
    linha_existente = sessao.execute(
        text("SELECT id FROM fn_resolve_tenant(:slug)"), {"slug": slug}
    ).first()
    tenant_id = linha_existente.id if linha_existente is not None else uuid.uuid4()
    sessao.execute(text("SELECT set_config('app.tenant_id', :tid, true)"), {"tid": str(tenant_id)})

    tenant, _ = _obter_ou_criar(
        sessao,
        Tenant,
        {"slug": slug},
        {
            "id": tenant_id,
            "razao_social": f"Tenant de teste {rotulo} (F1/A2)",
            "nome_exibicao": f"Tenant {rotulo}",
            "status": "ativo",
            "plano": "enterprise",
        },
    )
    tenant_id = tenant.id  # idem se reaproveitado

    configuracao, _ = _obter_ou_criar(
        sessao,
        TenantConfiguracao,
        {"tenant_id": tenant_id, "chave": "teste.f1a2.marca"},
        {"categoria": "geral", "valor": {"rotulo": rotulo}},
    )

    # CNPJ deterministico (14 digitos, sem checksum real -- o dominio so
    # valida formato) a partir da letra do tenant, para a busca por chave
    # natural em `_obter_ou_criar` ser estavel entre execucoes sucessivas.
    cnpj_ficticio = f"1000000000{ord(letra):04d}"
    empresa, _ = _obter_ou_criar(
        sessao,
        Empresa,
        {"tenant_id": tenant_id, "cnpj": cnpj_ficticio},
        {
            "tipo": "matriz",
            "razao_social": f"Empresa de teste {rotulo}",
            "nome_fantasia": f"Empresa {rotulo}",
            "municipio": "Goiania",
            "uf": "GO",
            "fuso_horario": "America/Sao_Paulo",
            "ativo": True,
        },
    )

    unidade, _ = _obter_ou_criar(
        sessao,
        Unidade,
        {"tenant_id": tenant_id, "empresa_id": empresa.id, "codigo": "SEDE"},
        {
            "nome": f"Sede {rotulo}",
            "tipo": "sede",
            "municipio": "Goiania",
            "uf": "GO",
            "fuso_horario": "America/Sao_Paulo",
            "geocerca_obrigatoria": False,
            "geocerca_tolerancia_metros": 50,
            "ativo": True,
        },
    )

    departamento, _ = _obter_ou_criar(
        sessao,
        Departamento,
        {"tenant_id": tenant_id, "empresa_id": empresa.id, "codigo": "DEP01"},
        {"nome": f"Departamento {rotulo}"},
    )

    # Dominio "exemplo.com.br" (nao ".local"/".test"/".example" -- reservados
    # por RFC 2606 e recusados pelo validador de e-mail do pydantic
    # (`EmailStr`) usado por `LoginRequisicao`: um e-mail sob dominio
    # reservado nunca passaria em `POST /v1/auth/login`, o que quebraria
    # qualquer teste desta fixture que precise autenticar de verdade). Mesma
    # convencao de dominio de `tests/f1/autenticacao/conftest.py`.
    admin, _ = _obter_ou_criar(
        sessao,
        Usuario,
        {"tenant_id": tenant_id, "email": f"admin.{slug}.f1a2@exemplo.com.br"},
        {"nome_completo": f"Admin {rotulo}", "tipo": "humano", "status": "ativo"},
    )
    colaborador, _ = _obter_ou_criar(
        sessao,
        Usuario,
        {"tenant_id": tenant_id, "email": f"colaborador.{slug}.f1a2@exemplo.com.br"},
        {"nome_completo": f"Colaborador {rotulo}", "tipo": "humano", "status": "ativo"},
    )

    credencial, _ = _obter_ou_criar(
        sessao,
        Credencial,
        {"tenant_id": tenant_id, "usuario_id": admin.id, "tipo": "senha", "ativo": True},
        # Hash Argon2id REAL (nao um valor de fachada): a identidade do admin
        # de `tenant-a` precisa autenticar de verdade via `POST /v1/auth/login`
        # nos testes de A1/A3 (fixture `identidade`, mais abaixo).
        {"hash": gerar_hash(SENHA_IDENTIDADE_TESTE), "algoritmo": "argon2id"},
    )

    sessao_login, _ = _obter_ou_criar(
        sessao,
        SessaoModelo,
        {"tenant_id": tenant_id, "usuario_id": admin.id, "canal": "web"},
        {"expira_em": _agora() + _dt.timedelta(days=1)},
    )

    mfa, _ = _obter_ou_criar(
        sessao,
        MfaDispositivo,
        {"tenant_id": tenant_id, "usuario_id": admin.id, "tipo": "totp"},
        {"rotulo": "Autenticador de teste (fixture F1/A2)", "ativo": True},
    )

    perfil, _ = _obter_ou_criar(
        sessao,
        Perfil,
        {"tenant_id": tenant_id, "codigo": "perfil_teste_f1a2"},
        {"nome": f"Perfil de teste {rotulo}", "sistema": False, "escopo_padrao": "tenant"},
    )

    permissao = sessao.scalars(sa.select(Permissao).filter_by(codigo=CODIGO_PERMISSAO_TESTE)).one()
    perfil_permissao, _ = _obter_ou_criar(
        sessao,
        PerfilPermissao,
        {"tenant_id": tenant_id, "perfil_id": perfil.id, "permissao_id": permissao.id},
        {"concedida": True},
    )

    usuario_perfil, _ = _obter_ou_criar(
        sessao,
        UsuarioPerfil,
        {
            "tenant_id": tenant_id,
            "usuario_id": admin.id,
            "perfil_id": perfil.id,
            "escopo_tipo": "tenant",
        },
        {"incluir_subordinados": True},
    )

    delegacao, _ = _obter_ou_criar(
        sessao,
        Delegacao,
        {
            "tenant_id": tenant_id,
            "delegante_usuario_id": admin.id,
            "delegado_usuario_id": colaborador.id,
            "status": "ativa",
        },
        {
            "motivo": "Ferias de teste (fixture F1/A2)",
            "inicio_em": _agora() - _dt.timedelta(hours=1),
            "fim_em": _agora() + _dt.timedelta(days=1),
        },
    )

    return TenantSemeado(
        id=tenant_id,
        slug=slug,
        nome_exibicao=tenant.nome_exibicao,
        admin=UsuarioSemeado(id=admin.id, email=admin.email),
        colaborador=UsuarioSemeado(id=colaborador.id, email=colaborador.email),
        empresa_id=empresa.id,
        unidade_id=unidade.id,
        departamento_id=departamento.id,
        credencial_id=credencial.id,
        perfil_id=perfil.id,
        perfil_permissao_id=perfil_permissao.id,
        usuario_perfil_id=usuario_perfil.id,
        mfa_dispositivo_id=mfa.id,
        sessao_id=sessao_login.id,
        delegacao_id=delegacao.id,
        tenant_configuracao_id=configuracao.id,
        configuracao_chave="teste.f1a2.marca",
    )


@dataclass(frozen=True, slots=True)
class ContextoF1:
    """O que a fixture de sessao entrega aos tres agentes da F1."""

    url_login_async: str
    usuario_login: str
    senha_login: str
    tenant_a: TenantSemeado
    tenant_b: TenantSemeado
    permissao_codigo: str


@pytest.fixture(scope="session")
def contexto_f1() -> ContextoF1:
    """Migra, provisiona a role de login e semeia tenant-a/tenant-b (uma vez).

    Conexao sincrona (psycopg) de proposito: nao depende de nenhum event loop
    de asyncio, o que evita reusar conexao presa a um loop ja encerrado entre
    modulos de teste distintos (ver `app/db/sessao.py`, docstring "engine
    presa ao event loop", achado ao ligar esta mesma fixture contra o
    andaime).
    """
    url = url_teste()
    url_async = _normaliza_para_asyncpg(make_url(url))
    url_sync_admin = _normaliza_para_psycopg(make_url(url))

    _aplica_migracao(url_sync_admin)

    senha_login = secrets.token_urlsafe(32)
    _provisiona_como_administrador(url_sync_admin, senha_login)

    url_sync_login = url_sync_admin.set(username=PAPEL_LOGIN, password=senha_login)
    engine_login_sync = sa.create_engine(url_sync_login, future=True)
    try:
        with SessaoSincrona(engine_login_sync) as sessao, sessao.begin():
            tenant_a = _semear_tenant(sessao, slug="tenant-a", rotulo="A", letra="a")
        with SessaoSincrona(engine_login_sync) as sessao, sessao.begin():
            tenant_b = _semear_tenant(sessao, slug="tenant-b", rotulo="B", letra="b")
    finally:
        engine_login_sync.dispose()

    url_login_async = url_async.set(username=PAPEL_LOGIN, password=senha_login)

    return ContextoF1(
        url_login_async=url_login_async.render_as_string(hide_password=False),
        usuario_login=PAPEL_LOGIN,
        senha_login=senha_login,
        tenant_a=tenant_a,
        tenant_b=tenant_b,
        permissao_codigo=CODIGO_PERMISSAO_TESTE,
    )


# =============================================================================
# Sessao assincrona, conectada como a role de LOGIN (nunca como superusuario)
# =============================================================================
@pytest.fixture
async def engine_f1(contexto_f1: ContextoF1) -> AsyncIterator[AsyncEngine]:
    """Engine assincrona por teste -- nao reaproveita engine entre testes para
    nunca correr risco de reusar conexao presa a um event loop encerrado
    (cada teste assincrono do pytest-asyncio, no modo `function`, tem o seu)."""
    engine = create_async_engine(contexto_f1.url_login_async, pool_pre_ping=True)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
def fabrica_f1(engine_f1: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(bind=engine_f1, expire_on_commit=False, autoflush=False)


AbrirSessaoTenant = Callable[[uuid.UUID], contextlib.AbstractAsyncContextManager[AsyncSession]]


@pytest.fixture
def abrir_sessao_tenant(fabrica_f1: async_sessionmaker[AsyncSession]) -> AbrirSessaoTenant:
    """Fabrica: `async with abrir_sessao_tenant(tenant_id) as sessao: ...`.

    Publica `app.tenant_id` via `SET LOCAL` -- o mesmo mecanismo de
    `app/db/sessao.py:aplicar_tenant` -- antes de devolver a sessao. Quem
    quiser testar a AUSENCIA de tenant (nenhum `SET LOCAL` aplicado) abre a
    sessao direto pela `fabrica_f1`, sem passar por esta fabrica.
    """

    @contextlib.asynccontextmanager
    async def _abrir(tenant_id: uuid.UUID) -> AsyncIterator[AsyncSession]:
        async with fabrica_f1() as sessao:
            await sessao.execute(
                text("SELECT set_config('app.tenant_id', :tid, true)"), {"tid": str(tenant_id)}
            )
            yield sessao

    return _abrir


# =============================================================================
# Cliente HTTP da aplicacao real, apontado para o banco de teste
# =============================================================================
@pytest.fixture
def cliente(contexto_f1: ContextoF1) -> Iterator[TestClient]:
    """`TestClient` da aplicacao real (`app.main.criar_aplicacao`), com
    `DATABASE_URL` redirecionada para o banco de teste desta fixture.

    Usado como *context manager* (`with TestClient(app) as cliente`) de
    proposito: e o que mantem um unico portal/event loop estavel para todas
    as chamadas deste cliente, em vez do padrao usado por
    `tests/test_andaime.py` (sem context manager), que abre um loop novo por
    chamada e e a causa raiz do "Event loop is closed" documentado em
    `app/db/sessao.py`.
    """
    from app.core.config import obter_configuracao
    from app.main import criar_aplicacao

    antigo = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = contexto_f1.url_login_async
    obter_configuracao.cache_clear()
    try:
        aplicacao = criar_aplicacao()
        with TestClient(aplicacao, raise_server_exceptions=False) as cliente_http:
            yield cliente_http
    finally:
        if antigo is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = antigo
        obter_configuracao.cache_clear()


# =============================================================================
# Identidade pronta para autenticar (consumida por A1 e A3)
# =============================================================================
@dataclass(frozen=True, slots=True)
class IdentidadeDeTeste:
    """Uma identidade real, pronta para `POST /v1/auth/login`.

    Sempre a mesma: o admin de `tenant-a`, com senha conhecida e hash Argon2id
    real (`app.identidade.autenticacao.senha.gerar_hash`), gravado por
    `_semear_tenant`.
    """

    tenant_id: uuid.UUID
    tenant_slug: str
    usuario_id: uuid.UUID
    email: str
    senha: str


def cabecalhos(tenant_slug: str, *, idempotencia: str | None = None) -> dict[str, str]:
    """Cabecalhos padrao de uma chamada de teste: `X-Tenant` e `Idempotency-Key`.

    `Idempotency-Key` e gerada por chamada quando omitida (o contrato exige o
    cabecalho em todo POST/PUT/PATCH/DELETE, mas duas chamadas com a mesma
    chave e corpos diferentes respondem `PONTO-IDEM-002` -- gerar uma nova por
    padrao evita colisao acidental entre chamadas do mesmo teste).
    """
    return {
        "X-Tenant": tenant_slug,
        "Idempotency-Key": idempotencia or f"teste-f1-{uuid.uuid4()}",
    }


@pytest.fixture
def identidade(contexto_f1: ContextoF1) -> IdentidadeDeTeste:
    admin = contexto_f1.tenant_a.admin
    return IdentidadeDeTeste(
        tenant_id=contexto_f1.tenant_a.id,
        tenant_slug=contexto_f1.tenant_a.slug,
        usuario_id=admin.id,
        email=admin.email,
        senha=SENHA_IDENTIDADE_TESTE,
    )


@pytest.fixture
async def sessao_db(
    contexto_f1: ContextoF1, abrir_sessao_tenant: AbrirSessaoTenant
) -> AsyncIterator[AsyncSession]:
    """Sessao assincrona ja publicada para o tenant de `identidade` (`tenant-a`).

    Duas conexoes distintas ao mesmo banco -- esta e a que o `cliente` HTTP
    abre por tras dos panos a cada requisicao -- ficam visiveis uma a outra
    depois de `commit()`, o que permite um teste alterar estado aqui (por
    exemplo, forcar `bloqueado_ate` para simular o fim de uma janela de
    bloqueio) e depois observar o efeito via `cliente`.
    """
    async with abrir_sessao_tenant(contexto_f1.tenant_a.id) as sessao:
        yield sessao
