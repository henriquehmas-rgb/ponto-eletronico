"""Adaptador de envio por push -- T11, A3.

Sem credencial de FCM (Firebase Cloud Messaging) ou APNs configurada em
lugar nenhum do repositório (confirmado em `infra/.env.example`: nenhuma
variável `FCM_*`/`APNS_*`, PCF §2.8) e `apps/mobile` é só o esqueleto vazio
da Fase 0 (F7 -- app Flutter -- não foi executada). O adaptador REAL desta
fase é "log estruturado + marca como enviada", nunca uma chamada HTTP
inventada para um provedor sem credencial (PCF, proibição 7).

A interface (`enviar`) já é a definitiva: quando houver credencial real e
SDK de push integrado, só o CORPO desta função muda -- quem chama
(`worker.tarefas.notificacoes`) e a assinatura continuam os mesmos.
"""

from __future__ import annotations

from ponto_contracts import Notificacao

from app.core.log import obter_logger

logger = obter_logger("notificacao.canais.push")

#: Grava em `notificacoes.provedor` mesmo sem chamada real, documentando
#: qual seria o provedor quando o canal for plugado de verdade.
PROVEDOR = "fcm"


async def enviar(notificacao: Notificacao) -> bool:
    """ "Envia" a notificação push.

    # TODO F10+N: trocar por chamada real ao FCM (ou APNs, por plataforma)
    # quando houver credencial (`FCM_*` em `infra/.env.example`) e o app
    # Flutter (F7) estiver registrando token de dispositivo -- só este
    # corpo muda, a assinatura e quem chama continuam os mesmos.
    """
    logger.info(
        "push (adaptador provisorio) enviado",
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
