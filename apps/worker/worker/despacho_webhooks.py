"""Suporte de fan-out e despacho de `webhook_entregas` do lado `worker`/
`scheduler` (T11/T12 do PCF da F13, agente A3).

Modulo NOVO, dedicado -- mesma razao que `worker/terminais_saude.py` (F6) e
`worker/banco_horas_vencimento.py` (F4) ja documentam para manter o diff de
`worker/scheduler.py` restrito ao corpo da funcao que e minha (ver
docstring daqueles modulos). `apps/worker/Dockerfile` ja instala `apps/api`
como biblioteca na MESMA imagem (ADR-009: "os servicos worker e scheduler do
compose apontam para este mesmo Dockerfile e para a mesma imagem"), entao
importar `app.*` daqui e valido em producao e em teste, mesmo padrao ja em
uso por `worker/notificacoes_verificacao.py`.

Duas responsabilidades, deliberadamente separadas de
`app.integracoes.webhooks.fan_out` (apps/api):

1. **Fan-out fire-and-forget dos tres produtores fora de `apps/api`**
   (`worker.terminais_saude.publicar_terminal_offline`,
   `worker.banco_horas_vencimento.publicar_banco_horas_vencendo`, e --
   via copia, `apps/device-gw/gateway/dominio/eventos.py::
   publicar_terminal_online`, que NAO pode importar este modulo, ver nota
   abaixo). Diferente do lado `apps/api` (que usa `ContextVar` + listener
   `after_commit` do SQLAlchemy, porque `publicar()` la roda MEIO de uma
   transacao HTTP ainda aberta), aqui os tres pontos de publicacao SEMPRE
   rodam **depois** que o commit local da rotina ja aconteceu (confirmado
   por leitura de cada um -- ver `docs` do relatorio desta fase):
   `publicar_terminal_offline` roda depois de `await gravar_amostra_saude`
   (que abre e fecha a propria transacao via `engine.begin()`);
   `publicar_banco_horas_vencendo` nao tem escrita propria alguma associada
   (e uma notificacao derivada de leitura, nunca corrompida por rollback);
   `publicar_terminal_online` roda depois que o `async with
   sessao_com_tenant(...)` de leitura ja saiu do escopo. Por isso, aqui
   basta *"fire and forget"*: `asyncio.create_task` para inserir a linha em
   `webhook_entregas` de forma assincrona verdadeira (nao ha callback
   sincrono do SQLAlchemy no meio do caminho como do lado `apps/api`), sem
   segurar a rotina de cron/scheduler esperando.

   **Janela de risco aceita** (documentada tambem no relatorio da fase):
   entre a rotina retornar (ou o processo terminar/crashar) e a Task
   agendada terminar de rodar, um evento pode se perder -- maior que a
   janela do lado `apps/api` (que e sincrona com a resposta HTTP), mas
   aceitavel: os tres pontos aqui sao rotinas de CRON, que rodam de novo em
   poucos minutos (`terminal.offline` a cada 5 min, `banco_horas.vencendo`
   1x/dia) ou, no caso de `terminal.online`, um evento nao entregue nao
   compromete nenhuma garantia de auditoria (o proximo catch-up bem
   sucedido gera um novo).

2. **Despacho cross-tenant de `webhook_entregas` pendentes** (rotina de
   cron nova, `worker.scheduler.despachar_webhooks_pendentes`, T11/T12):
   varre TODO tenant ativo (`fn_tenants_ativos()`, RFC-013/014, mesmo padrao
   ja usado tres vezes por `verificar_banco_horas_vencendo`/
   `verificar_terminal_offline`/`verificar_notificacoes_pendentes`) por
   linhas `status IN ('pendente','falha') AND proxima_tentativa_em <=
   now()`, reivindica cada lote com `UPDATE ... FOR UPDATE SKIP LOCKED`
   (defesa contra dupla dispensa se um dia houver mais de uma replica do
   scheduler) e enfileira `enviar_webhook` (T12) para o `worker` real
   consumir (`_queue_name=FILA_PADRAO` explicito -- `ctx["redis"]` do
   scheduler tem `default_queue_name=FILA_MANUTENCAO`, mesmo achado real de
   `app/core/filas.py`/F9b/A3 documentado tres vezes nos modulos irmaos).

Sobre `apps/device-gw/gateway/dominio/eventos.py::publicar_terminal_online`
-------------------------------------------------------------------------------
`device-gw` e uma imagem/pacote Python SEPARADO (nao instala `apps/api` nem
`apps/worker` -- mesma razao de `gateway/log.py` duplicar `app/core/log.py`).
O corpo de `publicar_terminal_online` (unico ponto que A3 tem permissao de
tocar naquele arquivo, PCF secao 5.4: "apps/device-gw/** (exceto o corpo de
publicar() no arquivo listado em secao 2.2, exclusivo de A3)") duplica a
MESMA logica de fire-and-forget deste modulo, com sua propria sessao
(`gateway.dominio.bd.sessao_com_tenant`) -- deliberado, nao um esquecimento.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger("worker.despacho_webhooks")

__all__ = [
    "NOME_TAREFA_ENVIAR_WEBHOOK",
    "despachar_webhooks_pendentes_cross_tenant",
    "publicar_fire_and_forget",
]

NOME_TAREFA_ENVIAR_WEBHOOK = "enviar_webhook"

#: Mantem referencia forte as Tasks em voo -- sem isto, o event loop pode
#: coletar a Task antes dela terminar (aviso conhecido do proprio `asyncio`:
#: "Task was destroyed but it is pending"), e uma excecao dentro dela nunca
#: seria vista nem logada.
_TASKS_EM_VOO: set[asyncio.Task[None]] = set()


async def _inserir_entrega_pendente(envelope: dict[str, Any]) -> None:
    """Async de verdade (worker tem event loop proprio rodando a Task) --
    reaproveita a MESMA sessao/engine do worker (`app.db.sessao`, ADR-009) e
    o MESMO SQL canonico de `app.integracoes.webhooks.fan_out` (ver
    docstring do modulo)."""
    from app.db.sessao import aplicar_tenant, fabrica_de_sessoes  # type: ignore[import-not-found]
    from app.integracoes.webhooks import fan_out  # type: ignore[import-not-found]

    tipo = envelope.get("tipo")
    if not tipo or tipo in fan_out.EVENTOS_INTERNOS:
        return
    tenant_id = envelope.get("tenantId")
    evento_id = envelope.get("id")
    if not tenant_id or not evento_id:
        logger.warning(
            "envelope pendente de fan-out (worker) sem tenantId/id, descartado",
            extra={"tipo": tipo},
        )
        return

    fabrica = fabrica_de_sessoes()
    async with fabrica() as sessao:
        await aplicar_tenant(sessao, str(tenant_id))
        await sessao.execute(
            fan_out.SQL_INSERIR_ENTREGAS_PENDENTES,
            {
                "evento": tipo,
                "evento_id": str(evento_id),
                "payload": fan_out.payload_json(envelope),
                "tenant_id": str(tenant_id),
            },
        )
        await sessao.commit()


async def _inserir_entrega_pendente_protegido(envelope: dict[str, Any]) -> None:
    try:
        await _inserir_entrega_pendente(envelope)
    except Exception:
        # Mesma politica do lado `apps/api` (`fan_out._apos_commit`): uma
        # falha aqui e logada e engolida, nunca propagada -- a rotina de
        # cron que publicou o evento ja terminou seu proprio trabalho com
        # sucesso, e nao deve ser derrubada por um problema no fan-out.
        logger.exception(
            "falha ao gravar fan-out de webhook_entregas (worker)",
            extra={"tipo": envelope.get("tipo")},
        )


def publicar_fire_and_forget(envelope: dict[str, Any]) -> None:
    """Agenda `_inserir_entrega_pendente` como Task, sem bloquear o
    chamador. Chamada ADITIVA, apos o `BARRAMENTO_INTERNO.append` (nome e
    comportamento inalterados), em `worker.terminais_saude.
    publicar_terminal_offline` e `worker.banco_horas_vencimento.
    publicar_banco_horas_vencendo` -- ver docstring do modulo para a prova de
    que os dois pontos ja rodam depois de qualquer commit relevante."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:  # pragma: no cover - so fora de contexto assincrono
        logger.warning(
            "publicar_fire_and_forget chamado fora de um event loop; evento descartado",
            extra={"tipo": envelope.get("tipo")},
        )
        return
    tarefa = loop.create_task(_inserir_entrega_pendente_protegido(envelope))
    _TASKS_EM_VOO.add(tarefa)
    tarefa.add_done_callback(_TASKS_EM_VOO.discard)


