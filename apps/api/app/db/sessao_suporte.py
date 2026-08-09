"""Sessao de banco do SUPORTE da SEEG -- a UNICA do sistema com `BYPASSRLS`.

Escopo desta sessao: EXCLUSIVAMENTE `GET /v1/tenants` (`listarTenants`) e
`POST /v1/tenants` (`criarTenant`), em `app/routers/tenants.py`. Nenhuma outra
rota, worker, script ou dependencia deve importar `SessaoDbSuporte`.

**Por que um modulo separado de `app/db/sessao.py`.** `SessaoDb` (a sessao de
toda requisicao normal) conecta como `ponto_app_runtime`, role SEM
`BYPASSRLS`, e publica `app.tenant_id` via `SET LOCAL` antes de devolver a
sessao -- e isso, e so isso, que faz o Row Level Security valer para o sistema
inteiro (ADR-001). Aquela sessao NAO e tocada por este modulo: continua
exatamente como estava, com a mesma engine, a mesma role e o mesmo
comportamento. Este arquivo abre uma engine PROPRIA, com uma credencial
PROPRIA (`ponto_app_suporte`, criada por `migrations/versions/
0005_role_suporte_bypassrls.py`), usada so pelas duas rotas cross-tenant.

**O que a credencial de suporte pode fazer.** `BYPASSRLS` sim -- mas os
privilegios de TABELA dela sao apenas `SELECT, INSERT` em `tenants` e em
`auditoria` (ver a migration: a role NAO e membro de `ponto_app`, entao nao
herda nada do resto do schema). Uma consulta a `colaboradores`,
`marcacoes` ou `biometria_templates` com esta sessao responde
`permission denied`, mesmo com o RLS contornado. O bypass e real; o alcance
dele nao e.

**`app.tenant_id` nao e publicado aqui, de proposito.** Com `BYPASSRLS` o
valor seria ignorado pelas policies; publica-lo daria a falsa impressao de
que esta sessao esta escopada a um tenant. Ela nao esta -- e a auditoria
obrigatoria das duas rotas (`app/identidade/tenancy/servico_suporte.py`) e o
que registra, por escrito e dentro da cadeia de hash, que a operacao foi
cross-tenant.

**Falha fechada na configuracao.** Antes de servir a primeira sessao o modulo
confere, contra o proprio banco, que `current_user` e mesmo a role de suporte
e que ela tem `rolbypassrls`. Se a URL de suporte estiver apontando por engano
para a role normal (variavel de ambiente esquecida, por exemplo), a rota
responde `500 PONTO-INT-001` com o motivo no log -- nunca serve silenciosamente
uma listagem de um unico tenant como se fosse "todos", e nunca usa a conexao
comum para uma operacao que foi desenhada para o bypass.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import Configuracao, obter_configuracao
from app.core.erros import ErroDeAplicacao
from app.core.log import obter_logger

logger = obter_logger("db.suporte")

#: Nome da role criada por `0005_role_suporte_bypassrls`. Constante literal --
#: nunca interpolada a partir de entrada externa.
ROLE_SUPORTE = "ponto_app_suporte"

#: Mesmo fallback publico e explicito da migration (`_SENHA_PADRAO_DEV`): usado
#: so quando `POSTGRES_SUPORTE_PASSWORD` nao esta definida, para o ambiente de
#: desenvolvimento/teste subir sem `.env`. Nunca vale como segredo.
SENHA_PADRAO_DEV = "ponto-suporte-dev-nao-use-em-producao"

#: Pool pequeno de proposito: sao duas rotas administrativas, de uso raro. Uma
#: credencial com BYPASSRLS nao deve manter dezenas de conexoes ociosas abertas.
_TAMANHO_POOL = 2

_engine: AsyncEngine | None = None
_engine_loop: asyncio.AbstractEventLoop | None = None
_fabrica: async_sessionmaker[AsyncSession] | None = None
_credencial_conferida = False


def url_suporte(config: Configuracao | None = None) -> str:
    """URL de conexao da role de suporte.

    `DATABASE_URL_SUPORTE` tem precedencia (deploy pode querer outro host,
    outro pool ou ate outra replica). Sem ela, a URL e derivada de
    `DATABASE_URL` trocando SOMENTE usuario e senha -- assim um ambiente que ja
    aponta para o banco certo nao precisa repetir host/porta/base, e a unica
    variavel nova obrigatoria em producao e `POSTGRES_SUPORTE_PASSWORD`.
    """
    config = config or obter_configuracao()
    if config.database_url_suporte:
        return config.database_url_suporte
    senha = config.postgres_suporte_password.get_secret_value() or SENHA_PADRAO_DEV
    url = make_url(config.database_url).set(username=ROLE_SUPORTE, password=senha)
    return url.render_as_string(hide_password=False)


def _engine_presa_a_outro_loop() -> bool:
    """Mesmo cuidado de `app/db/sessao.py`: uma `AsyncEngine` fica presa ao
    event loop em que nasceu, e o `TestClient` sincrono pode trocar de loop
    entre chamadas."""
    if _engine is None or _engine_loop is None:
        return False
    try:
        return asyncio.get_running_loop() is not _engine_loop
    except RuntimeError:
        return False


def obter_engine_suporte(config: Configuracao | None = None) -> AsyncEngine:
    """Engine da role de suporte, criada no primeiro uso (nunca no import)."""
    global _engine, _engine_loop, _fabrica, _credencial_conferida
    if _engine is not None and _engine_presa_a_outro_loop():
        logger.warning("engine de suporte presa a event loop encerrado; recriando")
        _engine = None
        _fabrica = None
        _engine_loop = None
        _credencial_conferida = False
    if _engine is None:
        config = config or obter_configuracao()
        _engine = create_async_engine(
            url_suporte(config),
            echo=config.database_echo,
            pool_pre_ping=True,
            pool_size=_TAMANHO_POOL,
            max_overflow=0,
            pool_timeout=config.database_pool_timeout_s,
            connect_args={
                # `application_name` distinto do resto: uma conexao com
                # BYPASSRLS precisa ser identificavel de imediato em
                # `pg_stat_activity` e nos logs do Postgres.
                "server_settings": {"application_name": f"{config.otel_service_name}-suporte"}
            },
        )
        try:
            _engine_loop = asyncio.get_running_loop()
        except RuntimeError:
            _engine_loop = None
        _credencial_conferida = False
        logger.info("engine de suporte criada", extra={"role": ROLE_SUPORTE})
    return _engine


def fabrica_de_sessoes_suporte(
    config: Configuracao | None = None,
) -> async_sessionmaker[AsyncSession]:
    global _fabrica
    engine = obter_engine_suporte(config)
    if _fabrica is None:
        _fabrica = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    return _fabrica


async def encerrar_engine_suporte() -> None:
    """Fecha o pool de suporte. Chamado no encerramento da aplicacao."""
    global _engine, _engine_loop, _fabrica, _credencial_conferida
    if _engine is not None:
        await _engine.dispose()
        logger.info("engine de suporte encerrada")
    _engine = None
    _engine_loop = None
    _fabrica = None
    _credencial_conferida = False


async def _conferir_credencial(sessao: AsyncSession) -> None:
    """Falha fechada: a sessao so serve se for MESMO a role de suporte com
    `BYPASSRLS`. Conferido uma vez por engine (a resposta so muda se a role
    for alterada no cluster, o que exige uma migration/DBA)."""
    global _credencial_conferida
    if _credencial_conferida:
        return
    linha = (
        await sessao.execute(
            text(
                "SELECT current_user AS usuario, "
                "COALESCE((SELECT rolbypassrls FROM pg_roles WHERE rolname = current_user), FALSE) "
                "AS bypassrls"
            )
        )
    ).one()
    if linha.usuario != ROLE_SUPORTE or not linha.bypassrls:
        raise ErroDeAplicacao(
            "PONTO-INT-001",
            contexto_log={
                "motivo": "sessao de suporte nao esta conectada como a role de bypass",
                "usuario_conectado": linha.usuario,
                "bypassrls": bool(linha.bypassrls),
                "role_esperada": ROLE_SUPORTE,
            },
        )
    _credencial_conferida = True


async def obter_sessao_suporte() -> AsyncIterator[AsyncSession]:
    """Dependencia FastAPI das DUAS rotas cross-tenant do suporte da SEEG.

    Commit no caminho feliz, rollback em qualquer excecao -- mesma disciplina
    de `app/db/sessao.py:obter_sessao`. Nao publica `app.tenant_id` (ver
    docstring do modulo) e nao exige tenant resolvido: a operacao e, por
    definicao, de fora de qualquer tenant.
    """
    fabrica = fabrica_de_sessoes_suporte()
    async with fabrica() as sessao:
        try:
            await _conferir_credencial(sessao)
            yield sessao
            await sessao.commit()
        except Exception:
            await sessao.rollback()
            raise


#: Anotacao para os DOIS handlers de suporte: `sessao: SessaoDbSuporte`.
SessaoDbSuporte = Annotated[AsyncSession, Depends(obter_sessao_suporte)]
