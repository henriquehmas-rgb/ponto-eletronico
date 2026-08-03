"""T4 -- `app.comum.limitador_taxa` (F13/A1).

Teste de carga simples (N+1 requisições no mesmo minuto) contra o Redis
real (`PONTO_TEST_REDIS_URL`): prova o `429` na N+1 com os cabeçalhos
corretos. Usa `rate_limit_por_minuto` pequeno (3) para não depender de
esperar um minuto de verdade -- N+1 chamadas cabem folgadamente dentro da
mesma janela fixa de 60s.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from starlette.responses import Response

import app.comum.limitador_taxa as limitador_mod
from app.comum.autenticacao_cliente import ClienteAutenticado
from app.core.erros import ErroDeAplicacao

_URL_REDIS_PADRAO_LOCAL = "redis://localhost:6379/1"


@pytest_asyncio.fixture(autouse=True)
async def _redis_de_teste(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[None]:
    """Aponta `app.comum.limitador_taxa` para `PONTO_TEST_REDIS_URL` (o
    Redis real desta sessão) via variável de ambiente + `cache_clear()` --
    nunca mutando a instância de `Configuracao` diretamente, para não
    depender da ordem relativa entre esta fixture e
    `tests.f13.conftest._engine_global_isolada_por_teste` (que também limpa
    o cache de configuração; a próxima leitura, de qualquer uma das duas,
    sempre volta a ler `REDIS_URL` do ambiente, que esta fixture já
    ajustou). Garante também um cliente Redis NOVO por teste -- cada teste
    roda num event loop novo, e um cliente `redis.asyncio` cacheado do loop
    anterior quebraria do mesmo jeito que a engine do banco quebraria.
    Fixture ASSÍNCRONA (não `asyncio.run()` num teardown síncrono): o
    encerramento do cliente precisa rodar no MESMO event loop em que ele foi
    aberto, senão o driver reclama de conexão presa a outro loop."""
    url = os.environ.get("PONTO_TEST_REDIS_URL", _URL_REDIS_PADRAO_LOCAL)
    monkeypatch.setenv("REDIS_URL", url)
    limitador_mod.obter_configuracao.cache_clear()
    await limitador_mod._para_teste["encerrar_cliente_redis"]()

    yield

    await limitador_mod._para_teste["encerrar_cliente_redis"]()
    limitador_mod.obter_configuracao.cache_clear()


def _cliente(api_client_id: uuid.UUID, limite: int) -> ClienteAutenticado:
    return ClienteAutenticado(
        tenant_id=uuid.uuid4(),
        api_client_id=api_client_id,
        ambiente="producao",
        escopos=("webhooks:ler",),
        rate_limit_por_minuto=limite,
    )


async def test_dentro_da_cota_escreve_cabecalhos_e_nao_levanta() -> None:
    cliente = _cliente(uuid.uuid4(), limite=5)
    response = Response()

    await limitador_mod._verificar_e_registrar(response, cliente)

    assert response.headers["RateLimit-Limit"] == "5"
    assert response.headers["RateLimit-Remaining"] == "4"
    assert int(response.headers["RateLimit-Reset"]) <= 60
    assert response.headers["RateLimit-Policy"] == "5;w=60"


async def test_np1_esima_requisicao_responde_429_com_cabecalhos() -> None:
    limite = 3
    cliente = _cliente(uuid.uuid4(), limite=limite)

    for _ in range(limite):
        response = Response()
        await limitador_mod._verificar_e_registrar(response, cliente)

    with pytest.raises(ErroDeAplicacao) as excinfo:
        await limitador_mod._verificar_e_registrar(Response(), cliente)

    assert excinfo.value.codigo == "PONTO-RATE-001"
    cabecalhos = excinfo.value.cabecalhos
    assert cabecalhos["RateLimit-Limit"] == str(limite)
    assert cabecalhos["RateLimit-Remaining"] == "0"
    assert cabecalhos["RateLimit-Policy"] == f"{limite};w=60"
    assert "Retry-After" in cabecalhos
    assert excinfo.value.tentar_novamente_em is not None


async def test_clientes_diferentes_tem_cotas_independentes() -> None:
    limite = 2
    cliente_a = _cliente(uuid.uuid4(), limite=limite)
    cliente_b = _cliente(uuid.uuid4(), limite=limite)

    for _ in range(limite):
        await limitador_mod._verificar_e_registrar(Response(), cliente_a)

    # `cliente_b` nunca chamou ainda: continua com a cota cheia, mesmo
    # `cliente_a` já tendo esgotado a própria.
    response_b = Response()
    await limitador_mod._verificar_e_registrar(response_b, cliente_b)
    assert response_b.headers["RateLimit-Remaining"] == str(limite - 1)


async def test_redis_indisponivel_falha_aberta(monkeypatch: pytest.MonkeyPatch) -> None:
    """Falha de infraestrutura auxiliar nunca deve bloquear tráfego
    legítimo (ver docstring do módulo)."""
    config = limitador_mod.obter_configuracao()
    monkeypatch.setattr(config, "redis_url", "redis://host-que-nao-existe-de-verdade:6399/0")

    cliente = _cliente(uuid.uuid4(), limite=1)
    response = Response()
    # Nao deve levantar, mesmo com Redis inalcancavel.
    await limitador_mod._verificar_e_registrar(response, cliente)
    assert "RateLimit-Limit" not in response.headers
