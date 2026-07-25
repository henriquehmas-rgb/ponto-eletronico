"""Execucao assincrona de relatorios. Implementacao na F11.

O catalogo tem 24 relatorios (PROJETO.md secao 9). Relatorio de 12 meses por
1.000 colaboradores nao cabe em requisicao sincrona: a API responde 202 com um
identificador de execucao, esta tarefa produz o arquivo no MinIO e o cliente
acompanha por `GET /v1/relatorios/execucoes/{execucaoId}`.
"""

from __future__ import annotations

from typing import Any

from worker.filas import resultado_nao_implementado
from worker.log import obter_logger

logger = obter_logger("tarefas.relatorios")


async def executar_relatorio(
    ctx: dict[str, Any],
    *,
    tenant_id: str,
    execucao_id: str,
    codigo: str,
    parametros: dict[str, Any] | None = None,
    formato: str = "xlsx",
    solicitante_id: str | None = None,
) -> dict[str, Any]:
    """Executa um relatorio do catalogo e publica o arquivo no MinIO.

    Args:
        ctx: contexto do ARQ.
        tenant_id: tenant dono do dado.
        execucao_id: registro de execucao criado pela API, que recebe o progresso.
        codigo: codigo do relatorio no catalogo (ex.: `espelho-jornada`).
        parametros: periodo, filtros, agrupamentos e colunas escolhidas.
        formato: `csv`, `xlsx` ou `pdf`.
        solicitante_id: quem pediu, para a trilha de auditoria e para a entrega.
    """
    logger.info(
        "executar_relatorio recebida",
        extra={
            "jobId": ctx.get("job_id"),
            "tenantId": tenant_id,
            "execucaoId": execucao_id,
            "codigo": codigo,
            "formato": formato,
        },
    )
    return resultado_nao_implementado(
        "executar_relatorio",
        tenant_id=tenant_id,
        execucao_id=execucao_id,
        codigo=codigo,
        formato=formato,
    )
