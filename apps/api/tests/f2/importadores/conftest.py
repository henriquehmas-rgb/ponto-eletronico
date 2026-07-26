"""Fixtures locais dos testes de `app/importadores` e do worker
`importar_colaboradores` (T10, agente A3).

Reusa `contexto_organizacional` e `sessao_f2` de `apps/api/tests/f2/conftest.py`
(A1, T1) para tenant/empresa/unidade. O que este arquivo acrescenta e proprio
de A3: aponta a `Configuracao` do WORKER (`apps/worker`, pacote separado) para
o mesmo banco de teste, e resolve o Redis de teste para o job de verdade poder
ser enfileirado e, quando o teste quiser, consumido diretamente como funcao.

Variavel de ambiente lida (alem de `PONTO_TEST_DATABASE_URL`, da fixture da
fase): `PONTO_TEST_REDIS_URL` (default local -- nunca um ambiente real).
"""

from __future__ import annotations

import os

import pytest
import pytest_asyncio
from sqlalchemy.engine import URL

_URL_REDIS_PADRAO_LOCAL = "redis://localhost:6379/0"


@pytest.fixture(scope="session")
def redis_teste_url() -> str:
    return os.environ.get("PONTO_TEST_REDIS_URL", _URL_REDIS_PADRAO_LOCAL)


@pytest.fixture(scope="session")
def _ambiente_worker(url_login_sessao: URL, redis_teste_url: str) -> URL:
    """Aponta `worker.config.Configuracao` (`DATABASE_URL`, `REDIS_URL`) para
    o mesmo banco/redis de teste da fase, autenticada como a mesma role de
    LOGIN da fixture de A1 -- o worker tambem passa pelo RLS, nunca por
    superusuario (ADR-001)."""
    os.environ["DATABASE_URL"] = url_login_sessao.render_as_string(hide_password=False)
    os.environ["REDIS_URL"] = redis_teste_url

    from worker.config import obter_configuracao

    obter_configuracao.cache_clear()
    return url_login_sessao


@pytest_asyncio.fixture
async def ambiente_worker(_ambiente_worker: URL) -> URL:
    """Versao por-teste: garante que o ambiente do worker ja foi aplicado
    antes do teste rodar.

    Descarta a engine assincrona cacheada em modulo por
    `worker/tarefas/importacoes.py` a cada teste (`reiniciar_engine_para_testes`).
    O cache em modulo e correto em producao (o processo ARQ real vive num
    unico event loop a vida inteira), mas `pytest-asyncio` cria um loop NOVO
    por teste (`asyncio_default_fixture_loop_scope = "function"`); sem este
    reset, o segundo teste que chama `importar_colaboradores` reusa uma
    engine presa ao loop JA FECHADO do teste anterior e falha com
    `RuntimeError: Event loop is closed` (documentado na propria docstring
    de `reiniciar_engine_para_testes`)."""
    from worker.tarefas.importacoes import reiniciar_engine_para_testes

    await reiniciar_engine_para_testes()
    return _ambiente_worker
