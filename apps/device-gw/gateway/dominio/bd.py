"""Engine assincrona e sessao do `device-gw`, com o mesmo gatilho de RLS que
`apps/api/app/db/sessao.py` (ADR-001).

Por que este modulo existe em vez de importar `apps/api`
---------------------------------------------------------

`device-gw` e um processo separado, com o proprio `pyproject.toml` e a propria
imagem de container (ver docstring de `gateway/main.py`): ele nao pode
importar `apps.api.app.*`. A duplicacao do padrao "engine preguicosa + `SET
LOCAL app.tenant_id`" e deliberada -- mesma decisao ja tomada para
`gateway/log.py` versus `app/core/log.py`.

Duas formas de abrir sessao
---------------------------

* `sessao_com_tenant(tenant_id)`: o caminho comum, usado depois que o terminal
  foi resolvido (T2) -- publica `app.tenant_id` e todo acesso subsequente
  respeita a Row Level Security normalmente.
* `conexao_sem_tenant()`: usada **apenas** para chamar `fn_resolve_terminal`
  (`SECURITY DEFINER`), a unica consulta que roda antes de existir tenant
  (RFC-010). Nenhuma outra tabela e acessada por aqui.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from gateway.config import Configuracao, obter_configuracao

_engine: AsyncEngine | None = None
_engine_loop: asyncio.AbstractEventLoop | None = None
_fabrica: async_sessionmaker[AsyncSession] | None = None


def _engine_presa_a_outro_loop() -> bool:
    """Verdadeiro quando ha engine, mas o event loop corrente ja nao e o
    dela -- mesmo problema (e mesma solucao) documentado em
    `apps/api/app/db/sessao.py`: um teste assincrono novo por funcao (ou um
    `TestClient` sincrono) pode rodar sob um loop diferente do que criou o
    pool, e reusar o pool antigo produz `RuntimeError: Event loop is
    closed` em vez de reconectar."""
    if _engine is None or _engine_loop is None:
        return False
    try:
        return asyncio.get_running_loop() is not _engine_loop
    except RuntimeError:
        return False


def obter_engine(config: Configuracao | None = None) -> AsyncEngine:
    """Engine assincrona do processo, criada no primeiro uso (ou recriada se
    o event loop corrente mudou)."""
    global _engine, _engine_loop, _fabrica
    if _engine is not None and _engine_presa_a_outro_loop():
        _engine = None
        _fabrica = None
        _engine_loop = None
    if _engine is None:
        config = config or obter_configuracao()
        _engine = create_async_engine(
            config.database_url,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=5,
            connect_args={"server_settings": {"application_name": "ponto-device-gw"}},
        )
        try:
            _engine_loop = asyncio.get_running_loop()
        except RuntimeError:
            _engine_loop = None
    return _engine


def fabrica_de_sessoes(config: Configuracao | None = None) -> async_sessionmaker[AsyncSession]:
    global _fabrica
    if _fabrica is None:
        _fabrica = async_sessionmaker(
            bind=obter_engine(config), expire_on_commit=False, autoflush=False
        )
    return _fabrica


async def encerrar_engine() -> None:
    """Fecha o pool. Uso exclusivo de teste (entre modulos com fixture propria).
    Nao tenta fechar graciosamente uma engine presa a um loop ja encerrado
    (mesmo caso de `_engine_presa_a_outro_loop`) -- so descarta a referencia."""
    global _engine, _fabrica, _engine_loop
    if _engine is not None and not _engine_presa_a_outro_loop():
        await _engine.dispose()
    _engine = None
    _fabrica = None
    _engine_loop = None


async def aplicar_tenant(sessao: AsyncSession, tenant_id: str) -> None:
    """`SET LOCAL app.tenant_id` -- gatilho do RLS (ADR-001). `SET LOCAL` limita
    o efeito a transacao corrente: a conexao volta ao pool sem carregar o
    tenant do terminal anterior."""
    await sessao.execute(
        text("SELECT set_config('app.tenant_id', :tenant, true)"), {"tenant": tenant_id}
    )


@contextlib.asynccontextmanager
async def sessao_com_tenant(
    tenant_id: str, *, config: Configuracao | None = None
) -> AsyncIterator[AsyncSession]:
    """Sessao em transacao, com `app.tenant_id` publicado. Commit no caminho
    feliz, rollback em qualquer excecao -- mesma semantica de `obter_sessao`
    da API (`apps/api/app/db/sessao.py`)."""
    fabrica = fabrica_de_sessoes(config)
    async with fabrica() as sessao:
        try:
            await aplicar_tenant(sessao, tenant_id)
            yield sessao
            await sessao.commit()
        except Exception:
            await sessao.rollback()
            raise


@contextlib.asynccontextmanager
async def conexao_sem_tenant(
    *, config: Configuracao | None = None
) -> AsyncIterator[AsyncConnection]:
    """Conexao **sem** `app.tenant_id`. Uso exclusivo de `fn_resolve_terminal`
    (`SECURITY DEFINER`, RFC-010) -- nenhuma outra tabela e legivel por aqui,
    porque nenhuma outra tem policy que dispense o tenant."""
    engine = obter_engine(config)
    async with engine.connect() as conexao:
        yield conexao
