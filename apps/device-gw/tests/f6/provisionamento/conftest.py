"""Fixture de banco desta tarefa (T7 do PCF da F6, agente A2).

Auto-contida e EXCLUSIVA de A2: banco `ponto_f6_a2`, nunca compartilhado com
outro agente da mesma fase (instrucao do orquestrador para esta onda -- ver
o cabecalho do proprio PCF, "nunca compartilhe banco com outro agente, mesmo
da mesma fase"). Migra o banco, cria uma role de LOGIN sem `BYPASSRLS`
(nunca a role administrativa `ponto` para os testes) e semeia um tenant, uma
empresa e um terminal minimos para exercitar `worker.tarefas.integracoes.
sincronizar_terminal`.

Variavel de ambiente lida: `PONTO_TEST_DATABASE_URL` (conexao administrativa
contra o banco `ponto_f6_a2`, ja criado e migrado antes da suite rodar -- ver
o relatorio final desta tarefa para os comandos exatos).
"""

from __future__ import annotations

import os
import secrets
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass

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

_URL_PADRAO_LOCAL = "postgresql+asyncpg://ponto:ponto@localhost:5432/ponto_f6_a2"

#: Role de LOGIN exclusiva desta suite. Membra de `ponto_app` (criada por
#: `0001_inicial`) para herdar exatamente os privilegios de tabela que a
#: aplicacao usa em producao -- nunca a role administrativa do bootstrap.
_ROLE_LOGIN = "ponto_teste_f6_a2"


def _url_superusuario() -> URL:
    bruta = os.environ.get("PONTO_TEST_DATABASE_URL", _URL_PADRAO_LOCAL)
    return make_url(bruta)


@pytest.fixture(scope="session")
def url_login_sessao() -> URL:
    """Devolve a `URL` de conexao da role de LOGIN. A migracao e a criacao
    da role acontecem fora do teste (ver secao 8 do relatorio final): o
    banco `ponto_f6_a2` ja chega migrado, esta fixture so garante a role."""
    url_super = _url_superusuario()

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

    return url_super.set(drivername="postgresql+asyncpg", username=_ROLE_LOGIN, password=senha)


@pytest_asyncio.fixture
async def engine_f6(url_login_sessao: URL) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(url_login_sessao, pool_pre_ping=True, connect_args={"timeout": 8})
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def sessao_f6(engine_f6: AsyncEngine) -> AsyncIterator[AsyncSession]:
    fabrica = async_sessionmaker(engine_f6, expire_on_commit=False, autoflush=False)
    async with fabrica() as sessao:
        yield sessao
        await sessao.rollback()


async def aplicar_tenant_teste(sessao: AsyncSession, tenant_id: uuid.UUID) -> None:
    await sessao.execute(
        text("SELECT set_config('app.tenant_id', :tenant, true)"), {"tenant": str(tenant_id)}
    )


@dataclass(frozen=True, slots=True)
class ContextoTerminal:
    tenant_id: uuid.UUID
    empresa_id: uuid.UUID
    terminal_id: uuid.UUID
    numero_serie: str
    dispositivo_id: uuid.UUID


@pytest_asyncio.fixture
async def contexto_terminal(sessao_f6: AsyncSession) -> ContextoTerminal:
    """Semeia 1 tenant, 1 empresa e 1 terminal (com o `dispositivos` que
    `terminais.dispositivo_id` exige). Cada chamada gera dados novos -- nenhum
    teste compartilha semente com outro."""
    sufixo = uuid.uuid4().hex[:12]
    tenant_id = uuid.uuid4()
    tenant_slug = f"f6a2-{sufixo}"

    await aplicar_tenant_teste(sessao_f6, tenant_id)

    await sessao_f6.execute(
        text(
            "INSERT INTO tenants (id, slug, razao_social, nome_exibicao, status) "
            "VALUES (:id, :slug, :razao, :nome, 'ativo')"
        ),
        {
            "id": tenant_id,
            "slug": tenant_slug,
            "razao": "Tenant de teste F6/A2",
            "nome": "Tenant F6 A2",
        },
    )

    empresa_id = uuid.uuid4()
    # DOM_CNPJ exige 14 digitos puros -- `sufixo` e hexadecimal (pode ter
    # a-f), entao cada nibble e reduzido a um digito decimal antes de compor.
    digitos_sufixo = "".join(str(int(c, 16) % 10) for c in sufixo[:8])
    cnpj = f"{digitos_sufixo}000159"
    await sessao_f6.execute(
        text(
            "INSERT INTO empresas "
            "(id, tenant_id, tipo, cnpj, razao_social, nome_fantasia, uf, "
            " codigo_ibge_municipio) "
            "VALUES (:id, :tenant_id, 'matriz', :cnpj, :razao, :fantasia, 'SP', '3550308')"
        ),
        {
            "id": empresa_id,
            "tenant_id": tenant_id,
            "cnpj": cnpj,
            "razao": "Empresa de Teste F6/A2 Ltda",
            "fantasia": "Empresa F6 A2",
        },
    )

    dispositivo_id = uuid.uuid4()
    await sessao_f6.execute(
        text(
            "INSERT INTO dispositivos "
            "(id, tenant_id, empresa_id, tipo, identificador, status) "
            "VALUES (:id, :tenant_id, :empresa_id, 'terminal', :identificador, 'ativo')"
        ),
        {
            "id": dispositivo_id,
            "tenant_id": tenant_id,
            "empresa_id": empresa_id,
            "identificador": f"IDF-{sufixo}",
        },
    )

    terminal_id = uuid.uuid4()
    numero_serie = f"IDF-{sufixo}"
    await sessao_f6.execute(
        text(
            "INSERT INTO terminais "
            "(id, tenant_id, dispositivo_id, empresa_id, numero_serie, modo_comunicacao, status) "
            "VALUES (:id, :tenant_id, :dispositivo_id, :empresa_id, :numero_serie, 'push', 'ativo')"
        ),
        {
            "id": terminal_id,
            "tenant_id": tenant_id,
            "dispositivo_id": dispositivo_id,
            "empresa_id": empresa_id,
            "numero_serie": numero_serie,
        },
    )

    await sessao_f6.commit()
    await aplicar_tenant_teste(sessao_f6, tenant_id)

    return ContextoTerminal(
        tenant_id=tenant_id,
        empresa_id=empresa_id,
        terminal_id=terminal_id,
        numero_serie=numero_serie,
        dispositivo_id=dispositivo_id,
    )


async def inserir_colaborador(
    sessao: AsyncSession, *, tenant_id: uuid.UUID, empresa_id: uuid.UUID, matricula: str, nome: str
) -> uuid.UUID:
    """Colaborador ATIVO minimo, suficiente para `sincronizar_terminal`
    (escopo `usuarios`) listar. CPF gerado sem validar digito verificador --
    a coluna aceita, e nao e regra desta tarefa validar CPF de novo."""
    colaborador_id = uuid.uuid4()
    cpf = str(abs(hash((matricula, str(tenant_id)))))[:11].ljust(11, "1")
    await sessao.execute(
        text(
            "INSERT INTO colaboradores "
            "(id, tenant_id, empresa_id, matricula, cpf, nome_completo, status, data_admissao) "
            "VALUES (:id, :tenant_id, :empresa_id, :matricula, :cpf, :nome, 'ativo', CURRENT_DATE)"
        ),
        {
            "id": colaborador_id,
            "tenant_id": tenant_id,
            "empresa_id": empresa_id,
            "matricula": matricula,
            "cpf": cpf,
            "nome": nome,
        },
    )
    return colaborador_id
