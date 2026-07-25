"""Geracao dos arquivos fiscais REP-P. Implementacao na F12.

Dois arquivos com escopos deliberadamente diferentes -- confundir os dois e o
erro que invalida o sistema numa fiscalizacao:

**AFD** (Arquivo Fonte de Dados)
    Deriva **exclusivamente** das marcacoes. Texto ASCII ISO 8859-1, campos
    separados por `|`, linhas terminadas em CR+LF, um NSR por registro comecando
    em 1 e sem lacuna, CRC-16 por registro e SHA-256 do arquivo. Registro tipo 7
    e a marcacao do REP-P. Nao enxerga tratamento, nao enxerga abono.

**AEJ** (Arquivo Eletronico de Jornada)
    Gerado pelo Programa de Tratamento. Enxerga horario contratual, tratamento,
    ausencia e banco de horas, alem das marcacoes. Substitui AFDT e ACJEF.

Assinatura CAdES (`.p7s` destacado, certificado ICP-Brasil) e tarefa da F12/A3 e
depende do e-CNPJ A1 da SEEG. Ate o certificado chegar, os arquivos sao gerados
validos porem nao assinados -- e o parametro `assinar` existe para isso.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from worker.filas import resultado_nao_implementado
from worker.log import obter_logger

logger = obter_logger("tarefas.fiscal")


async def gerar_afd(
    ctx: dict[str, Any],
    *,
    tenant_id: str,
    rep_p_id: str,
    inicio: dt.date | str,
    fim: dt.date | str,
    assinar: bool = True,
    solicitante_id: str | None = None,
) -> dict[str, Any]:
    """Gera o AFD de um REP-P para um periodo e guarda o arquivo no MinIO.

    Args:
        ctx: contexto do ARQ.
        tenant_id: tenant dono do dado.
        rep_p_id: REP-P cujo AFD sera extraido. O NSR e sequencial POR REP-P.
        inicio: primeiro dia do periodo, inclusive.
        fim: ultimo dia do periodo, inclusive.
        assinar: quando `False`, gera sem `.p7s` (certificado ICP ainda ausente).
        solicitante_id: usuario que pediu a geracao, para a trilha de auditoria.
    """
    logger.info(
        "gerar_afd recebida",
        extra={
            "jobId": ctx.get("job_id"),
            "tenantId": tenant_id,
            "repPId": rep_p_id,
            "inicio": str(inicio),
            "fim": str(fim),
            "assinar": assinar,
        },
    )
    return resultado_nao_implementado(
        "gerar_afd",
        tenant_id=tenant_id,
        rep_p_id=rep_p_id,
        inicio=str(inicio),
        fim=str(fim),
        assinar=assinar,
    )


async def gerar_aej(
    ctx: dict[str, Any],
    *,
    tenant_id: str,
    empresa_id: str,
    inicio: dt.date | str,
    fim: dt.date | str,
    assinar: bool = True,
    solicitante_id: str | None = None,
) -> dict[str, Any]:
    """Gera o AEJ de uma empresa para um periodo.

    Args:
        ctx: contexto do ARQ.
        tenant_id: tenant dono do dado.
        empresa_id: empresa (CNPJ) do arquivo. O AEJ e por empregador.
        inicio: primeiro dia do periodo, inclusive.
        fim: ultimo dia do periodo, inclusive.
        assinar: quando `False`, gera sem `.p7s`.
        solicitante_id: usuario que pediu a geracao, para a trilha de auditoria.
    """
    logger.info(
        "gerar_aej recebida",
        extra={
            "jobId": ctx.get("job_id"),
            "tenantId": tenant_id,
            "empresaId": empresa_id,
            "inicio": str(inicio),
            "fim": str(fim),
            "assinar": assinar,
        },
    )
    return resultado_nao_implementado(
        "gerar_aej",
        tenant_id=tenant_id,
        empresa_id=empresa_id,
        inicio=str(inicio),
        fim=str(fim),
        assinar=assinar,
    )
