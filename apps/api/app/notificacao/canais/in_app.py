"""Canal in-app -- T11, A3.

Não há transporte externo aqui: a própria linha de `notificacoes`
(`canal='in_app'`) É o canal -- quem a consome, no futuro, é
`GET /v1/notificacoes` (ainda não existe no contrato; achado registrado no
PCF §2.7 item 1). "Enviar" nesta fase significa só marcar a linha como
disponível: não há rede pelo meio para falhar, então este adaptador nunca
retorna `False` por erro de transporte.
"""

from __future__ import annotations

from ponto_contracts import Notificacao

from app.core.log import obter_logger

logger = obter_logger("notificacao.canais.in_app")

PROVEDOR = "in_app"


async def enviar(notificacao: Notificacao) -> bool:
    """Marca a notificação in-app como disponível (a linha em si é o
    canal -- ver docstring do módulo)."""
    logger.info(
        "notificacao in-app disponivel",
        extra={
            "notificacaoId": str(notificacao.id),
            "usuarioId": str(notificacao.usuario_id) if notificacao.usuario_id else None,
            "evento": notificacao.evento,
        },
    )
    notificacao.provedor = PROVEDOR
    return True


__all__ = ["PROVEDOR", "enviar"]
