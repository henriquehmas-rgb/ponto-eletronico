"""Fila de comandos do modo Push, no Redis (T4 do PCF da F6).

Uma lista Redis por terminal (`numero_serie`): `enfileirar_comando` (API,
worker) empurra um envelope `{verb, endpoint, contentType, queryString,
body}`; `push_obter_comando` retira o mais antigo (FIFO) quando o terminal
pergunta "tem comando para mim?". O comando **sai da fila no momento em que e
entregue** -- nao ha fila de "pendente de confirmacao" nesta versao: se o
terminal cair entre receber o comando e devolver o resultado, o proximo ciclo
de sincronizacao (`sincronizar_terminal`, F6/A2) reenfileira o trabalho, e a
idempotencia do lado da marcacao (`dispositivo_id` + `log_externo_id`) cobre
o caso especifico de `access_logs` reentregues.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from uuid import uuid4

from redis.asyncio import Redis
from redis.asyncio import from_url as _redis_from_url

from gateway.config import Configuracao

PREFIXO_FILA = "ponto:device-gw:push:"

_cliente_redis: Redis | None = None
_cliente_redis_loop: asyncio.AbstractEventLoop | None = None


def _cliente_preso_a_outro_loop() -> bool:
    """Mesmo problema (e mesma solucao) de `gateway.dominio.bd`: um cliente
    Redis async fica preso ao event loop em que nasceu."""
    if _cliente_redis is None or _cliente_redis_loop is None:
        return False
    try:
        return asyncio.get_running_loop() is not _cliente_redis_loop
    except RuntimeError:
        return False


def obter_redis(config: Configuracao) -> Redis:
    """Cliente Redis do processo, criado no primeiro uso (ou recriado se o
    event loop corrente mudou -- descarta a instancia presa sem tentar
    fecha-la graciosamente, porque o loop que a criou ja fechou)."""
    global _cliente_redis, _cliente_redis_loop
    if _cliente_redis is not None and _cliente_preso_a_outro_loop():
        _cliente_redis = None
        _cliente_redis_loop = None
    if _cliente_redis is None:
        # `from_url` nao tem anotacao de retorno na redis-py 5/6/8 -- mesma
        # isencao documentada em `gateway/rotas/saude.py`.
        _cliente_redis = _redis_from_url(config.redis_url)  # type: ignore[no-untyped-call]
        try:
            _cliente_redis_loop = asyncio.get_running_loop()
        except RuntimeError:
            _cliente_redis_loop = None
    return _cliente_redis


async def encerrar_redis() -> None:
    """Uso exclusivo de teste: fecha e descarta o cliente entre casos."""
    global _cliente_redis, _cliente_redis_loop
    if _cliente_redis is not None and not _cliente_preso_a_outro_loop():
        await _cliente_redis.aclose()
    _cliente_redis = None
    _cliente_redis_loop = None


def _chave(numero_serie: str) -> str:
    return f"{PREFIXO_FILA}{numero_serie}"


async def enfileirar_comando(
    redis: Redis,
    numero_serie: str,
    *,
    verb: str,
    endpoint: str,
    body: dict[str, Any] | None = None,
    content_type: str = "application/json",
) -> str:
    """Empurra um comando para o fim da fila do terminal. Devolve o `id`
    (uuid4) do comando, usado so para correlacao em log."""
    comando_id = str(uuid4())
    envelope = {
        "id": comando_id,
        "verb": verb,
        "endpoint": endpoint,
        "contentType": content_type,
        "queryString": "",
        "body": body or {},
    }
    # As assinaturas de `redis.asyncio` sao compartilhadas com o cliente
    # sincrono (overloads da redis-py), entao o `mypy --strict` ve
    # `Awaitable[int] | int` em vez de `Awaitable[int]` puro -- mesma
    # isencao pontual em `proximo_comando`/`tamanho_fila` abaixo.
    await redis.rpush(_chave(numero_serie), json.dumps(envelope, ensure_ascii=False))  # type: ignore[misc]
    return comando_id


async def proximo_comando(redis: Redis, numero_serie: str) -> dict[str, Any] | None:
    """Retira (`LPOP`) o comando mais antigo da fila do terminal, ou `None`
    quando nao ha nenhum -- resposta vazia e "nada a fazer, volte depois", nao
    erro."""
    bruto = await redis.lpop(_chave(numero_serie))  # type: ignore[misc]
    if bruto is None:
        return None
    resultado: dict[str, Any] = json.loads(bruto)
    return resultado


async def tamanho_fila(redis: Redis, numero_serie: str) -> int:
    """Quantos comandos aguardam este terminal -- usado por diagnostico."""
    return int(await redis.llen(_chave(numero_serie)))  # type: ignore[misc]
