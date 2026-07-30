"""Adaptadores de envio por canal (`push`, `email`, `in_app`) -- T11, A3.

Cada adaptador expõe `async def enviar(notificacao) -> bool`, mesma
assinatura fixada, plugável sem mudar quem chama
(`worker.tarefas.notificacoes.processar_fila_notificacoes`). `ADAPTADORES` é
o único ponto de despacho por `notificacoes.canal`.

`whatsapp`/`sms` ficam de fora de propósito nesta fase (PCF §2.8): sem
adaptador registrado aqui, o worker trata como canal ainda sem
implementação (nunca finge sucesso, nunca chama HTTP para um provedor sem
credencial -- proibição 7 do PCF).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from ponto_contracts import Notificacao

from app.notificacao.canais import email, in_app, push

AdaptadorCanal = Callable[[Notificacao], Awaitable[bool]]

ADAPTADORES: dict[str, AdaptadorCanal] = {
    "push": push.enviar,
    "email": email.enviar,
    "in_app": in_app.enviar,
}

__all__ = ["ADAPTADORES", "AdaptadorCanal", "email", "in_app", "push"]
