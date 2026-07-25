"""Engine assincrona, fabrica de sessoes e dependencia de sessao.

Decisoes de andaime que as fases seguintes herdam:

* **Engine preguicosa.** Criada no primeiro uso, nao no import. E o que permite
  `python -c "from app.main import app"` rodar em maquina sem PostgreSQL --
  usado no CI e na conferencia de rotas.
* **`pool_pre_ping`.** Conexao morta por restart do banco ou por timeout do
  Traefik e descartada antes de virar erro 500 do usuario.
* **`expire_on_commit=False`.** Sem isso, todo objeto vira consulta nova depois
  do commit, o que na apuracao de 10.000 colaboradores custaria caro.
* **`SET LOCAL app.tenant_id`.** Cada transacao publica o tenant corrente na
  sessao do PostgreSQL. E o gatilho do Row Level Security descrito no glossario
  (secao 1.1): *sem* esse `SET`, `current_setting` devolve NULL e nenhuma linha
  e visivel -- falha fechada, nao aberta. A F1 endurece isto (role dedicada,
  verificacao de divergencia com o token); o andaime ja garante que a semente
  esteja no lugar certo, dentro da transacao e com `LOCAL`.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import Configuracao, obter_configuracao
from app.core.contexto import tenant_atual
from app.core.log import obter_logger

logger = obter_logger("db")

_engine: AsyncEngine | None = None
_fabrica: async_sessionmaker[AsyncSession] | None = None


def obter_engine(config: Configuracao | None = None) -> AsyncEngine:
    """Engine assincrona do processo, criada no primeiro uso."""
    global _engine
    if _engine is None:
        config = config or obter_configuracao()
        _engine = create_async_engine(
            config.database_url,
            echo=config.database_echo,
            pool_pre_ping=True,
            pool_size=config.database_pool_size,
            max_overflow=config.database_max_overflow,
            pool_timeout=config.database_pool_timeout_s,
            # `application_name` aparece em pg_stat_activity: identificar qual
            # servico segura um lock e a diferenca entre 5 min e 2 h de
            # investigacao numa madrugada de incidente.
            connect_args={"server_settings": {"application_name": config.otel_service_name}},
        )
        logger.info("engine criada", extra={"pool": config.database_pool_size})
    return _engine


def fabrica_de_sessoes(config: Configuracao | None = None) -> async_sessionmaker[AsyncSession]:
    """Fabrica de sessoes do processo."""
    global _fabrica
    if _fabrica is None:
        _fabrica = async_sessionmaker(
            bind=obter_engine(config),
            expire_on_commit=False,
            autoflush=False,
        )
    return _fabrica


async def encerrar_engine() -> None:
    """Fecha o pool. Chamado no encerramento da aplicacao."""
    global _engine, _fabrica
    if _engine is not None:
        await _engine.dispose()
        logger.info("engine encerrada")
    _engine = None
    _fabrica = None


async def aplicar_tenant(sessao: AsyncSession, tenant: str) -> None:
    """Publica o tenant na sessao do PostgreSQL para o Row Level Security.

    `SET LOCAL` limita o efeito a transacao corrente: uma conexao devolvida ao
    pool nunca leva o tenant da requisicao anterior. Parametro vinculado, nunca
    interpolacao de string -- `SET LOCAL` nao aceita bind, entao usamos
    `set_config`, que aceita.
    """
    await sessao.execute(
        text("SELECT set_config('app.tenant_id', :tenant, true)"),
        {"tenant": tenant},
    )


async def obter_sessao() -> AsyncIterator[AsyncSession]:
    """Dependencia FastAPI: uma sessao por requisicao, em transacao.

    Commit no caminho feliz, rollback em qualquer excecao. O handler nao precisa
    lembrar de nenhum dos dois.
    """
    fabrica = fabrica_de_sessoes()
    async with fabrica() as sessao:
        tenant = tenant_atual()
        try:
            if tenant:
                await aplicar_tenant(sessao, tenant)
            yield sessao
            await sessao.commit()
        except Exception:
            await sessao.rollback()
            raise


#: Anotacao pronta para os handlers: `sessao: SessaoDb`.
SessaoDb = Annotated[AsyncSession, Depends(obter_sessao)]


async def verificar_banco(timeout_s: float = 3.0) -> tuple[bool, str]:
    """`SELECT 1` com prazo. Usado por `/ready`. Nunca levanta excecao."""
    try:
        async with asyncio.timeout(timeout_s):
            engine = obter_engine()
            async with engine.connect() as conexao:
                await conexao.execute(text("SELECT 1"))
        return True, "ok"
    except TimeoutError:
        return False, f"timeout apos {timeout_s}s"
    except Exception as exc:
        return False, type(exc).__name__
