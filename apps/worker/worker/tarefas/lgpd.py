"""Politica de retencao e expurgo de dado pessoal (F14/A3).

O ponto guarda dois tipos de dado com prazos deliberadamente diferentes
(PROJETO.md secao 7.4 e tabela `politicas_retencao`):

* **Marcacao** -- 5 anos (1825 dias). Prazo de guarda legal. Nunca e apagada
  antes disso, e o expurgo jamais toca em `marcacoes`, `nsr_emissoes` ou
  `auditoria` sem o prazo cumprido: sao tabelas append-only com gatilho de
  imutabilidade, e uma tentativa indevida aborta na propria base.
* **Imagem de captura** -- prazo curto e configuravel (padrao 30 dias). A
  biometria em si vive cifrada em `biometria_templates`, com chave separada.

Esta tarefa e disparada pelo *scheduler* (`worker.retencao_lgpd`, a cada
execucao diaria de `verificar_politicas_retencao_lgpd`), nao pela API. Ela
delega o trabalho de verdade a `app.lgpd.expurgo.aplicar_politicas_vencidas`
(`apps/api`, instalado como biblioteca nesta imagem -- ADR-009, mesmo padrao
que `worker/despacho_webhooks.py` e `worker/tarefas/integracoes.py` ja usam
para importar `app.*`): varre as politicas ativas do tenant e trata o que ja
venceu, registrando cada execucao em `politicas_retencao.
ultima_execucao_em`/`proxima_execucao_em`/`registros_ultima_execucao`.

`simulacao=True` (padrao) e um "dry run" de verdade: a transacao inteira faz
ROLLBACK no final, entao NADA persiste -- nem a remocao de dado, nem o
bookkeeping da politica (`ultima_execucao_em` etc. so avancam quando a
chamada e real). Isso e deliberado: remocao de dado pessoal e irreversivel e
nao deve ser o comportamento acidental de uma chamada sem parametro, mesma
razao que a docstring original desta tarefa (Fase 0) ja registrava.
"""

from __future__ import annotations

import datetime as dt
from typing import Any
from uuid import UUID

from worker.log import obter_logger

logger = obter_logger("tarefas.lgpd")

__all__ = ["expurgo_lgpd"]


async def expurgo_lgpd(
    ctx: dict[str, Any],
    *,
    tenant_id: str,
    politica_id: str | None = None,
    simulacao: bool = True,
) -> dict[str, Any]:
    """Aplica a politica de retencao de um tenant.

    Args:
        ctx: contexto do ARQ.
        tenant_id: tenant cujo dado vencido sera expurgado.
        politica_id: politica especifica; `None` aplica todas as ativas e
            vencidas.
        simulacao: quando `True`, avalia e reporta o que seria feito, mas
            faz ROLLBACK no final -- nada e persistido. O padrao e `True`
            de proposito.
    """
    from app.db.sessao import aplicar_tenant, fabrica_de_sessoes  # type: ignore[import-not-found]
    from app.lgpd.expurgo import aplicar_politicas_vencidas  # type: ignore[import-not-found]

    logger.info(
        "expurgo_lgpd recebida",
        extra={
            "jobId": ctx.get("job_id"),
            "tenantId": tenant_id,
            "politicaId": politica_id,
            "simulacao": simulacao,
        },
    )

    fabrica = fabrica_de_sessoes()
    async with fabrica() as sessao:
        await aplicar_tenant(sessao, tenant_id)
        resultados = await aplicar_politicas_vencidas(
            sessao,
            tenant_id=UUID(tenant_id),
            politica_id=UUID(politica_id) if politica_id else None,
        )
        if simulacao:
            await sessao.rollback()
        else:
            await sessao.commit()

    payload = [
        {
            "politicaId": str(resultado.politica_id),
            "entidade": resultado.entidade,
            "acao": resultado.acao,
            "executado": resultado.executado,
            "registrosAfetados": resultado.registros_afetados,
            "motivo": resultado.motivo,
        }
        for resultado in resultados
    ]
    logger.info(
        "expurgo_lgpd concluida",
        extra={
            "jobId": ctx.get("job_id"),
            "tenantId": tenant_id,
            "simulacao": simulacao,
            "politicasAvaliadas": len(resultados),
        },
    )
    return {
        "implementado": True,
        "tarefa": "expurgo_lgpd",
        "tenantId": tenant_id,
        "simulacao": simulacao,
        "politicasAvaliadas": len(resultados),
        "resultados": payload,
        "executadoEm": dt.datetime.now(tz=dt.UTC).isoformat(),
    }
