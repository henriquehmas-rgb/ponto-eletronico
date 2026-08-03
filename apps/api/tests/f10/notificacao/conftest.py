"""Fixture local dos testes de `app.notificacao` (T10/T11, agente A3).

`apps/api/tests/f10/conftest.py` (a fixture COMPARTILHADA da fase inteira,
ownership exclusivo de A1, PCF §5, T1) pode não existir ainda no momento em
que este módulo roda -- os quatro agentes da fase rodam em paralelo. Para
não bloquear a suíte de A3 na ordem de chegada, este `conftest.py` é uma
cópia LOCAL e INDEPENDENTE, território exclusivo de
`apps/api/tests/f10/notificacao/**` (ownership de A3), que nunca edita nem
substitui o arquivo compartilhado de A1. Ela replica apenas a FORMA de
bootstrap já estabelecida por `tests/f3/conftest.py` (migração + role de
LOGIN derivada do nome do banco + sessão por teste sob RLS) -- mesmo
precedente que `tests/f4/tratamento/conftest.py` (A3) e
`tests/f4/banco_horas/conftest.py` (A2) já documentaram para o mesmo
problema estrutural, nunca a lógica de negócio de outra fase.

Semente mínima por teste (escopo `function`, nunca reaproveitada entre
testes): 1 tenant `status='ativo'`, 1 empresa, 1 unidade
(`America/Sao_Paulo`), 2 colaboradores COM vínculo `usuarios` (um
"solicitante", um "aprovador" -- o motor de notificação precisa do elo
`usuarios.colaborador_id` para resolver destinatário, e a fila de aprovação
precisa de um `aprovador_usuario_id` real), 1 `tipos_solicitacao`
(categoria `ajuste_ponto`, uma etapa `gestor`), 1 `Solicitacao` `pendente` e
1 `Aprovacao` (`etapa=1`, `decisao='pendente'`) -- o suficiente para os
testes do motor (T10), da varredura cross-tenant (T11) e da fila de envio
(T11) desta fase, sem depender de jornada/escala (F3) nem de marcação real
(F5).
"""

from __future__ import annotations

import asyncio
import datetime as dt
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

#: Default de desenvolvimento local. Só usado quando `PONTO_TEST_DATABASE_URL`
#: não está definida -- nunca aponta para banco de ambiente real.
_URL_PADRAO_LOCAL = "postgresql+asyncpg://ponto:ponto@localhost:5432/ponto"


def _url_superusuario() -> URL:
    bruta = os.environ.get("PONTO_TEST_DATABASE_URL", _URL_PADRAO_LOCAL)
    return make_url(bruta)


def _nome_role_login(url_super: URL) -> str:
    """Deriva o nome da role de LOGIN do nome do banco -- evita colisão de
    `ALTER ROLE PASSWORD` entre agentes da fase rodando em paralelo contra o
    mesmo cluster (cada um com seu próprio banco exclusivo)."""
    base = re.sub(r"[^a-z0-9_]", "_", (url_super.database or "ponto").lower())
    return f"ponto_f10_a3_login_{base}"


@pytest.fixture(scope="session")
def url_login_sessao_notificacao() -> URL:
    """Migra o banco de teste e devolve a `URL` de conexão da role de
    LOGIN. Escopo `session`: `alembic upgrade head` roda uma única vez por
    sessão de pytest."""
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
            "alembic upgrade head falhou ao preparar o banco de teste da F10/A3:\n"
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

    ultimo_erro: Exception | None = None
    for tentativa in range(5):
        try:
            with psycopg.connect(dsn_login, connect_timeout=5):
                pass
            break
        except Exception as exc:  # pragma: no cover - só em falha real de rede
            ultimo_erro = exc
            time.sleep(0.3 * (tentativa + 1))
    else:
        raise RuntimeError(
            f"Não foi possível validar a role de LOGIN após 5 tentativas: {ultimo_erro}"
        )

    return url_login


