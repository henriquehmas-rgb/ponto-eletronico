"""Traducao `access_logs.user_id` (interno ao equipamento) -> `matricula` do
colaborador, via o campo `registration` que o provisionamento (F6/A2, T7)
grava em `users` ao criar o usuario no terminal.

`user_id` **nunca** vira `colaboradorId`: isso exigiria uma consulta a
`colaboradores`, que este servico nao tem motivo para fazer (secao 2 do PCF).
`MarcacaoCriar.matricula` e o unico campo de identificacao que o `device-gw`
envia.

Duas fontes, nesta ordem
-------------------------

1. **Cache persistido no Redis** (`ponto:device-gw:registration:<numero_serie>:
   <user_id>`), gravado por `gravar_registration_cache` -- e o caminho que A2
   (T7) deveria chamar ao criar/atualizar um `users` com `registration`. E
   OBRIGATORIO para terminal em modo **Push**: o servidor nao consegue abrir
   conexao com um equipamento atras de NAT, entao nao ha como fazer
   `load_objects.fcgi` sob demanda nesse modo.
2. **`load_objects.fcgi` sob demanda**, so quando um `ClienteControlID` foi
   passado (terminal em `polling`/`direto`, ou simulador -- que nunca tem o
   problema de NAT porque nao ha rede de verdade envolvida). O resultado
   tambem e gravado no cache persistido, para a proxima chamada nao precisar
   ir ao equipamento de novo.

Sem nenhuma das duas fontes, a conversao nao pode prosseguir --
`PONTO-TERM-005` (resposta/estado do terminal invalido para o que foi pedido).
"""

from __future__ import annotations

from redis.asyncio import Redis

from gateway.cliente_controlid import ClienteControlID
from gateway.erros import ErroDeAplicacao

CODIGO_RESPOSTA_INVALIDA = "PONTO-TERM-005"
_PREFIXO_CACHE = "ponto:device-gw:registration:"


def _chave_cache(numero_serie: str, user_id: int) -> str:
    return f"{_PREFIXO_CACHE}{numero_serie}:{user_id}"


async def gravar_registration_cache(
    redis: Redis, numero_serie: str, user_id: int, matricula: str
) -> None:
    """Popula o cache persistido. Chamado pelo provisionamento (T7, A2) ao
    criar/atualizar um `users` com `registration`, e por
    `resolver_matricula` apos uma resolucao por `load_objects.fcgi`."""
    await redis.set(_chave_cache(numero_serie, user_id), matricula)


async def resolver_matricula(
    *,
    redis: Redis,
    numero_serie: str,
    user_id: int,
    cliente: ClienteControlID | None,
    cache_local: dict[int, str],
) -> str:
    """Resolve a matricula: cache em memoria da execucao corrente -> cache
    persistido no Redis -> `load_objects.fcgi` sob demanda (so quando
    `cliente` foi passado, isto e, o terminal permite conexao direta)."""
    if user_id in cache_local:
        return cache_local[user_id]

    persistida = await redis.get(_chave_cache(numero_serie, user_id))
    if persistida:
        valor = persistida.decode("utf-8") if isinstance(persistida, bytes) else str(persistida)
        cache_local[user_id] = valor
        return valor

    if cliente is None:
        raise ErroDeAplicacao(
            CODIGO_RESPOSTA_INVALIDA,
            detalhe=(
                f"matricula de user_id={user_id} nao esta em cache e o terminal "
                f"{numero_serie} nao permite consulta direta (modo push)."
            ),
        )
    registros = await cliente.load_objects(
        "users", onde=[{"field": "id", "operator": "=", "value": user_id}]
    )
    if not registros:
        raise ErroDeAplicacao(
            CODIGO_RESPOSTA_INVALIDA, detalhe=f"users.id={user_id} nao encontrado no terminal."
        )
    matricula = registros[0].get("registration")
    if not matricula:
        raise ErroDeAplicacao(
            CODIGO_RESPOSTA_INVALIDA,
            detalhe=f"users.id={user_id} sem 'registration' cadastrada (provisionamento pendente).",
        )
    valor = str(matricula)
    cache_local[user_id] = valor
    await gravar_registration_cache(redis, numero_serie, user_id, valor)
    return valor
