"""Evento de dominio `aej.gerado` -- barramento interno do dominio `aej`
(F12/A2).

Envelope e payload identicos, campo a campo, ao declarado em
`packages/contracts/events.yaml`. A entrega por webhook e da F13; esta fase
so publica no barramento interno e prova por teste que o corpo bate com o
contrato -- mesmo padrao replicado por F2-F5/F4/F10 (`app.pessoas.eventos`,
`app.marcacao.eventos`, `app.apuracao.tratamento.eventos`,
`app.workflow.fechamento.eventos`, ...): barramento em memoria mais um
`logger.info`, nunca importado de outra fase -- cada dominio tem o seu
proprio.
"""

from __future__ import annotations

import datetime as dt
from typing import Any
from uuid import UUID, uuid4

from app.core.log import obter_logger

logger = obter_logger("fiscal.aej.eventos")

NOME_AEJ_GERADO = "aej.gerado"
VERSAO_AEJ_GERADO = 1

#: Barramento interno do dominio: cada envelope publicado fica aqui, na
#: ordem de publicacao. So para prova por teste e depuracao local -- a F13
#: substitui por fila de verdade sem mudar a assinatura de `publicar`.
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
    """Monta o envelope exato de `events.yaml`: id, tipo, versao, ocorridoEm,
    tenantId, dados -- os cinco campos `required`, mais os opcionais
    `publicadoEm` e `empresaId`. Copia propria do mesmo formato usado por
    `app.workflow.fechamento.eventos.montar_envelope` (F10) -- nunca
    importada de outra fase."""
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


def publicar_aej_gerado(
    *,
    tenant_id: UUID,
    arquivo_id: UUID,
    empresa_id: UUID,
    periodo_inicio: dt.date,
    periodo_fim: dt.date,
    total_vinculos: int,
    hash_sha256: str,
    periodo_id: UUID | None = None,
    nome_arquivo: str | None = None,
    total_marcacoes: int | None = None,
    total_ausencias: int | None = None,
    total_lancamentos_banco: int | None = None,
    assinado: bool = False,
) -> dict[str, Any]:
    """Publica `aej.gerado` -- campos `required` do payload conforme
    `events.yaml`: arquivoId, empresaId, periodoInicio, periodoFim,
    totalVinculos, hashSha256 (`app.fiscal.aej.gerador`, T9, ao final de
    `gerar_aej_arquivo`, quando `status` passa a `gerado`)."""
    dados: dict[str, Any] = {
        "arquivoId": str(arquivo_id),
        "empresaId": str(empresa_id),
        "periodoInicio": periodo_inicio.isoformat(),
        "periodoFim": periodo_fim.isoformat(),
        "totalVinculos": total_vinculos,
        "hashSha256": hash_sha256,
    }
    if periodo_id is not None:
        dados["periodoId"] = str(periodo_id)
    if nome_arquivo is not None:
        dados["nomeArquivo"] = nome_arquivo
    if total_marcacoes is not None:
        dados["totalMarcacoes"] = total_marcacoes
    if total_ausencias is not None:
        dados["totalAusencias"] = total_ausencias
    if total_lancamentos_banco is not None:
        dados["totalLancamentosBanco"] = total_lancamentos_banco
    dados["assinado"] = assinado

    envelope = montar_envelope(
        tipo=NOME_AEJ_GERADO,
        versao=VERSAO_AEJ_GERADO,
        tenant_id=tenant_id,
        dados=dados,
        empresa_id=empresa_id,
    )
    publicar(envelope)
    return envelope
