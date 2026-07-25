"""Politica de retencao e expurgo de dado pessoal. Implementacao na F14.

O ponto guarda dois tipos de dado com prazos deliberadamente diferentes
(PROJETO.md secao 7.4 e tabela `politicas_retencao`):

* **Marcacao** -- 5 anos (1825 dias). Prazo de guarda legal. Nunca e apagada
  antes disso, e o expurgo jamais toca em `marcacoes`, `nsr_emissoes` ou
  `auditoria` sem o prazo cumprido: sao tabelas append-only com gatilho de
  imutabilidade, e uma tentativa indevida aborta na propria base.
* **Imagem de captura** -- prazo curto e configuravel (padrao 30 dias). A
  biometria em si vive cifrada em `biometria_templates`, com chave separada.

Esta tarefa e disparada pelo *scheduler*, nao pela API. Ela varre as politicas
ativas do tenant e remove o que ja venceu, registrando cada remocao na trilha de
auditoria -- expurgo silencioso e indistinguivel de vazamento.

Na Fase 0 nao apaga nada: devolve `PONTO-INT-005`.
"""

from __future__ import annotations

from typing import Any

from worker.filas import resultado_nao_implementado
from worker.log import obter_logger

logger = obter_logger("tarefas.lgpd")


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
        politica_id: politica especifica; `None` aplica todas as ativas.
        simulacao: quando `True`, apenas relata o que seria removido. O padrao e
            `True` de proposito -- remocao de dado pessoal e irreversivel e nao
            deve ser o comportamento acidental de uma chamada sem parametro.
    """
    logger.info(
        "expurgo_lgpd recebida",
        extra={
            "jobId": ctx.get("job_id"),
            "tenantId": tenant_id,
            "politicaId": politica_id,
            "simulacao": simulacao,
        },
    )
    return resultado_nao_implementado(
        "expurgo_lgpd",
        tenant_id=tenant_id,
        politica_id=politica_id,
        simulacao=simulacao,
    )