# =============================================================================
# Despacho cross-tenant (rotina de cron `despachar_webhooks_pendentes`,
# `worker/scheduler.py`)
# =============================================================================

_SQL_RECLAMAR_LOTE = """
    UPDATE webhook_entregas
    SET status = 'enviando'
    WHERE id IN (
        SELECT id FROM webhook_entregas
        WHERE tenant_id = :tenant_id
          AND status IN ('pendente', 'falha')
          AND proxima_tentativa_em <= now()
        ORDER BY proxima_tentativa_em
        LIMIT :lote
        FOR UPDATE SKIP LOCKED
    )
    RETURNING id, webhook_id, evento, tentativa
"""


async def despachar_webhooks_pendentes_cross_tenant(
    *, redis: Any, tamanho_lote: int = 200
) -> dict[str, int]:
    """Varre `webhook_entregas` pendentes/em retentativa de TODO tenant
    ativo e enfileira `enviar_webhook` para o `worker` consumir.

    `redis` e `ctx["redis"]` do scheduler (pool com `default_queue_name=
    FILA_MANUTENCAO`) -- `_queue_name=FILA_PADRAO` explicito em cada
    `enqueue_job`, mesmo motivo documentado no modulo.
    """
    from app.db.sessao import aplicar_tenant, fabrica_de_sessoes
    from sqlalchemy import text

    from worker.filas import FILA_PADRAO
    from worker.notificacoes_verificacao import listar_tenants_ativos_cross_tenant

    tenants = await listar_tenants_ativos_cross_tenant()
    fabrica = fabrica_de_sessoes()
    entregas_enfileiradas = 0

    for tenant in tenants:
        async with fabrica() as sessao:
            await aplicar_tenant(sessao, str(tenant.id))
            linhas = (
                await sessao.execute(
                    text(_SQL_RECLAMAR_LOTE),
                    {"tenant_id": str(tenant.id), "lote": tamanho_lote},
                )
            ).all()
            await sessao.commit()

        for linha in linhas:
            await redis.enqueue_job(
                NOME_TAREFA_ENVIAR_WEBHOOK,
                tenant_id=str(tenant.id),
                entrega_id=str(linha.id),
                webhook_id=str(linha.webhook_id),
                evento=linha.evento,
                tentativa=linha.tentativa,
                _queue_name=FILA_PADRAO,
            )
            entregas_enfileiradas += 1

    return {
        "tenantsVerificados": len(tenants),
        "entregasEnfileiradas": entregas_enfileiradas,
    }
