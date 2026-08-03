"""Fixture do subarvore `importadores/afd_terceiro` no lado worker da fase
F13 (A8, T19 -- ownership exclusivo, `apps/worker/tests/f13/**` nao tem
dono nomeado no PCF; criado por A8 como extensao natural do proprio
ownership, mesma decisao documentada em `apps/api/app/integracoes/
importadores/__init__.py`).

Self-contained (mesmo banco de teste exclusivo `PONTO_TEST_DATABASE_URL`
que `apps/api/tests/f13/conftest.py` usa -- os dois apontam para o MESMO
`ponto_f13_a8`, instrucao operacional desta sessao): abre a propria engine
(o worker nao importa `apps/api/app/db/sessao.py`, imagens Docker separadas),
semeia tenant/empresa/REP-P minimos, e sobe o objeto no MinIO real via
`app.comum.armazenamento.salvar_objeto` (mesmo cliente que `worker/tarefas/
integracoes.py::importar_arquivo_generico` usa em producao -- nunca um
segundo cliente MinIO)."""

from __future__ import annotations

import datetime as dt
import os
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

_URL_PADRAO_LOCAL = "postgresql+asyncpg://ponto:ponto@localhost:5432/ponto_f13_a8"


def _url_banco_teste() -> str:
    return os.environ.get("PONTO_TEST_DATABASE_URL", _URL_PADRAO_LOCAL)


@pytest_asyncio.fixture
async def engine_worker_f13(request: object) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(_url_banco_teste(), pool_pre_ping=True)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def sessao_worker_f13(engine_worker_f13: AsyncEngine) -> AsyncIterator[AsyncSession]:
    fabrica = async_sessionmaker(engine_worker_f13, expire_on_commit=False, autoflush=False)
    async with fabrica() as sessao:
        yield sessao
        await sessao.rollback()


async def _aplicar_tenant(sessao: AsyncSession, tenant_id: uuid.UUID) -> None:
    await sessao.execute(
        text("SELECT set_config('app.tenant_id', :tenant, true)"), {"tenant": str(tenant_id)}
    )


@dataclass(frozen=True, slots=True)
class ContextoWorkerF13:
    tenant_id: uuid.UUID
    empresa_id: uuid.UUID
    rep_p_id: uuid.UUID


def _digitos(quantidade: int) -> str:
    return str(uuid.uuid4().int)[:quantidade].zfill(quantidade)


@pytest_asyncio.fixture
async def contexto_worker_f13(sessao_worker_f13: AsyncSession) -> ContextoWorkerF13:
    """Semeia tenant + empresa + REP-P ativo minimos, direto por SQL (mesmo
    padrao que os conftests de F12/F13 ja estabelecem para dado de cadastro
    que nao e o foco do teste)."""
    tenant_id = uuid.uuid4()
    slug = f"f13a8w-{uuid.uuid4().hex[:10]}"
    await _aplicar_tenant(sessao_worker_f13, tenant_id)
    await sessao_worker_f13.execute(
        text(
            "INSERT INTO tenants (id, slug, razao_social, nome_exibicao, status) "
            "VALUES (:id, :slug, 'Tenant worker F13/A8', 'Tenant worker F13/A8', 'ativo')"
        ),
        {"id": tenant_id, "slug": slug},
    )
    empresa_id = uuid.uuid4()
    empresa_cnpj = _digitos(14)
    await sessao_worker_f13.execute(
        text(
            "INSERT INTO empresas "
            "(id, tenant_id, tipo, cnpj, razao_social, nome_fantasia, uf, codigo_ibge_municipio) "
            "VALUES (:id, :tenant_id, 'matriz', :cnpj, 'Empresa worker F13/A8', 'Empresa', 'GO', "
            "        '5208707')"
        ),
        {"id": empresa_id, "tenant_id": tenant_id, "cnpj": empresa_cnpj},
    )
    rep_p_id = uuid.uuid4()
    numero_inpi = str(uuid.uuid4().int)[:15].zfill(15)
    await sessao_worker_f13.execute(
        text(
            "INSERT INTO rep_ps "
            "(id, tenant_id, empresa_id, identificador, tipo, numero_inpi, cnpj_desenvolvedor, "
            " razao_social_desenvolvedor, cnpj_empregador, razao_social_empregador, "
            " versao_programa, data_inicio_operacao, status) "
            "VALUES (:id, :tenant_id, :empresa_id, :identificador, 'rep_p', :numero_inpi, "
            "        '60258502000149', 'SEEG Servicos de Tecnologia da Informacao LTDA', "
            "        :cnpj_emp, 'Empresa worker F13/A8', '1.0.0-teste', :inicio, 'ativo')"
        ),
        {
            "id": rep_p_id,
            "tenant_id": tenant_id,
            "empresa_id": empresa_id,
            "identificador": f"REP-{uuid.uuid4().hex[:10]}",
            "numero_inpi": numero_inpi,
            "cnpj_emp": empresa_cnpj,
            "inicio": dt.date.today(),
        },
    )
    await sessao_worker_f13.commit()
    await _aplicar_tenant(sessao_worker_f13, tenant_id)
    return ContextoWorkerF13(tenant_id=tenant_id, empresa_id=empresa_id, rep_p_id=rep_p_id)
