"""Canal de entrega `email` de `relatorio_agendamentos` (F11, T11/A3).

Mesmo tratamento que `app.notificacao.canais.email` (F10) já deu ao mesmo
problema estrutural: **sem credencial de SMTP configurada em lugar nenhum do
repositório** (confirmado em `infra/.env.example`: nenhuma variável
`SMTP_*`/`EMAIL_*`). O adaptador REAL desta fase é "log estruturado + marca
como entregue", nunca uma chamada SMTP/HTTP inventada para um provedor sem
credencial (PCF, proibição 10).

**Módulo próprio, não importa `app.notificacao.canais.email`** (PCF §5,
tabela "compartilhado dentro da fase" -- `entrega/email.py` de A3 entrega
RELATÓRIOS exportados, um arquivo genérico; é semanticamente diferente do
que aquele módulo entrega, mesmo que a chamada SMTP de baixo nível, quando
existir de verdade, provavelmente venha a ser a mesma função utilitária --
combinar a extração então, não duplicar hoje uma dependência entre módulos
de fases diferentes).

A interface (`entregar`) já é a definitiva: quando houver credencial real,
só o CORPO desta função muda.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.log import obter_logger

if TYPE_CHECKING:
    from ponto_contracts import RelatorioAgendamento, RelatorioExecucao

logger = obter_logger("relatorios.entrega.email")

#: Documenta qual seria o provedor quando o canal for plugado de verdade --
#: mesmo papel que `app.notificacao.canais.email.PROVEDOR` cumpre para
#: notificação (F10), mas como constante própria (módulo não compartilhado).
PROVEDOR = "smtp"


async def entregar(execucao: RelatorioExecucao, agendamento: RelatorioAgendamento) -> bool:
    """ "Envia" por e-mail o arquivo já gerado por `execucao` aos
    `agendamento.destinatarios`.

    # TODO F11+N: trocar por SMTP real (ou um provedor transacional) quando
    # houver credencial (`SMTP_*` em `infra/.env.example`) -- só este corpo
    # muda, a assinatura e quem chama continuam os mesmos.
    """
    if not agendamento.destinatarios:
        logger.warning(
            "agendamento de relatorio sem destinatarios para o canal email",
            extra={"agendamentoId": str(agendamento.id), "execucaoId": str(execucao.id)},
        )
        return False
    logger.info(
        "e-mail de relatorio (adaptador provisorio) enviado",
        extra={
            "execucaoId": str(execucao.id),
            "agendamentoId": str(agendamento.id),
            "destinatarios": list(agendamento.destinatarios),
            "formato": execucao.formato,
            "conteudoRef": execucao.conteudo_ref,
            "provedor": PROVEDOR,
        },
    )
    return True


__all__ = ["PROVEDOR", "entregar"]
