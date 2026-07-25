"""Contexto da requisicao corrente, propagado por `ContextVar`.

Tres informacoes atravessam toda a pilha sem passar de funcao em funcao:

* `request_id` -- correlacao ponta a ponta. Vai no log, no cabecalho de resposta
  `X-Request-Id`, no corpo de erro (`requestId`) e, a partir da F1, na trilha de
  auditoria.
* `tenant` -- slug ou UUID do cliente do SaaS. A partir da F1 e ele quem alimenta
  o `SET LOCAL app.tenant_id` de cada transacao, que e o que liga o Row Level
  Security do PostgreSQL.
* `usuario` -- identificador do sujeito autenticado. Fica vazio na Fase 0
  (autenticacao e F1) e ja existe aqui para o log nao precisar mudar de formato
  depois.

`ContextVar` e nao `contextvars.copy_context()` manual porque asyncio propaga o
contexto para toda `Task` filha automaticamente: o valor definido no middleware
continua visivel dentro do handler, do worker de background e do driver do banco.
"""

from __future__ import annotations

import secrets
from contextvars import ContextVar, Token
from dataclasses import dataclass

_request_id: ContextVar[str] = ContextVar("ponto_request_id", default="")
_tenant: ContextVar[str] = ContextVar("ponto_tenant", default="")
_usuario: ContextVar[str] = ContextVar("ponto_usuario", default="")

PREFIXO_REQUEST_ID = "req_"
_TAMANHO_SUFIXO = 26


@dataclass(frozen=True, slots=True)
class MarcasDeContexto:
    """Tokens devolvidos por `definir_contexto`, para restaurar o estado depois."""

    request_id: Token[str]
    tenant: Token[str]
    usuario: Token[str]


def gerar_request_id() -> str:
    """Identificador opaco e ordenavel o suficiente para correlacao em log."""
    return PREFIXO_REQUEST_ID + secrets.token_hex(_TAMANHO_SUFIXO // 2).upper()


def request_id_atual() -> str:
    return _request_id.get()


def tenant_atual() -> str:
    return _tenant.get()


def usuario_atual() -> str:
    return _usuario.get()


def definir_contexto(
    *, request_id: str = "", tenant: str = "", usuario: str = ""
) -> MarcasDeContexto:
    """Fixa o contexto da requisicao e devolve as marcas para restauracao."""
    return MarcasDeContexto(
        request_id=_request_id.set(request_id),
        tenant=_tenant.set(tenant),
        usuario=_usuario.set(usuario),
    )


def restaurar_contexto(marcas: MarcasDeContexto) -> None:
    """Desfaz `definir_contexto`, evitando vazamento entre requisicoes."""
    _request_id.reset(marcas.request_id)
    _tenant.reset(marcas.tenant)
    _usuario.reset(marcas.usuario)


def definir_tenant(tenant: str) -> None:
    """Atualiza somente o tenant. Usado pelo middleware de resolucao."""
    _tenant.set(tenant)


def definir_usuario(usuario: str) -> None:
    """Atualiza somente o usuario. A F1 chama isto depois de validar o token."""
    _usuario.set(usuario)


def instantaneo() -> dict[str, str]:
    """Contexto corrente em forma de dicionario, para anexar ao log."""
    dados = {
        "requestId": request_id_atual(),
        "tenant": tenant_atual(),
        "usuario": usuario_atual(),
    }
    return {chave: valor for chave, valor in dados.items() if valor}
