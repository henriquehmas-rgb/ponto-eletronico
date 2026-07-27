"""Evento `ocorrencia.aberta` -- barramento interno do dominio `dominio`
(apuracao do dia, T4).

Envelope e payload identicos, campo a campo, ao declarado em
`packages/contracts/events.yaml`. A entrega por webhook e da F13; esta fase
so publica no barramento interno e prova por teste que o corpo bate com o
contrato. Mesmo padrao replicado por `app.apuracao.tratamento.eventos` (A3,
mesma fase) e por F2/F3/F5 (`app.pessoas.eventos`, `app.marcacao.eventos`,
...): barramento em memoria mais um `logger.info`, nunca importado de outro
dominio -- cada um tem o seu proprio.

`apuracao.recalculada` NAO e publicado aqui: quem publica e
`app.apuracao.tratamento.recalculo.recalcular_periodo` (A3), uma unica vez
por vinculo ao final do intervalo reprocessado (payload agregado
`diasAlterados`/`dataInicio`/`dataFim`), nunca uma vez por dia -- publica-lo
aqui duplicaria o evento por dia processado.
"""

from __future__ import annotations

import datetime as dt
from typing import Any
from uuid import UUID, uuid4

from app.core.log import obter_logger

logger = obter_logger("apuracao.dominio.eventos")

NOME_OCORRENCIA_ABERTA = "ocorrencia.aberta"
VERSAO_OCORRENCIA_ABERTA = 1

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
    `publicadoEm` e `empresaId`."""
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
    """Publica um envelope no barramento interno."""
    BARRAMENTO_INTERNO.append(envelope)
    logger.info(
        "evento de dominio publicado",
        extra={"tipo": envelope["tipo"], "id": envelope["id"], "tenantId": envelope["tenantId"]},
    )


def publicar_ocorrencia_aberta(
    *,
    tenant_id: UUID,
    ocorrencia_id: UUID,
    colaborador_id: UUID,
    data: dt.date,
    codigo: str,
    severidade: str,
    vinculo_id: UUID | None = None,
    apuracao_dia_id: UUID | None = None,
    descricao: str | None = None,
) -> dict[str, Any]:
    """Publica `ocorrencia.aberta`. Chamado por `servico.py` ao abrir uma
    ocorrencia nova durante `apurar_dia` -- nunca para uma ocorrencia ja
    aberta anteriormente (idempotencia de ocorrencia)."""
    dados: dict[str, Any] = {
        "ocorrenciaId": str(ocorrencia_id),
        "colaboradorId": str(colaborador_id),
        "data": data.isoformat(),
        "codigo": codigo,
        "severidade": severidade,
    }
    if vinculo_id is not None:
        dados["vinculoId"] = str(vinculo_id)
    if apuracao_dia_id is not None:
        dados["apuracaoDiaId"] = str(apuracao_dia_id)
    if descricao is not None:
        dados["descricao"] = descricao
    envelope = montar_envelope(
        tipo=NOME_OCORRENCIA_ABERTA,
        versao=VERSAO_OCORRENCIA_ABERTA,
        tenant_id=tenant_id,
        dados=dados,
    )
    publicar(envelope)
    return envelope