@pytest_asyncio.fixture
async def engine_notificacao(url_login_sessao_notificacao: URL) -> AsyncIterator[AsyncEngine]:
    """Engine assíncrona por teste, autenticada como a role de LOGIN da
    fase. Reconecta algumas vezes: a primeira conexão de uma engine nova,
    através do túnel SSH até a VPS, ocasionalmente falha uma vez por
    latência de rede (mesmo padrão de `tests/f3/conftest.py`)."""
    ultimo_erro: Exception | None = None
    for tentativa in range(8):
        engine = create_async_engine(
            url_login_sessao_notificacao, pool_pre_ping=True, connect_args={"timeout": 8}
        )
        try:
            async with asyncio.timeout(10):
                async with engine.connect():
                    pass
        except Exception as exc:  # pragma: no cover - só em falha real de rede
            ultimo_erro = exc
            await engine.dispose()
            await asyncio.sleep(min(0.5 * (tentativa + 1), 3.0))
            continue
        try:
            yield engine
        finally:
            await engine.dispose()
        return
    raise RuntimeError(f"Não foi possível abrir a engine de teste da F10/A3: {ultimo_erro}")


@pytest_asyncio.fixture
async def sessao_notificacao(engine_notificacao: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """Sessão assíncrona por teste, autenticada como a role de LOGIN (nunca
    superusuário) -- RLS sempre ativa. O teste decide quando comitar."""
    fabrica = async_sessionmaker(engine_notificacao, expire_on_commit=False, autoflush=False)
    async with fabrica() as sessao:
        yield sessao
        await sessao.rollback()


async def aplicar_tenant_teste(sessao: AsyncSession, tenant_id: uuid.UUID) -> None:
    """Publica `app.tenant_id` na transação corrente, como
    `app/db/sessao.py` faz em produção."""
    await sessao.execute(
        text("SELECT set_config('app.tenant_id', :tenant, true)"),
        {"tenant": str(tenant_id)},
    )


@dataclass(frozen=True, slots=True)
class ContextoNotificacao:
    """IDs da semente mínima usada pelos testes de `app.notificacao`."""

    tenant_id: uuid.UUID
    tenant_slug: str
    empresa_id: uuid.UUID
    unidade_id: uuid.UUID
    colaborador_id: uuid.UUID
    usuario_id: uuid.UUID
    vinculo_id: uuid.UUID
    aprovador_colaborador_id: uuid.UUID
    aprovador_usuario_id: uuid.UUID
    tipo_solicitacao_id: uuid.UUID
    solicitacao_id: uuid.UUID
    aprovacao_id: uuid.UUID


async def semear_tenant_minimo(
    sessao: AsyncSession, *, sufixo: str | None = None, status_tenant: str = "ativo"
) -> ContextoNotificacao:
    """Semeia tenant + empresa + unidade + 2 colaboradores (com `usuarios`
    vinculados) + 1 `tipos_solicitacao`/`Solicitacao`/`Aprovacao` pendente
    -- via `INSERT` direto, nunca pela API (mesmo padrão de
    `tests/f3/conftest.py`).

    Função (não fixture) para os testes de `fn_tenants_ativos()`/varredura
    cross-tenant (T11) poderem chamá-la mais de uma vez na mesma sessão,
    com tenants diferentes, e provar a enumeração cross-tenant.

    `sufixo`, quando informado, é um RÓTULO (não o sufixo final): sempre
    combinado com um hex aleatório, para os testes que COMITAM de verdade
    (cross-tenant) nunca colidirem com `uq_tenants_slug` numa reexecução da
    suíte.
    """
    rotulo = f"{sufixo}-" if sufixo else ""
    sufixo_final = f"{rotulo}{uuid.uuid4().hex[:10]}"
    tenant_id = uuid.uuid4()

    await aplicar_tenant_teste(sessao, tenant_id)

    await sessao.execute(
        text(
            "INSERT INTO tenants (id, slug, razao_social, nome_exibicao, status) "
            "VALUES (:id, :slug, :razao, :nome, :status)"
        ),
        {
            "id": tenant_id,
            "slug": f"f10-a3-{sufixo_final}",
            "razao": "Tenant de teste F10/A3",
            "nome": "Tenant F10 A3",
            "status": status_tenant,
        },
    )

    empresa_id = uuid.uuid4()
    cnpj = f"{secrets.randbelow(10**14):014d}"
    await sessao.execute(
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
            "razao": "Empresa de Teste F10 A3 Ltda",
            "fantasia": "Empresa Teste F10 A3",
        },
    )

    unidade_id = uuid.uuid4()
    await sessao.execute(
        text(
            "INSERT INTO unidades "
            "(id, tenant_id, empresa_id, codigo, nome, tipo, uf, codigo_ibge_municipio, "
            " fuso_horario, geocerca_obrigatoria) "
            "VALUES (:id, :tenant_id, :empresa_id, 'SEDE', 'Sede de Teste', 'sede', "
            "        'SP', '3550308', 'America/Sao_Paulo', FALSE)"
        ),
        {"id": unidade_id, "tenant_id": tenant_id, "empresa_id": empresa_id},
    )

    async def _colaborador_com_usuario(
        rotulo_pessoa: str,
    ) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
        colaborador_id = uuid.uuid4()
        cpf = f"{secrets.randbelow(10**11):011d}"
        await sessao.execute(
            text(
                "INSERT INTO colaboradores "
                "(id, tenant_id, empresa_id, matricula, cpf, nome_completo, status) "
                "VALUES (:id, :tenant_id, :empresa_id, :matricula, :cpf, :nome, 'ativo')"
            ),
            {
                "id": colaborador_id,
                "tenant_id": tenant_id,
                "empresa_id": empresa_id,
                "matricula": f"MAT-{rotulo_pessoa}-{sufixo_final}",
                "cpf": cpf,
                "nome": f"Colaborador {rotulo_pessoa} de Teste F10 A3",
            },
        )
        vinculo_id = uuid.uuid4()
        await sessao.execute(
            text(
                "INSERT INTO vinculos "
                "(id, tenant_id, colaborador_id, empresa_id, unidade_id, matricula_esocial, "
                " tipo_vinculo, data_inicio, apura_ponto, status) "
                "VALUES (:id, :tenant_id, :colaborador_id, :empresa_id, :unidade_id, :esocial, "
                "        'empregado', :data_inicio, TRUE, 'ativo')"
            ),
            {
                "id": vinculo_id,
                "tenant_id": tenant_id,
                "colaborador_id": colaborador_id,
                "empresa_id": empresa_id,
                "unidade_id": unidade_id,
                "esocial": f"ESOC-{rotulo_pessoa}-{sufixo_final}",
                "data_inicio": dt.date(2020, 1, 1),
            },
        )
        usuario_id = uuid.uuid4()
        await sessao.execute(
            text(
                "INSERT INTO usuarios "
                "(id, tenant_id, colaborador_id, email, nome_completo, tipo, status) "
                "VALUES (:id, :tenant_id, :colaborador_id, :email, :nome, 'humano', 'ativo')"
            ),
            {
                "id": usuario_id,
                "tenant_id": tenant_id,
                "colaborador_id": colaborador_id,
                "email": f"{rotulo_pessoa}.{sufixo_final}@teste.f10a3.invalid",
                "nome": f"Usuario {rotulo_pessoa} de Teste F10 A3",
            },
        )
        return colaborador_id, vinculo_id, usuario_id

    colaborador_id, vinculo_id, usuario_id = await _colaborador_com_usuario("solicitante")
    (
        aprovador_colaborador_id,
        _aprovador_vinculo_id,
        aprovador_usuario_id,
    ) = await _colaborador_com_usuario("aprovador")

    tipo_solicitacao_id = uuid.uuid4()
    await sessao.execute(
        text(
            "INSERT INTO tipos_solicitacao "
            "(id, tenant_id, codigo, nome, categoria, etapas, ativo) "
            "VALUES (:id, :tenant_id, :codigo, 'Ajuste de teste', 'ajuste_ponto', "
            "        :etapas, TRUE)"
        ).bindparams(),
        {
            "id": tipo_solicitacao_id,
            "tenant_id": tenant_id,
            "codigo": f"AJT-{sufixo_final}",
            "etapas": '[{"papel": "gestor"}]',
        },
    )

    solicitacao_id = uuid.uuid4()
    agora = dt.datetime.now(tz=dt.UTC)
    await sessao.execute(
        text(
            "INSERT INTO solicitacoes "
            "(id, tenant_id, tipo_solicitacao_id, colaborador_id, vinculo_id, "
            " solicitante_usuario_id, protocolo, data_referencia, descricao, status, "
            " etapa_atual, prazo_em) "
            "VALUES (:id, :tenant_id, :tipo_solicitacao_id, :colaborador_id, :vinculo_id, "
            "        :solicitante_usuario_id, :protocolo, :data_referencia, :descricao, "
            "        'pendente', 1, :prazo_em)"
        ),
        {
            "id": solicitacao_id,
            "tenant_id": tenant_id,
            "tipo_solicitacao_id": tipo_solicitacao_id,
            "colaborador_id": colaborador_id,
            "vinculo_id": vinculo_id,
            "solicitante_usuario_id": usuario_id,
            "protocolo": f"2026-{secrets.randbelow(999999):06d}",
            "data_referencia": (agora - dt.timedelta(days=1)).date(),
            "descricao": "Esqueci de registrar a marcação de saída.",
            "prazo_em": agora - dt.timedelta(hours=1),
        },
    )

    aprovacao_id = uuid.uuid4()
    await sessao.execute(
        text(
            "INSERT INTO aprovacoes "
            "(id, tenant_id, solicitacao_id, etapa, papel, aprovador_usuario_id, decisao, "
            " prazo_em) "
            "VALUES (:id, :tenant_id, :solicitacao_id, 1, 'gestor', :aprovador_usuario_id, "
            "        'pendente', :prazo_em)"
        ),
        {
            "id": aprovacao_id,
            "tenant_id": tenant_id,
            "solicitacao_id": solicitacao_id,
            "aprovador_usuario_id": aprovador_usuario_id,
            "prazo_em": agora - dt.timedelta(hours=1),
        },
    )

    return ContextoNotificacao(
        tenant_id=tenant_id,
        tenant_slug=f"f10-a3-{sufixo_final}",
        empresa_id=empresa_id,
        unidade_id=unidade_id,
        colaborador_id=colaborador_id,
        usuario_id=usuario_id,
        vinculo_id=vinculo_id,
        aprovador_colaborador_id=aprovador_colaborador_id,
        aprovador_usuario_id=aprovador_usuario_id,
        tipo_solicitacao_id=tipo_solicitacao_id,
        solicitacao_id=solicitacao_id,
        aprovacao_id=aprovacao_id,
    )


