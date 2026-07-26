"""Barramento interno de eventos de dominio da fase de marcacao.

Padrao identico ao de `app.pessoas.eventos` (F2), replicado aqui de proposito:
cada fase tem o seu proprio barramento em memoria ate a F13 entregar fila real
de eventos (webhooks com HMAC, retentativa, DLQ). Ate la, este modulo e o
unico produtor e o unico consumidor: publica, guarda para o teste inspecionar,
e loga a correlacao.

Uso: A2 e A3 importam `montar_envelope` e `publicar` daqui e criam, cada um no
seu proprio arquivo, as funcoes especificas de publicacao dos seus eventos
(`marcacao.criada`, `marcacao.suspeita`, `marcacao.sincronizada_offline` para
A2; `comprovante.emitido` para A3). Ninguem acrescenta funcao neste arquivo
depois da T1.
"""

from __future__ import annotations

import datetime as dt
from typing import Any
from uuid import UUID, uuid4

from app.core.log import obter_logger

logger = obter_logger("marcacao.eventos")

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
