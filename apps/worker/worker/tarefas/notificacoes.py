"""Tarefa assíncrona que drena `notificacoes.status='pendente'` de um
tenant e chama o adaptador de canal certo (T11, F10/A3).

`app.notificacao.motor.processar_evento` (A1/A2/A4, chamado em processo
logo após publicar um evento local) só GRAVA a linha de `Notificacao`, com
`status='pendente'` -- o envio de verdade acontece aqui, fora da requisição
HTTP que originou o evento, mesmo raciocínio de `apurar_dia`/
`recalcular_periodo` (F4): um side effect potencialmente lento (chamar um
provedor externo, mesmo que hoje seja só o adaptador provisório do PCF
§2.8) nunca deveria correr dentro do ciclo de uma requisição.

Quem enfileira esta tarefa
---------------------------
Esta fase não tem uma operação HTTP dedicada a "criar notificação" -- elas
nascem em processo, dentro da transação de `criarSolicitacao`/
`decidirAprovacao`/`criarFechamento`/`assinarEspelho` (A1/A2/A4), routers
que não são ownership de A3 (PCF §5). Em vez de depender de um
`ctx["redis"].enqueue_job("processar_fila_notificacoes", ...)` que teria de
ser adicionado em código de outro agente, `worker.notificacoes_verificacao.
verificar_notificacoes_pendentes` (T11, cron a cada 10 minutos, ownership de
A3) enfileira esta tarefa, uma vez por tenant ativo, ao final de cada
varredura -- autossuficiente dentro do ownership desta fase, sem exigir
nenhuma mudança em `app/workflow/**`. Efeito prático: uma notificação criada
em processo pode levar até ~10 minutos para ser "enviada" pelo adaptador
provisório -- aceitável enquanto o adaptador real não tem SLA nenhum para
cumprir (nenhuma credencial configurada, PCF §2.8). Registrado como achado
de integração no relatório final da fase, para o orquestrador decidir se
A1/A2/A4 devem também enfileirar diretamente no futuro.

Mesmo achado de arquitetura que `worker/tarefas/apuracao.py` documenta
(import tardio de `app.*`, ver ADR-009): `apps/worker` instala `apps/api`
como biblioteca na imagem `runtime`, nunca serve HTTP.
"""

from __future__ import annotations

import datetime as dt
from typing import Any
from uuid import UUID

import sqlalchemy as sa

from worker.log import obter_logger

logger = obter_logger("tarefas.notificacoes")

#: Tamanho do lote por execução -- evita segurar a vaga do worker
#: (`ARQ_MAX_JOBS`) por tempo indefinido num tenant com fila muito grande;
#: o que sobrar fica `pendente` para a próxima varredura (10 em 10 minutos).
LOTE_PADRAO = 200

#: Tentativas de ENVIO (por notificação) antes de desistir e marcar
#: `falhou` definitivamente -- independente de retentativa de JOB do ARQ
#: (que não se aplica aqui: este job nunca levanta por notificação
#: individual falha, ver corpo da tarefa).
MAX_TENTATIVAS = 5


async def processar_fila_notificacoes(
    ctx: dict[str, Any], *, tenant_id: str, lote: int = LOTE_PADRAO
) -> dict[str, Any]:
    """Envia toda `Notificacao` `pendente` do tenant cuja janela já chegou.

    Busca `notificacoes.status='pendente' AND (agendada_para IS NULL OR
    agendada_para <= now())`, chama `app.notificacao.canais.ADAPTADORES`
    pelo `canal` da linha e atualiza `status`/`enviada_em`/`tentativas`/
    `erro`. Uma notificação cujo canal não tem adaptador registrado (hoje,
    só pode acontecer para `whatsapp`/`sms`, PCF §2.8 -- nenhuma regra do
    motor cria essas duas) fica retida em `pendente` com `erro` preenchido,
    nunca finge sucesso nem descarta silenciosamente.
    """
    from app.db.sessao import aplicar_tenant, fabrica_de_sessoes  # type: ignore[import-not-found]
    from app.notificacao.canais import ADAPTADORES  # type: ignore[import-not-found]
    from ponto_contracts import Notificacao

    logger.info(
        "processar_fila_notificacoes recebida",
        extra={"jobId": ctx.get("job_id"), "tenantId": tenant_id, "lote": lote},
    )

    tenant_uuid = UUID(tenant_id)
    agora = dt.datetime.now(tz=dt.UTC)

    enviadas = 0
    falhadas = 0
    sem_adaptador = 0

    fabrica = fabrica_de_sessoes()
    async with fabrica() as sessao:
        await aplicar_tenant(sessao, tenant_id)

        linhas = await sessao.execute(
            sa.select(Notificacao)
            .where(
                Notificacao.tenant_id == tenant_uuid,
                Notificacao.status == "pendente",
                sa.or_(
                    Notificacao.agendada_para.is_(None),
                    Notificacao.agendada_para <= agora,
                ),
            )
            .order_by(Notificacao.criado_em)
            .limit(lote)
            .with_for_update(skip_locked=True)
        )
        pendentes = list(linhas.scalars().all())

        for notificacao in pendentes:
            adaptador = ADAPTADORES.get(notificacao.canal)
            if adaptador is None:
                sem_adaptador += 1
                notificacao.erro = f"Canal '{notificacao.canal}' sem adaptador de envio nesta fase."
                continue

            try:
                sucesso = await adaptador(notificacao)
            except Exception as exc:  # falha de canal nunca derruba o lote inteiro
                sucesso = False
                notificacao.erro = f"{type(exc).__name__}: {exc}"

            notificacao.tentativas += 1
            if sucesso:
                notificacao.status = "enviada"
                notificacao.enviada_em = agora
                notificacao.erro = None
                enviadas += 1
            else:
                falhadas += 1
                if notificacao.tentativas >= MAX_TENTATIVAS:
                    notificacao.status = "falhou"

        await sessao.commit()

    resultado = {
        "implementado": True,
        "tenantId": tenant_id,
        "encontradas": len(pendentes),
        "enviadas": enviadas,
        "falhadas": falhadas,
        "semAdaptador": sem_adaptador,
        "executadoEm": agora.isoformat(),
    }
    logger.info(
        "processar_fila_notificacoes concluida", extra={"jobId": ctx.get("job_id"), **resultado}
    )
    return resultado


__all__ = ["LOTE_PADRAO", "MAX_TENTATIVAS", "processar_fila_notificacoes"]
