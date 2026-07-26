"""Evento `terminal.online` (`packages/contracts/events.yaml`, `origem:
worker`), publicado ao final de um catch-up que encerra um periodo
classificado como offline.

Mesmo padrao de `apps/worker/worker/tarefas/importacoes.py::publicar_evento` e
`apps/api/app/pessoas/eventos.py`: barramento interno em memoria (lista +
log estruturado). A entrega por webhook -- assinatura HMAC, retentativa,
DLQ -- e da F13; esta fase so publica e prova por teste que o payload bate
campo a campo com o contrato.
"""

from __future__ import annotations

import datetime as dt
from typing import Any
from uuid import UUID, uuid4

from gateway.log import obter_logger

logger = obter_logger("dominio.eventos")

NOME_TERMINAL_ONLINE = "terminal.online"
VERSAO_TERMINAL_ONLINE = 1

#: Barramento interno do processo -- so para prova por teste. A F13 substitui
#: por fila de verdade sem mudar a assinatura de `publicar`.
BARRAMENTO_INTERNO: list[dict[str, Any]] = []


def limpar_barramento() -> None:
    """Uso exclusivo de teste, entre casos."""
    BARRAMENTO_INTERNO.clear()


def _montar_envelope(
    *, tipo: str, versao: int, tenant_id: UUID, dados: dict[str, Any]
) -> dict[str, Any]:
    agora = dt.datetime.now(tz=dt.UTC)
    return {
        "id": str(uuid4()),
        "tipo": tipo,
        "versao": versao,
        "ocorridoEm": agora.isoformat(),
        "publicadoEm": agora.isoformat(),
        "tenantId": str(tenant_id),
        "dados": dados,
    }


def publicar_terminal_online(
    *,
    tenant_id: UUID,
    terminal_id: UUID,
    empresa_id: UUID,
    numero_serie: str,
    retorno_em: dt.datetime | None = None,
    unidade_id: UUID | None = None,
    minutos_indisponivel: int | None = None,
    marcacoes_recuperadas: int | None = None,
    firmware: str | None = None,
) -> dict[str, Any]:
    """Publica `terminal.online` com os `required` de `events.yaml`
    preenchidos: `terminalId`, `empresaId`, `numeroSerie`, `retornoEm`."""
    dados: dict[str, Any] = {
        "terminalId": str(terminal_id),
        "empresaId": str(empresa_id),
        "numeroSerie": numero_serie,
        "retornoEm": (retorno_em or dt.datetime.now(tz=dt.UTC)).isoformat(),
    }
    if unidade_id is not None:
        dados["unidadeId"] = str(unidade_id)
    if minutos_indisponivel is not None:
        dados["minutosIndisponivel"] = minutos_indisponivel
    if marcacoes_recuperadas is not None:
        dados["marcacoesRecuperadas"] = marcacoes_recuperadas
    if firmware is not None:
        dados["firmware"] = firmware
    envelope = _montar_envelope(
        tipo=NOME_TERMINAL_ONLINE, versao=VERSAO_TERMINAL_ONLINE, tenant_id=tenant_id, dados=dados
    )
    BARRAMENTO_INTERNO.append(envelope)
    logger.info(
        "evento de dominio publicado",
        extra={"tipo": envelope["tipo"], "id": envelope["id"], "tenantId": envelope["tenantId"]},
    )
    return envelope
