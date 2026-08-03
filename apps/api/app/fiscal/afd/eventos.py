"""Evento de domínio `afd.gerado` — barramento interno de `app.fiscal.afd`
(F12/A1). Mesmo padrão replicado por F2-F5/F10 (`app.pessoas.eventos`,
`app.marcacao.eventos`, `app.workflow.fechamento.eventos`, ...): barramento
em memória mais um `logger.info`, nunca importado de outra fase — a entrega
por webhook é da F13 (`webhook_publico: true` em `events.yaml`, mas esta
fase só publica no barramento interno do próprio módulo)."""

from __future__ import annotations

import datetime as dt
from typing import Any
from uuid import UUID, uuid4

from app.core.log import obter_logger

logger = obter_logger("fiscal.afd.eventos")

NOME_AFD_GERADO = "afd.gerado"
VERSAO_AFD_GERADO = 1

#: Barramento interno do domínio: cada envelope publicado fica aqui, na
#: ordem de publicação. Só para prova por teste e depuração local.
BARRAMENTO_INTERNO: list[dict[str, Any]] = []


def limpar_barramento() -> None:
    """Esvazia o barramento interno. Uso exclusivo de teste, entre casos."""
    BARRAMENTO_INTERNO.clear()


def montar_envelope(
    *,
    tipo: str,
    versao: int,
    tenant_id: UUID,
    dados: dict[str, Any],
    empresa_id: UUID | None = None,
    ocorrido_em: dt.datetime | None = None,
) -> dict[str, Any]:
    """Envelope exato de `events.yaml`: id, tipo, versao, ocorridoEm,
    tenantId, dados -- campos `required`, mais os opcionais `publicadoEm` e
    `empresaId`."""
    agora = dt.datetime.now(tz=dt.UTC)
    envelope: dict[str, Any] = {
        "id": str(uuid4()),
        "tipo": tipo,
        "versao": versao,
        "ocorridoEm": (ocorrido_em or agora).isoformat(),
        "publicadoEm": agora.isoformat(),
        "tenantId": str(tenant_id),
        "dados": dados,
    }
    if empresa_id is not None:
        envelope["empresaId"] = str(empresa_id)
    return envelope


def publicar(envelope: dict[str, Any]) -> None:
    """Publica um envelope no barramento interno.

    F13/A3, T11 -- aditivo, corpo desta funcao e o UNICO ponto que A3 toca
    neste arquivo (PCF F13 secao 5.2/5.4): alem do `BARRAMENTO_INTERNO.
    append` acima (nome/assinatura/comportamento inalterados -- os testes
    desta fase dependem disso), registra o envelope para fan-out
    transacionalmente seguro em `webhook_entregas`. `registrar_pendente`
    NUNCA levanta excecao e so grava a linha durável depois que a
    transacao corrente (que chamou `publicar`) commitar de verdade -- ver
    `app.integracoes.webhooks.fan_out` para a costura completa."""
    BARRAMENTO_INTERNO.append(envelope)
    logger.info(
        "evento de dominio publicado",
        extra={"tipo": envelope["tipo"], "id": envelope["id"], "tenantId": envelope["tenantId"]},
    )
    from app.integracoes.webhooks.fan_out import registrar_pendente

    registrar_pendente(envelope)


def publicar_afd_gerado(
    *,
    tenant_id: UUID,
    arquivo_id: UUID,
    empresa_id: UUID,
    rep_p_id: UUID,
    nome_arquivo: str,
    periodo_inicio: dt.date,
    periodo_fim: dt.date,
    nsr_inicial: int,
    nsr_final: int,
    total_registros: int,
    hash_sha256: str,
    tamanho_bytes: int | None = None,
    assinado: bool = False,
    fracionado: bool = False,
) -> dict[str, Any]:
    """Publica `afd.gerado` — "ao final da geração, quando o status do
    arquivo passa a gerado" (`events.yaml`). Uma publicação por arquivo
    gerado (uma por fração, quando fracionado)."""
    dados: dict[str, Any] = {
        "arquivoId": str(arquivo_id),
        "empresaId": str(empresa_id),
        "repPId": str(rep_p_id),
        "nomeArquivo": nome_arquivo,
        "periodoInicio": periodo_inicio.isoformat(),
        "periodoFim": periodo_fim.isoformat(),
        "nsrInicial": nsr_inicial,
        "nsrFinal": nsr_final,
        "totalRegistros": total_registros,
        "hashSha256": hash_sha256,
        "assinado": assinado,
        "fracionado": fracionado,
    }
    if tamanho_bytes is not None:
        dados["tamanhoBytes"] = tamanho_bytes
    envelope = montar_envelope(
        tipo=NOME_AFD_GERADO,
        versao=VERSAO_AFD_GERADO,
        tenant_id=tenant_id,
        dados=dados,
        empresa_id=empresa_id,
    )
    publicar(envelope)
    return envelope