@pytest_asyncio.fixture
async def contexto_notificacao(sessao_notificacao: AsyncSession) -> ContextoNotificacao:
    """Semeia a massa mínima (ver `semear_tenant_minimo`) e comita, deixando
    `app.tenant_id` publicado para o corpo do teste."""
    contexto = await semear_tenant_minimo(sessao_notificacao)
    await sessao_notificacao.commit()
    await aplicar_tenant_teste(sessao_notificacao, contexto.tenant_id)
    return contexto


@pytest_asyncio.fixture
async def ambiente_worker_notificacao(
    url_login_sessao_notificacao: URL, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[None]:
    """Aponta `app.core.config.Configuracao`/`worker.config.Configuracao`
    (`DATABASE_URL`) para o mesmo banco de teste da fase, autenticado como a
    MESMA role de LOGIN -- o worker também passa pelo RLS, nunca por
    superusuário (ADR-001). Mesmo padrão de
    `tests/f4/banco_horas/test_vencimento.py` (F4/A2), estendido para
    também resetar `app.db.sessao` (usada por
    `worker.notificacoes_verificacao`/`worker.tarefas.notificacoes` via
    import tardio, ver docstring dos dois módulos): sem isto, a engine
    cacheada em `app.db.sessao` (módulo de `apps/api`, meta compartilhada
    entre TODOS os testes do processo) fica presa ao event loop do PRIMEIRO
    teste que a criou -- `pytest-asyncio` abre um loop novo por teste
    (`asyncio_default_fixture_loop_scope = "function"`), e reusar uma
    engine assíncrona sob um loop diferente derruba a conexão em vez de
    reconectar (mesmo achado que `app/db/sessao.py` já documenta na própria
    docstring, para o `TestClient` síncrono da Fase 0).

    `monkeypatch.setenv` (nunca `os.environ[...] =` direto, achado do
    orquestrador no fechamento da F13): reverte `DATABASE_URL`
    automaticamente no teardown, evitando vazar para qualquer teste que rode
    depois no mesmo processo -- mesma correção já aplicada em
    `tests/f13/sso/oidc/conftest.py`/`tests/f4/dominio/
    test_apurar_dia_worker.py`."""
    monkeypatch.setenv(
        "DATABASE_URL", url_login_sessao_notificacao.render_as_string(hide_password=False)
    )
    from worker.config import obter_configuracao as obter_configuracao_worker

    from app.core.config import obter_configuracao as obter_configuracao_api
    from app.db.sessao import encerrar_engine

    obter_configuracao_api.cache_clear()
    obter_configuracao_worker.cache_clear()
    await encerrar_engine()
    yield
    await encerrar_engine()
