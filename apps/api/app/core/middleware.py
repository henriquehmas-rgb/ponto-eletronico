"""Middlewares de plataforma: request-id, tenant e registro de acesso.

Ordem de execucao (o ultimo `add_middleware` roda primeiro, ver `app.main`):

    1. RequestIdMiddleware       -- cria/propaga a correlacao
    2. TenantMiddleware          -- resolve o tenant da requisicao
    3. RegistroDeAcessoMiddleware -- registra o resultado com duracao

O request-id precisa vir antes de tudo para que qualquer falha, inclusive a
resolucao de tenant, ja saia correlacionada no log e no corpo do erro.

**Escopo da Fase 0.** O `TenantMiddleware` apenas *resolve* o identificador do
tenant (do cabecalho `X-Tenant` ou do subdominio do host) e o publica no
contexto. Ele nao consulta o banco, nao valida existencia, nao compara com o
token e nao aplica RLS -- tudo isso e da F1. O ponto de extensao ja esta aqui
para que a F1 preencha o miolo sem mexer na montagem da aplicacao.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from app.core import contexto
from app.core.config import Configuracao
from app.core.log import obter_logger

logger = obter_logger("http")

ProximoMiddleware = Callable[[Request], Awaitable[Response]]

#: Caminhos que nao exigem tenant e nao entram no log de acesso: sao chamados
#: pelo healthcheck do Docker a cada 30 s e poluiriam a trilha.
CAMINHOS_SILENCIOSOS: frozenset[str] = frozenset({"/health", "/ready", "/live"})


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Garante um `X-Request-Id` por requisicao, de ponta a ponta.

    Aceita o valor enviado pelo cliente (util para correlacionar com o log do
    app mobile e do web) e gera um quando ausente. O valor recebido e truncado
    em 128 caracteres, o limite declarado no contrato, para nao virar vetor de
    poluicao de log.
    """

    def __init__(self, app: ASGIApp, *, cabecalho: str = "X-Request-Id") -> None:
        super().__init__(app)
        self._cabecalho = cabecalho

    async def dispatch(self, request: Request, call_next: ProximoMiddleware) -> Response:
        recebido = (request.headers.get(self._cabecalho) or "").strip()[:128]
        request_id = recebido or contexto.gerar_request_id()
        marcas = contexto.definir_contexto(request_id=request_id)
        request.state.request_id = request_id
        try:
            resposta = await call_next(request)
            resposta.headers[self._cabecalho] = request_id
            return resposta
        finally:
            # Restaurar no `finally` evita que uma excecao deixe o contexto
            # sujo para a proxima requisicao servida pela mesma task.
            contexto.restaurar_contexto(marcas)


class TenantMiddleware(BaseHTTPMiddleware):
    """Resolve o tenant da requisicao e publica no contexto.

    Precedencia, como o contrato define:

    1. Cabecalho `X-Tenant` (usado por cliente de integracao que fala com
       `api.ponto.<dominio>`).
    2. Subdominio do host (`seeg.ponto.<dominio>` -> `seeg`), o caminho normal
       do acesso pelo navegador.

    Divergencia entre o tenant do token e o do cabecalho e `PONTO-TEN-002` --
    verificacao que pertence a F1, quando existir token para comparar.
    """

    def __init__(self, app: ASGIApp, *, config: Configuracao) -> None:
        super().__init__(app)
        self._cabecalho = config.cabecalho_tenant
        self._sufixo_dominio = config.dominio_tenants.lower().lstrip(".")

    def _do_host(self, host: str) -> str:
        host = host.split(":", 1)[0].lower()
        if not self._sufixo_dominio or not host.endswith("." + self._sufixo_dominio):
            return ""
        rotulo = host[: -(len(self._sufixo_dominio) + 1)]
        # `api`, `dev` e `docs` sao hosts de servico, nao de cliente.
        if not rotulo or "." in rotulo or rotulo in {"api", "dev", "docs", "www"}:
            return ""
        return rotulo

    async def dispatch(self, request: Request, call_next: ProximoMiddleware) -> Response:
        if request.url.path in CAMINHOS_SILENCIOSOS:
            return await call_next(request)

        cabecalho = (request.headers.get(self._cabecalho) or "").strip()[:64]
        tenant = cabecalho or self._do_host(request.headers.get("host", ""))
        contexto.definir_tenant(tenant)
        request.state.tenant = tenant
        return await call_next(request)


class RegistroDeAcessoMiddleware(BaseHTTPMiddleware):
    """Uma linha de log por requisicao, com duracao e contexto.

    Substitui o access log do uvicorn (desligado em `app.core.log`), que nao
    enxerga `requestId` nem tenant.
    """

    async def dispatch(self, request: Request, call_next: ProximoMiddleware) -> Response:
        inicio = time.perf_counter()
        try:
            resposta = await call_next(request)
        except Exception:
            duracao_ms = round((time.perf_counter() - inicio) * 1000, 2)
            logger.exception(
                "requisicao falhou",
                extra={
                    "metodo": request.method,
                    "caminho": request.url.path,
                    "duracaoMs": duracao_ms,
                },
            )
            raise
        duracao_ms = round((time.perf_counter() - inicio) * 1000, 2)
        resposta.headers["X-Tempo-Resposta-Ms"] = str(duracao_ms)
        if request.url.path not in CAMINHOS_SILENCIOSOS:
            logger.info(
                "requisicao concluida",
                extra={
                    "metodo": request.method,
                    "caminho": request.url.path,
                    "status": resposta.status_code,
                    "duracaoMs": duracao_ms,
                },
            )
        return resposta
