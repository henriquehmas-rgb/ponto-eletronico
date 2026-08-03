"""Limite de taxa por cliente de API (F13/A1, T4).

`api_clients.rate_limit_por_minuto` (coluna, default 600) e os cabeçalhos
`RateLimit-Limit/Remaining/Reset/Policy` já estão no contrato e já aparecem
como `headers:` declarados em toda resposta 200/201 do OpenAPI (§2.6 do PCF)
— mas nada os preenchia de verdade antes desta fase. Este módulo fecha essa
ponta: janela fixa de 60s em Redis (`redis.asyncio`, já em uso por
`app/routers/saude.py` para o healthcheck — nenhuma dependência nova),
chave `ponto:ratelimit:{apiClientId}:{janela}`.

**Como se compõe com `exigir_escopo` (T1) sem autenticar duas vezes.** A
dependência devolvida por `exigir_limite_taxa` recebe a MESMA instância de
`Depends(exigir_escopo(...))` que a rota já declara — o cache de dependência
do FastAPI (chave = identidade do *callable*) garante que a autenticação
resolve uma única vez por requisição, mesmo aparecendo duas vezes na
assinatura do handler. Uso:

    _escopo = exigir_escopo("webhooks:ler")

    @roteador.get(...)
    async def handler(
        cliente: Annotated[ClienteAutenticado, Depends(_escopo)],
        _limite: Annotated[None, Depends(exigir_limite_taxa(_escopo))],
        response: Response,
        ...
    ) -> ...: ...

**Onde os cabeçalhos são escritos.** Em requisição dentro da cota, a própria
dependência recebe `response: Response` (injeção padrão do FastAPI: qualquer
dependência pode declarar esse parâmetro para mutar cabeçalhos da resposta
final) e escreve `RateLimit-*` nele. Na 429ª requisição, a resposta de
sucesso nunca é montada — `ErroDeAplicacao` reconstrói a resposta do zero a
partir de `exc.cabecalhos` (`app/core/erros.py:registrar_tratadores`), então
os mesmos quatro cabeçalhos (mais `Retry-After`) vão explicitamente no
argumento `cabecalhos=` da exceção, não em `response.headers`.

**Falha aberta, não fechada.** Redis fora do ar não deve derrubar a API
pública inteira — um erro de conexão é logado e a requisição segue sem
aplicar nem anunciar limite (mesmo espírito de `/ready` responder 503 só
quando Redis está PARA VALER fora do ar, nunca convertendo uma falha de
infraestrutura auxiliar em bloqueio de tráfego legítimo).
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Annotated, Any

from fastapi import Depends, Response

from app.comum.autenticacao_cliente import ClienteAutenticado
from app.core.config import obter_configuracao
from app.core.erros import ErroDeAplicacao
from app.core.log import obter_logger

if TYPE_CHECKING:
    from redis.asyncio import Redis

logger = obter_logger("limitador_taxa")

__all__ = ["JANELA_SEGUNDOS", "exigir_limite_taxa"]

#: Janela fixa da cota, em segundos. `RateLimit-Policy` usa este valor no
#: parâmetro `w` (RFC 9239 draft, ex.: `600;w=60`).
JANELA_SEGUNDOS = 60

_PREFIXO_CHAVE = "ponto:ratelimit"

_cliente_redis: Redis | None = None


def _obter_cliente_redis() -> Redis:
    """Cliente Redis do processo, criado sob demanda (mesmo espírito de
    `app/db/sessao.py:obter_engine` -- uma única instância reaproveitada).

    `redis.from_url` não publica tipos (`[[tool.mypy.overrides]] module =
    ["redis.*"]` já trata o pacote inteiro como sem stub, mesmo padrão que
    `app/routers/saude.py` já usa para a mesma chamada) -- o
    `no-untyped-call` do modo `strict` ainda dispara mesmo assim porque o
    pacote existe mas não é `py.typed`; ignorado aqui pelo mesmo motivo que
    já é tolerado em `saude.py`.
    """
    global _cliente_redis
    if _cliente_redis is None:
        import redis.asyncio as redis_assincrono

        config = obter_configuracao()
        _cliente_redis = redis_assincrono.from_url(  # type: ignore[no-untyped-call]
            config.redis_url, decode_responses=True
        )
    return _cliente_redis


async def _encerrar_cliente_redis() -> None:
    """Só para teste: descarta o cliente cacheado entre suítes que apontam
    para Redis diferentes."""
    global _cliente_redis
    if _cliente_redis is not None:
        await _cliente_redis.aclose()
        _cliente_redis = None


def _cabecalhos(limite: int, restante: int, reset_em: int) -> dict[str, str]:
    return {
        "RateLimit-Limit": str(limite),
        "RateLimit-Remaining": str(max(0, restante)),
        "RateLimit-Reset": str(reset_em),
        "RateLimit-Policy": f"{limite};w={JANELA_SEGUNDOS}",
    }


async def _verificar_e_registrar(response: Response, cliente: ClienteAutenticado) -> None:
    limite = max(1, cliente.rate_limit_por_minuto)
    agora = int(time.time())
    janela = agora // JANELA_SEGUNDOS
    reset_em = JANELA_SEGUNDOS - (agora % JANELA_SEGUNDOS)
    chave_redis = f"{_PREFIXO_CHAVE}:{cliente.api_client_id}:{janela}"

    try:
        redis_cliente = _obter_cliente_redis()
        contagem = await redis_cliente.incr(chave_redis)
        if contagem == 1:
            await redis_cliente.expire(chave_redis, JANELA_SEGUNDOS)
    except Exception:  # falha aberta deliberada, ver docstring do módulo
        logger.warning(
            "limitador de taxa indisponivel (Redis); requisicao segue sem limite",
            extra={"apiClientId": str(cliente.api_client_id)},
        )
        return

    cabecalhos = _cabecalhos(limite, limite - contagem, reset_em)
    if contagem > limite:
        cabecalhos["RateLimit-Remaining"] = "0"
        raise ErroDeAplicacao(
            "PONTO-RATE-001",
            tentar_novamente_em=reset_em,
            cabecalhos={**cabecalhos, "Retry-After": str(reset_em)},
            contexto_log={"apiClientId": str(cliente.api_client_id), "contagem": contagem},
        )

    for nome, valor in cabecalhos.items():
        response.headers[nome] = valor


def exigir_limite_taxa(
    dependencia_escopo: Callable[..., Awaitable[ClienteAutenticado]],
) -> Callable[..., Awaitable[None]]:
    """Fábrica de dependência: aplica o limite de `cliente.rate_limit_por_minuto`
    e escreve os cabeçalhos `RateLimit-*`. Veja a docstring do módulo para o
    porquê de receber `dependencia_escopo` (a MESMA instância de
    `exigir_escopo(...)` já usada pela rota)."""

    async def _dependencia(
        response: Response,
        cliente: Annotated[ClienteAutenticado, Depends(dependencia_escopo)],
    ) -> None:
        await _verificar_e_registrar(response, cliente)

    return _dependencia


# Reexportado só para os testes deste módulo poderem forçar um Redis novo
# entre casos que usam URLs diferentes, sem importar o nome "privado".
_para_teste: dict[str, Any] = {
    "obter_cliente_redis": _obter_cliente_redis,
    "encerrar_cliente_redis": _encerrar_cliente_redis,
}
