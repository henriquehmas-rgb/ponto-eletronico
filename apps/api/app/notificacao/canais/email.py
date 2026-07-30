"""Adaptador de envio por e-mail -- T11, A3.

Sem credencial de SMTP configurada em lugar nenhum do repositório
(confirmado em `infra/.env.example`: nenhuma variável `SMTP_*`/`EMAIL_*`,
PCF §2.8). O adaptador REAL desta fase é "log estruturado + marca como
enviada", nunca uma chamada HTTP/SMTP inventada para um provedor sem
credencial (PCF, proibição 7).

A interface (`enviar`) já é a definitiva: quando houver credencial real
(SMTP ou um provedor transacional), só o CORPO desta função muda -- quem
chama (`worker.tarefas.notificacoes`) e a assinatura continuam os mesmos.
"""

from __future__ import annotations

from ponto_contracts import Notificacao

from app.core.log import obter_logger

logger = obter_logger("notificacao.canais.email")

#: Grava em `notificacoes.provedor` mesmo sem chamada real, documentando
#: qual seria o provedor quando o canal for plugado de verdade.
PROVEDOR = "smtp"


async def enviar(notificacao: Notificacao) -> bool:
    """ "Envia" a notificação por e-mail.

    # TODO F10+N: trocar por SMTP real (ou um provedor transacional) quando
    # houver credencial (`SMTP_*` em `infra/.env.example`) -- só este corpo
    # muda, a assinatura e quem chama continuam os mesmos.
    """
    logger.info(
        "e-mail (adaptador provisorio) enviado",
        extra={
            "notificacaoId": str(notificacao.id),
            "usuarioId": str(notificacao.usuario_id) if notificacao.usuario_id else None,
            "evento": notificacao.evento,
            "titulo": notificacao.titulo,
        },
    )
    notificacao.provedor = PROVEDOR
    return True


__all__ = ["PROVEDOR", "enviar"]
