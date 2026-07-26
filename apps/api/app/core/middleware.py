"""Middlewares de plataforma: request-id, tenant e registro de acesso.

Ordem de execucao (o ultimo `add_middleware` roda primeiro, ver `app.main`):

    1. RequestIdMiddleware       -- cria/propaga a correlacao
    2. TenantMiddleware          -- resolve o tenant da requisicao
    3. RegistroDeAcessoMiddleware -- registra o resultado com duracao

O request-id precisa vir antes de tudo para que qualquer falha, inclusive a
resolucao de tenant, ja saia correlacionada no log e no corpo do erro.

**F1.** O `TenantMiddleware` resolve o identificador do tenant (cabecalho
`X-Tenant` ou subdominio do host) e, quando um identificador foi informado,
valida sua existencia contra `fn_resolve_tenant` (`app/identidade/tenancy`),
recusando tenant inexistente (`PONTO-TEN-001`) ou suspenso/cancelado
(`PONTO-TEN-003`) antes mesmo de a requisicao chegar a rota. Quando NENHUM
identificador e informado, o middleware **nao** bloqueia a requisicao aqui: a
exigencia de tenant e responsabilidade de quem abre sessao de banco
(`app/db/sessao.py:obter_sessao`, que responde `PONTO-VAL-011` se
`app.tenant_id` nao foi resolvido). Essa camada dupla existe porque nem toda
rota de `/v1/...` toca o banco (rotas ainda em `501` na Fase 0, por exemplo), e
o teste de regressao do andaime (`tests/test_andaime.py`) depende de que a
ausencia de `X-Tenant` continue nao bloqueando essas rotas.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from app.core import contexto, erros
from app.core.config import Configuracao
from app.core.log import obter_logger
from app.db.sessao import obter_engine
from app.identidade.tenancy.resolucao import resolver_tenant

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
    """Resolve o tenant da requisicao, valida e publica no contexto.

    Precedencia, como o contrato define:

    1. Cabecalho `X-Tenant` (usado por cliente de integracao que fala com
       `api.ponto.<dominio>`).
    2. Subdominio do host (`seeg.ponto.<dominio>` -> `seeg`), o caminho normal
       do acesso pelo navegador.

    Quando um identificador foi informado (por qualquer uma das duas vias),
    ele e resolvido contra `fn_resolve_tenant` (unica porta segura antes de
    existir `app.tenant_id` na sessao -- ver
    `app/identidade/tenancy/resolucao.py`). Tenant inexistente responde
    `PONTO-TEN-001` (404); `suspenso`/`cancelado` responde `PONTO-TEN-003`
    (403). O identificador publicado no contexto passa a ser o **UUID
    resolvido**, nunca o slug cru: e o que `app/db/sessao.py:aplicar_tenant`
    manda para `SET LOCAL app.tenant_id`, e a policy de RLS compara UUID com
    UUID.

    Quando NENHUM identificador foi informado, o middleware nao bloqueia aqui
    (ver docstring do modulo) -- apenas publica tenant vazio no contexto.

    Divergencia entre o tenant do token e o deste cabecalho e `PONTO-TEN-002`;
    so pode ser verificada depois que o token foi validado (dependencia de
    autenticacao, `app/core/seguranca.py`), portanto fora do alcance deste
    middleware, que roda antes de qualquer dependencia de rota.
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

    @staticmethod
    def _problema(request: Request, codigo: str) -> Response:
        status, corpo = erros.montar_problema(codigo=codigo, caminho=request.url.path)
        return erros.RespostaProblema(status_code=status, content=corpo)

    async def dispatch(self, request: Request, call_next: ProximoMiddleware) -> Response:
        if request.url.path in CAMINHOS_SILENCIOSOS:
            return await call_next(request)

        cabecalho = (request.headers.get(self._cabecalho) or "").strip()[:64]
        candidato = cabecalho or self._do_host(request.headers.get("host", ""))

        # So rotas de dominio (/v1/...) exigem tenant; docs/openapi/redoc nao.
        if not candidato or not request.url.path.startswith("/v1/"):
            contexto.definir_tenant(candidato)
            request.state.tenant = candidato
            return await call_next(request)

        try:
            resolvido = await resolver_tenant(obter_engine(), candidato)
        except Exception:
            # Dependencia indisponivel (banco fora do ar): falha fechada, nao
            # aberta, e em application/problem+json em vez de erro 500 cru.
            logger.exception("falha ao resolver tenant", extra={"candidato": candidato})
            return self._problema(request, "PONTO-INT-003")

        if resolvido is None:
            logger.info("tenant nao encontrado", extra={"candidato": candidato})
            return self._problema(request, "PONTO-TEN-001")
        if resolvido.bloqueado:
            logger.info(
                "tenant suspenso ou cancelado",
                extra={"tenant": str(resolvido.id), "status": resolvido.status},
            )
            return self._problema(request, "PONTO-TEN-003")

        tenant_id = str(resolvido.id)
        contexto.definir_tenant(tenant_id)
        request.state.tenant = tenant_id
        request.state.tenant_slug = resolvido.slug
        request.state.tenant_status = resolvido.status
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
