"""Suporte de varredura cross-tenant da rotina de expurgo LGPD (F14/A3).

Modulo NOVO, dedicado -- mesmo motivo que `worker/despacho_webhooks.py`,
`worker/terminais_saude.py` (F6) e `worker/banco_horas_vencimento.py` (F4)
ja documentam para manter o diff de `worker/scheduler.py` restrito ao corpo
da funcao de cron que e desta fase.

Responsabilidade unica: encontrar, entre TODOS os tenants ativos, quais tem
ao menos uma `politicas_retencao` ativa e vencida, e enfileirar
`expurgo_lgpd` (real, `simulacao=False`) uma vez por tenant -- o trabalho de
verdade (qual entidade, qual acao, quantos registros) acontece dentro da
tarefa (`worker.tarefas.lgpd.expurgo_lgpd` -> `app.lgpd.expurgo.
aplicar_politicas_vencidas`), nao aqui.

A enumeracao cross-tenant usa `fn_tenants_ativos()` (RFC-014, SECURITY
DEFINER), reaproveitada via `worker.notificacoes_verificacao.
listar_tenants_ativos_cross_tenant` -- mesmo padrao ja usado por
`verificar_banco_horas_vencendo`/`verificar_terminal_offline`/
`verificar_notificacoes_pendentes`/`despachar_webhooks_pendentes`, nunca uma
segunda funcao `SECURITY DEFINER` (proibicao ja registrada nos modulos
irmaos).
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text

logger = logging.getLogger("worker.retencao_lgpd")

__all__ = [
    "NOME_TAREFA_EXPURGO_LGPD",
    "verificar_politicas_retencao_vencidas_cross_tenant",
]

NOME_TAREFA_EXPURGO_LGPD = "expurgo_lgpd"

_SQL_EXISTE_POLITICA_VENCIDA = """
    SELECT 1
    FROM politicas_retencao
    WHERE tenant_id = :tenant_id
      AND ativo = TRUE
      AND (proxima_execucao_em IS NULL OR proxima_execucao_em <= now())
    LIMIT 1
"""


async def verificar_politicas_retencao_vencidas_cross_tenant(*, redis: Any) -> dict[str, int]:
    """Varre `politicas_retencao` de TODO tenant ativo e enfileira
    `expurgo_lgpd` (`simulacao=False`) para cada tenant com ao menos uma
    politica vencida.

    `redis` e `ctx["redis"]` do scheduler (pool com `default_queue_name=
    FILA_MANUTENCAO`) -- `_queue_name=FILA_PADRAO` explicito no enqueue,
    mesmo motivo documentado nos modulos irmaos (`ctx["redis"]` aqui e do
    SCHEDULER, e o `worker` so consome `FILA_PADRAO`).
    """
    from app.db.sessao import aplicar_tenant, fabrica_de_sessoes  # type: ignore[import-not-found]

    from worker.filas import FILA_PADRAO
    from worker.notificacoes_verificacao import listar_tenants_ativos_cross_tenant

    tenants = await listar_tenants_ativos_cross_tenant()
    fabrica = fabrica_de_sessoes()
    tenants_com_expurgo = 0

    for tenant in tenants:
        async with fabrica() as sessao:
            await aplicar_tenant(sessao, str(tenant.id))
            linha = (
                await sessao.execute(
                    text(_SQL_EXISTE_POLITICA_VENCIDA), {"tenant_id": str(tenant.id)}
                )
            ).first()

        if linha is None:
            continue

        tenants_com_expurgo += 1
        await redis.enqueue_job(
            NOME_TAREFA_EXPURGO_LGPD,
            tenant_id=str(tenant.id),
            politica_id=None,
            simulacao=False,
            _queue_name=FILA_PADRAO,
        )

    return {
        "tenantsVerificados": len(tenants),
        "tenantsComExpurgoEnfileirado": tenants_com_expurgo,
    }
