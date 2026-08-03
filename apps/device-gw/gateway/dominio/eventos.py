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

    # F13/A3, T11 -- aditivo, TODO dentro do corpo desta funcao (unico ponto
    # que A3 tem permissao de tocar em apps/device-gw/**, PCF secao 5.4).
    # `device-gw` e imagem/pacote Python separado (nao instala `apps/api`
    # nem `apps/worker`, mesma razao de `gateway/log.py` duplicar
    # `app/core/log.py`) -- por isso a logica de fan-out fire-and-forget e
    # uma copia LOCAL e AUTOCONTIDA (import tardio, SQL inline, funcao
    # aninhada), em vez de importar `worker.despacho_webhooks` ou
    # `app.integracoes.webhooks.fan_out`. `publicar_terminal_online` roda
    # SEMPRE depois que a leitura de `terminal_saude` (unica consulta desta
    # rotina, `_publicar_online_se_estava_offline` em
    # `gateway/rotas/catchup.py`) ja saiu do `async with sessao_com_tenant`
    # -- nao ha commit pendente para esperar aqui, e o mesmo espirito de
    # "fire and forget, janela de risco pequena e documentada" do lado
    # `worker` (ver `apps/worker/worker/despacho_webhooks.py`, docstring do
    # modulo) se aplica.
    import asyncio
    import json

    async def _inserir_entrega_pendente_local() -> None:
        from sqlalchemy import text

        from gateway.dominio.bd import aplicar_tenant, fabrica_de_sessoes

        try:
            fabrica = fabrica_de_sessoes()
            async with fabrica() as sessao:
                await aplicar_tenant(sessao, str(tenant_id))
                await sessao.execute(
                    text(
                        """
                        INSERT INTO webhook_entregas
                            (tenant_id, webhook_id, evento, evento_id, payload,
                             tentativa, status, proxima_tentativa_em)
                        SELECT w.tenant_id, w.id, :evento, :evento_id,
                               CAST(:payload AS jsonb), 1, 'pendente', now()
                        FROM webhooks w
                        WHERE w.tenant_id = :tenant_id
                          AND w.status = 'ativo'
                          AND w.eventos @> ARRAY[:evento]::text[]
                          AND w.excluido_em IS NULL
                        """
                    ),
                    {
                        "evento": envelope["tipo"],
                        "evento_id": envelope["id"],
                        "payload": json.dumps(envelope, ensure_ascii=False, default=str),
                        "tenant_id": str(tenant_id),
                    },
                )
                await sessao.commit()
        except Exception:
            logger.exception(
                "falha ao gravar fan-out de webhook_entregas (device-gw)",
                extra={"tipo": envelope["tipo"]},
            )

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:  # pragma: no cover - so fora de contexto assincrono
        logger.warning(
            "publicar_terminal_online fora de um event loop; fan-out de webhook descartado",
            extra={"tipo": envelope["tipo"]},
        )
        return envelope

    # Referencia forte na propria funcao (atributo dinamico, inicializado no
    # primeiro uso) para a Task nao ser coletada pelo GC antes de terminar --
    # mesmo problema documentado em `worker.despacho_webhooks._TASKS_EM_VOO`,
    # resolvido aqui sem acrescentar nome novo ao MODULO (so ao objeto
    # funcao), para manter a mudanca restrita ao corpo de `publicar_
    # terminal_online` (unico ponto de `apps/device-gw/**` que A3 pode tocar).
    tasks_em_voo: set[asyncio.Task[None]] = (
        getattr(publicar_terminal_online, "_tasks_fan_out_em_voo", None) or set()
    )
    publicar_terminal_online._tasks_fan_out_em_voo = tasks_em_voo  # type: ignore[attr-defined]
    tarefa = loop.create_task(_inserir_entrega_pendente_local())
    tasks_em_voo.add(tarefa)
    tarefa.add_done_callback(tasks_em_voo.discard)

    return envelope
