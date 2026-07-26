"""Middleware que publica `usuario_id` no contexto a partir do access token.

`app/core/seguranca.py` (contrato entre fases, corpo real do agente A3) le
`contexto.usuario_atual()` dentro de `obter_sujeito()` para resolver o RBAC
completo. Este middleware e quem preenche esse valor para TODAS as rotas da
API (nao so as desta fase): decodifica o `Authorization: Bearer` quando
presente e publica `usuario_id` via `app.core.contexto.definir_usuario`.

**Nao rejeita nada aqui.** Rota publica (login, refresh, etc.) simplesmente
nao tem token, o contexto fica vazio e `core.seguranca.exigir_permissao`
responde `PONTO-AUTH-002` quando a rota exige sessao. Token invalido/expirado
tambem e silencioso aqui pelo mesmo motivo -- a rejeicao com o codigo certo
(`PONTO-AUTH-002/003/004`) e responsabilidade de quem exige autenticacao, nao
deste middleware de propagacao de contexto.

**Nao consulta o banco.** Confirma so a assinatura/validade do JWT (RS256,
emissor, audiencia, expiracao). A confirmacao de que a SESSAO referenciada
(`sid`) segue ativa fica com as proprias rotas de auth que fazem essa checagem
explicitamente (`app.identidade.tokens.dependencias.obter_sujeito_autenticado`,
usada por `logout`, `reautenticar`, `listarSessoes`, `revogarSessao` e
`obterSessaoAtual`). Isso limita a janela de uma sessao revogada continuar
"autenticando" em outras rotas ao tempo de vida do access token (15 minutos).

**Pendente de fiacao.** Este middleware precisa ser registrado em
`app/main.py` (ownership exclusivo do agente A2), depois de `TenantMiddleware`
e antes de `RegistroDeAcessoMiddleware` na ordem de `add_middleware` (que roda
do ultimo adicionado para o primeiro). Registrado em `docs/backlog.md` para o
agente A2 fazer a fiacao.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from app.core import contexto
from app.core.erros import ErroDeAplicacao
from app.identidade.tokens.jwt import decodificar_access_token

ProximoMiddleware = Callable[[Request], Awaitable[Response]]


class AutenticacaoMiddleware(BaseHTTPMiddleware):
    """Decodifica o access token, quando presente, e publica `usuario_id`."""

    def __init__(self, app: ASGIApp, *, cabecalho: str = "Authorization") -> None:
        super().__init__(app)
        self._cabecalho = cabecalho

    async def dispatch(self, request: Request, call_next: ProximoMiddleware) -> Response:
        valor = request.headers.get(self._cabecalho) or ""
        if valor.lower().startswith("bearer "):
            token = valor.split(" ", 1)[1].strip()
            if token:
                try:
                    claims = decodificar_access_token(token)
                except ErroDeAplicacao:
                    pass
                else:
                    contexto.definir_usuario(claims["sub"])
        return await call_next(request)
