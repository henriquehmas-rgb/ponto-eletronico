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
  e visivel -- falha fechada, nao aberta.
* **F1.** `obter_sessao` agora recusa abrir sessao de banco quando nenhum
  tenant foi resolvido (`PONTO-VAL-011`): uma rota que declara `SessaoDb` sem
  que `TenantMiddleware` tenha publicado um tenant no contexto e um bug de
  rota, nao uma requisicao legitima sem tenant. Isto e o que faz "requisicao
  sem tenant resolvido nao abre sessao de banco" (PCF da fase, T2) valer para
  toda rota que toca o banco, nao so para as que a F1 escreveu.
* **F1 -- engine presa ao event loop.** `TestClient` sincrono (usado por
  `tests/test_andaime.py`) pode abrir um event loop novo a cada chamada
  quando nao e usado como *context manager*. Uma `AsyncEngine`/pool do asyncpg
  fica presa ao loop em que nasceu; reusa-la sob um loop diferente produz
  `RuntimeError: Event loop is closed` em vez de reconectar -- descoberto ao
  ligar de verdade a resolucao de tenant (`TenantMiddleware`) contra o banco
  nesta fase, que e a primeira a exercitar I/O assincrono real por tras do
  `TestClient`. `obter_engine` agora descarta e recria a engine quando o loop
  corrente difere do loop em que ela foi criada.
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
from app.core.erros import CODIGO_CABECALHO_AUSENTE, ErroDeAplicacao
from app.core.log import obter_logger

logger = obter_logger("db")

_engine: AsyncEngine | None = None
_engine_loop: asyncio.AbstractEventLoop | None = None
_fabrica: async_sessionmaker[AsyncSession] | None = None


def _engine_presa_a_outro_loop() -> bool:
    """Verdadeiro quando ha engine, mas o event loop corrente ja nao e o dela."""
    if _engine is None or _engine_loop is None:
        return False
    try:
        return asyncio.get_running_loop() is not _engine_loop
    except RuntimeError:
        # Sem loop corrente (chamada fora de contexto assincrono): nao ha
        # como comparar: trata como "mesma engine", quem chamou que decida.
        return False


def obter_engine(config: Configuracao | None = None) -> AsyncEngine:
    """Engine assincrona do processo, criada no primeiro uso (ou recriada se
    o event loop corrente mudou -- ver docstring do modulo)."""
    global _engine, _engine_loop, _fabrica
    if _engine is not None and _engine_presa_a_outro_loop():
        # O loop antigo ja fechou: nao ha como `dispose()` nele. Solta a
        # referencia para coleta e recria contra o loop corrente.
        logger.warning("engine presa a event loop encerrado; recriando")
        _engine = None
        _fabrica = None
        _engine_loop = None
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
        try:
            _engine_loop = asyncio.get_running_loop()
        except RuntimeError:
            _engine_loop = None
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
    global _engine, _engine_loop, _fabrica
    if _engine is not None:
        await _engine.dispose()
        logger.info("engine encerrada")
    _engine = None
    _engine_loop = None
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

    Recusa abrir sessao quando nenhum tenant foi resolvido pelo
    `TenantMiddleware`: falha fechada, nao aberta. Isto evita que uma consulta
    rode com `app.tenant_id` vazio, que sob RLS devolveria silenciosamente zero
    linhas em vez de erro -- comportamento seguro, mas dificil de depurar
    quando o esperado era 400, nao uma lista vazia.
    """
    tenant = tenant_atual()
    if not tenant:
        raise ErroDeAplicacao(
            CODIGO_CABECALHO_AUSENTE,
            detalhe="Nenhum tenant resolvido para a requisicao (cabecalho X-Tenant "
            "ausente e o host nao identifica um tenant).",
            contexto_log={"dependencia": "obter_sessao"},
        )
    fabrica = fabrica_de_sessoes()
    async with fabrica() as sessao:
        try:
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
