"""Fixtures de banco para `verificar_terminal_offline` (T9, F6/A1).

Reaproveita as DUAS roles ja provisionadas para a fase (ver RFC-013):
`ponto_teste_f6_a1` (membro de `ponto_app`, RLS normal -- usada aqui via
`worker.config.Configuracao.database_url`) e `ponto_teste_f6_a1_suporte`
(BYPASSRLS, so leitura -- usada via `database_url_suporte`, a enumeracao
cross-tenant que a rotina de cron precisa).
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

VARIAVEL_URL = "PONTO_TEST_DATABASE_URL"
URL_PADRAO = "postgresql+asyncpg://ponto:ponto@localhost:5432/ponto"

PAPEL_APP = "ponto_teste_f6_a1"
SENHA_APP = "teste-f6-a1-senha"
PAPEL_SUPORTE = "ponto_teste_f6_a1_suporte"
SENHA_SUPORTE = "teste-f6-a1-suporte-senha"


def url_admin() -> str:
    return os.environ.get(VARIAVEL_URL, URL_PADRAO).strip()


def _url_com_role(url: str, role: str, senha: str) -> str:
    partes = sa.engine.make_url(url)
    return partes.set(username=role, password=senha).render_as_string(hide_password=False)


@pytest.fixture(scope="session", autouse=True)
def _config_worker() -> None:
    os.environ["DATABASE_URL"] = _url_com_role(url_admin(), PAPEL_APP, SENHA_APP)
    os.environ["DATABASE_URL_SUPORTE"] = _url_com_role(url_admin(), PAPEL_SUPORTE, SENHA_SUPORTE)
    from worker.config import obter_configuracao

    obter_configuracao.cache_clear()


@dataclass(frozen=True, slots=True)
class TenantSemeado:
    id: uuid.UUID
    empresa_id: uuid.UUID
    unidade_id: uuid.UUID


def _cnpj_de(base: uuid.UUID) -> str:
    digitos = "".join(c for c in base.hex if c.isdigit()) or "0"
    return (digitos * 2)[:14].rjust(14, "0")


@pytest_asyncio.fixture
async def tenant_worker() -> AsyncIterator[TenantSemeado]:
    engine = create_async_engine(url_admin())
    tenant_id = uuid.uuid4()
    empresa_id = uuid.uuid4()
    unidade_id = uuid.uuid4()
    slug = f"f6-worker-{tenant_id.hex[:8]}"
    async with engine.begin() as conexao:
        await conexao.execute(
            text(
                "INSERT INTO tenants (id, slug, razao_social, nome_exibicao, plano, status) "
                "VALUES (:id, :slug, 'F6 Worker Teste Ltda', 'F6 Worker Teste', 'padrao', 'ativo')"
            ),
            {"id": str(tenant_id), "slug": slug},
        )
        await conexao.execute(
            text("SELECT set_config('app.tenant_id', :tenant, true)"), {"tenant": str(tenant_id)}
        )
        await conexao.execute(
            text(
                "INSERT INTO empresas (id, tenant_id, razao_social, nome_fantasia, cnpj, ativo) "
                "VALUES (:id, :tenant_id, 'Empresa F6 Worker', 'F6 Worker', :cnpj, TRUE)"
            ),
            {"id": str(empresa_id), "tenant_id": str(tenant_id), "cnpj": _cnpj_de(tenant_id)},
        )
        await conexao.execute(
            text(
                "INSERT INTO unidades (id, tenant_id, empresa_id, codigo, nome, ativo) "
                "VALUES (:id, :tenant_id, :empresa_id, 'UN01', 'Unidade F6 Worker', TRUE)"
            ),
            {"id": str(unidade_id), "tenant_id": str(tenant_id), "empresa_id": str(empresa_id)},
        )
    await engine.dispose()
    yield TenantSemeado(id=tenant_id, empresa_id=empresa_id, unidade_id=unidade_id)


async def criar_terminal_worker(
    tenant: TenantSemeado,
    *,
    ultimo_contato_em: str | None,
    modo_comunicacao: str = "push",
    intervalo_push_segundos: int = 30,
) -> uuid.UUID:
    """`ultimo_contato_em` e uma expressao SQL (ex.: `"now() - interval '1 hour'"`)
    ou `None` (nunca contatou)."""
    engine = create_async_engine(url_admin())
    terminal_id = uuid.uuid4()
    numero_serie = f"IDF-WORKER-{terminal_id.hex[:10]}"
    async with engine.begin() as conexao:
        await conexao.execute(
            text("SELECT set_config('app.tenant_id', :tenant, true)"), {"tenant": str(tenant.id)}
        )
        dispositivo_id = uuid.uuid4()
        await conexao.execute(
            text(
                "INSERT INTO dispositivos (id, tenant_id, empresa_id, unidade_id, tipo, "
                "plataforma, identificador, status) VALUES (:id, :tenant_id, :empresa_id, "
                ":unidade_id, 'terminal', 'embarcado', :identificador, 'ativo')"
            ),
            {
                "id": str(dispositivo_id),
                "tenant_id": str(tenant.id),
                "empresa_id": str(tenant.empresa_id),
                "unidade_id": str(tenant.unidade_id),
                "identificador": numero_serie,
            },
        )
        # `contato_sql` nunca vem de entrada externa: e um literal SQL fixo
        # ("NULL" ou uma expressao `now() - interval ...`) escolhido pelo
        # proprio teste, nunca por um parametro de requisicao -- por isso o
        # `noqa` abaixo, e nao um bind (`SET LOCAL`/`interval` nao aceitam
        # parametro vinculado do jeito que este teste precisa variar).
        contato_sql = ultimo_contato_em if ultimo_contato_em is not None else "NULL"
        sql_terminal = (
            "INSERT INTO terminais (id, tenant_id, dispositivo_id, empresa_id, unidade_id, "  # noqa: S608
            "fabricante, numero_serie, modo_comunicacao, intervalo_push_segundos, "
            f"ultimo_contato_em, status) VALUES (:id, :tenant_id, :dispositivo_id, "
            f":empresa_id, :unidade_id, 'control_id', :numero_serie, :modo, :intervalo, "
            f"{contato_sql}, 'ativo')"
        )
        await conexao.execute(
            text(sql_terminal),
            {
                "id": str(terminal_id),
                "tenant_id": str(tenant.id),
                "dispositivo_id": str(dispositivo_id),
                "empresa_id": str(tenant.empresa_id),
                "unidade_id": str(tenant.unidade_id),
                "numero_serie": numero_serie,
                "modo": modo_comunicacao,
                "intervalo": intervalo_push_segundos,
            },
        )
    await engine.dispose()
    return terminal_id


@pytest_asyncio.fixture(autouse=True)
async def _reset_engines_worker() -> AsyncIterator[None]:
    from worker import terminais_saude

    await terminais_saude.reiniciar_engines_para_teste()
    terminais_saude.limpar_barramento()
    yield
