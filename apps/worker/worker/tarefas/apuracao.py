"""Tarefas de apuracao de jornada. Implementacao na F4 (Calculo e Banco de Horas).

Sequencia canonica do dominio (ver PROJETO.md secao 4.4), que estas tarefas
executarao::

    marcacoes imutaveis
      -> regras da jornada do dia
      -> tratamentos aplicaveis (ajuste aprovado, abono, afastamento)
      -> apuracao do dia
      -> lancamentos de banco de horas
      -> fechamento

Duas invariantes que a F4 tera de honrar e que ja moldam a assinatura daqui:

* **Determinismo.** Recalcular duas vezes o mesmo periodo produz exatamente o
  mesmo resultado. Por isso a tarefa recebe a data, e nao "hoje".
* **Marcacao nunca e tocada.** A apuracao le marcacao e escreve apuracao;
  correcao vive na camada de tratamento.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from worker.filas import resultado_nao_implementado
from worker.log import obter_logger

logger = obter_logger("tarefas.apuracao")


async def apurar_dia(
    ctx: dict[str, Any],
    *,
    tenant_id: str,
    vinculo_id: str,
    data: dt.date | str,
    motivo: str = "agendado",
) -> dict[str, Any]:
    """Apura um dia de um vinculo: pareia marcacoes e calcula os componentes.

    Args:
        ctx: contexto do ARQ (`redis`, `job_id`, `job_try`).
        tenant_id: tenant dono do dado. Alimenta o RLS na F4.
        vinculo_id: vinculo (contrato) apurado.
        data: dia civil apurado, em `AAAA-MM-DD`.
        motivo: por que a apuracao foi disparada, para a trilha de auditoria.
    """
    logger.info(
        "apurar_dia recebida",
        extra={
            "jobId": ctx.get("job_id"),
            "tenantId": tenant_id,
            "vinculoId": vinculo_id,
            "data": str(data),
            "motivo": motivo,
        },
    )
    return resultado_nao_implementado(
        "apurar_dia", tenant_id=tenant_id, vinculo_id=vinculo_id, data=str(data)
    )


async def recalcular_periodo(
    ctx: dict[str, Any],
    *,
    tenant_id: str,
    vinculo_id: str | None = None,
    inicio: dt.date | str,
    fim: dt.date | str,
    motivo: str = "regra alterada",
) -> dict[str, Any]:
    """Reprocessa um intervalo afetado por mudanca retroativa.

    Dispara quando entra atestado retroativo, quando uma regra muda ou quando um
    tratamento e aprovado. A F4 registra o *diff* na auditoria e recusa
    reprocessar periodo fechado sem reabertura autorizada.

    Args:
        ctx: contexto do ARQ.
        tenant_id: tenant dono do dado.
        vinculo_id: vinculo alvo, ou `None` para todos os afetados do tenant.
        inicio: primeiro dia do intervalo, inclusive.
        fim: ultimo dia do intervalo, inclusive.
        motivo: causa do recalculo, obrigatoria na trilha de auditoria.
    """
    logger.info(
        "recalcular_periodo recebida",
        extra={
            "jobId": ctx.get("job_id"),
            "tenantId": tenant_id,
            "vinculoId": vinculo_id,
            "inicio": str(inicio),
            "fim": str(fim),
            "motivo": motivo,
        },
    )
    return resultado_nao_implementado(
        "recalcular_periodo",
        tenant_id=tenant_id,
        vinculo_id=vinculo_id,
        inicio=str(inicio),
        fim=str(fim),
    )
