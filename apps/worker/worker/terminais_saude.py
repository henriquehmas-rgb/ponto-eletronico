"""Suporte de banco e de evento para `verificar_terminal_offline`
(`worker/scheduler.py`, T9 do PCF da F6, agente A1).

Modulo NOVO, dedicado, para manter o diff de `worker/scheduler.py` restrito ao
corpo da funcao que e minha (a tabela de ownership da F6 so me da
`verificar_terminal_offline` e a entrada em `montar_cron()` naquele arquivo
compartilhado com F4).

Enumeracao cross-tenant via SECURITY DEFINER (RFC-013, decidida)
------------------------------------------------------------------

`verificar_terminal_offline` roda **antes** de saber qual tenant verificar: e
um cron global, nao uma tarefa enfileirada por requisicao. A role de
aplicacao (`ponto_app`) nao tem `BYPASSRLS` (ADR-001) e toda tabela de
dominio esta sob `FORCE ROW LEVEL SECURITY` -- sem `app.tenant_id`,
`SELECT * FROM terminais` devolve zero linhas, sempre.

RFC-013 decidiu (opcao b) a funcao `fn_terminais_para_verificacao_saude()`
(`packages/contracts/schema.sql`, `SECURITY DEFINER`, mesmo padrao de
`fn_resolve_tenant`/`fn_resolve_terminal`): ela roda com os privilegios de
quem a definiu, entao enumera terminais de TODOS os tenants numa unica
chamada pela role comum `ponto_app`, sem `app.tenant_id` publicado e sem
segunda credencial de banco. Toda escrita (`terminal_saude`) continua usando
a mesma conexao, com `SET LOCAL app.tenant_id` assim que o `tenant_id` de
cada linha ja e conhecido.
"""

from __future__ import annotations

import asyncio
import datetime as dt
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from worker.config import Configuracao
from worker.log import obter_logger

logger = obter_logger("terminais_saude")

NOME_TERMINAL_OFFLINE = "terminal.offline"
VERSAO_TERMINAL_OFFLINE = 1

#: Barramento interno do processo, mesmo padrao de
#: `worker/tarefas/importacoes.py::publicar_evento` -- so para prova por
#: teste ate a F13 substituir por fila de verdade.
BARRAMENTO_INTERNO: list[dict[str, Any]] = []

_engine: AsyncEngine | None = None
_loop: asyncio.AbstractEventLoop | None = None


def limpar_barramento() -> None:
    """Uso exclusivo de teste, entre casos."""
    BARRAMENTO_INTERNO.clear()


def _loop_mudou(loop_guardado: asyncio.AbstractEventLoop | None) -> bool:
    """Mesmo problema (e mesma solucao) de `apps/api/app/db/sessao.py` e de
    `apps/device-gw/gateway/dominio/bd.py`: engine assincrona presa ao event
    loop em que nasceu."""
    if loop_guardado is None:
        return False
    try:
        return asyncio.get_running_loop() is not loop_guardado
    except RuntimeError:
        return False


def _obter_engine(config: Configuracao) -> AsyncEngine:
    global _engine, _loop
    if _engine is not None and _loop_mudou(_loop):
        _engine = None
        _loop = None
    if _engine is None:
        _engine = create_async_engine(config.database_url, pool_pre_ping=True, pool_size=5)
        try:
            _loop = asyncio.get_running_loop()
        except RuntimeError:
            _loop = None
    return _engine


async def reiniciar_engines_para_teste() -> None:
    """Uso exclusivo de teste: descarta a engine entre casos/loops. Nao tenta
    fechar graciosamente uma engine presa a um loop ja encerrado -- so
    descarta a referencia (mesmo raciocinio de
    `gateway.dominio.bd.encerrar_engine`)."""
    global _engine, _loop
    if _engine is not None and not _loop_mudou(_loop):
        await _engine.dispose()
    _engine = None
    _loop = None


@dataclass(frozen=True, slots=True)
class TerminalAtivo:
    """Recorte de `terminais` que a rotina de saude precisa, de TODOS os
    tenants (por isso vem de `fn_terminais_para_verificacao_saude()`,
    SECURITY DEFINER -- RFC-013)."""

    id: UUID
    tenant_id: UUID
    numero_serie: str
    empresa_id: UUID
    unidade_id: UUID | None
    modo_comunicacao: str
    intervalo_push_segundos: int
    ultimo_contato_em: dt.datetime | None


async def listar_terminais_ativos_cross_tenant(config: Configuracao) -> list[TerminalAtivo]:
    """Enumera terminais `ativo` de TODOS os tenants via
    `fn_terminais_para_verificacao_saude()` (RFC-013): a propria role comum
    `ponto_app`, sem `app.tenant_id` publicado -- a funcao roda com os
    privilegios de quem a definiu, nao os da conexao chamadora."""
    engine = _obter_engine(config)
    async with engine.connect() as conexao:
        resultado = await conexao.execute(
            text("SELECT * FROM fn_terminais_para_verificacao_saude()")
        )
        linhas = resultado.all()
    return [
        TerminalAtivo(
            id=linha.id,
            tenant_id=linha.tenant_id,
            numero_serie=linha.numero_serie,
            empresa_id=linha.empresa_id,
            unidade_id=linha.unidade_id,
            modo_comunicacao=linha.modo_comunicacao,
            intervalo_push_segundos=linha.intervalo_push_segundos,
            ultimo_contato_em=linha.ultimo_contato_em,
        )
        for linha in linhas
    ]


def limite_offline_minutos(modo_comunicacao: str, intervalo_push_segundos: int) -> int:
    """Limite (minutos sem contato) para classificar OFFLINE, por modo de
    comunicacao -- Push e Monitor toleram folgas diferentes (T9 pede para
    documentar a escolha):

    * **push**: o terminal e quem inicia contato a cada
      `intervalo_push_segundos`. Tres ciclos perdidos (3x o intervalo,
      minimo 10 minutos) e o limiar -- um unico ciclo perdido por
      instabilidade momentanea de rede nao deveria gerar alerta.
    * **monitor**: o terminal so fala quando tem evento; ausencia de contato
      nao e sinal tao direto de queda. Usamos um piso fixo mais generoso,
      15 minutos (`terminal_offline_minutos`, o mesmo piso do device-gw).
    * **polling/direto**: quem inicia contato e o SERVIDOR; ausencia de
      "ultimo_contato_em" reflete falha do nosso proprio lado tanto quanto do
      terminal, entao o limiar e o mais generoso, 20 minutos.
    """
    if modo_comunicacao == "push":
        return max(10, (intervalo_push_segundos * 3) // 60)
    if modo_comunicacao == "monitor":
        return 15
    return 20


async def ja_esta_marcado_offline(config: Configuracao, tenant_id: UUID, terminal_id: UUID) -> bool:
    """A ultima amostra de `terminal_saude` deste terminal ja classificava
    como offline? Usado para publicar `terminal.offline` **uma vez por
    queda**, nao a cada varredura (T9)."""
    engine = _obter_engine(config)
    async with engine.connect() as conexao:
        await conexao.execute(
            text("SELECT set_config('app.tenant_id', :tenant, false)"), {"tenant": str(tenant_id)}
        )
        linha = (
            await conexao.execute(
                text(
                    "SELECT online FROM terminal_saude WHERE terminal_id = :id "
                    "ORDER BY verificado_em DESC LIMIT 1"
                ),
                {"id": str(terminal_id)},
            )
        ).first()
    return linha is not None and linha.online is False


async def gravar_amostra_saude(
    config: Configuracao,
    *,
    tenant_id: UUID,
    terminal_id: UUID,
    online: bool,
    logs_pendentes: int | None = None,
) -> None:
    """Grava uma linha em `terminal_saude` (append-only -- so `INSERT`,
    nunca `UPDATE`/`DELETE`, `ponto_app` nem tem o privilegio para os dois
    ultimos)."""
    engine = _obter_engine(config)
    async with engine.begin() as conexao:
        await conexao.execute(
            text("SELECT set_config('app.tenant_id', :tenant, true)"), {"tenant": str(tenant_id)}
        )
        await conexao.execute(
            text(
                "INSERT INTO terminal_saude (tenant_id, terminal_id, online, logs_pendentes) "
                "VALUES (:tenant_id, :terminal_id, :online, :logs_pendentes)"
            ),
            {
                "tenant_id": str(tenant_id),
                "terminal_id": str(terminal_id),
                "online": online,
                "logs_pendentes": logs_pendentes,
            },
        )


def publicar_terminal_offline(
    *,
    tenant_id: UUID,
    terminal_id: UUID,
    empresa_id: UUID,
    numero_serie: str,
    ultimo_contato_em: dt.datetime | None,
    minutos_sem_contato: int,
    unidade_id: UUID | None = None,
    logs_pendentes_estimados: int | None = None,
) -> dict[str, Any]:
    """Publica `terminal.offline` (`events.yaml`, origem `scheduler`) com os
    `required` preenchidos: `terminalId`, `empresaId`, `numeroSerie`,
    `ultimoContatoEm`, `minutosSemContato`."""
    agora = dt.datetime.now(tz=dt.UTC)
    dados: dict[str, Any] = {
        "terminalId": str(terminal_id),
        "empresaId": str(empresa_id),
        "numeroSerie": numero_serie,
        "ultimoContatoEm": (ultimo_contato_em or agora).isoformat(),
        "minutosSemContato": minutos_sem_contato,
    }
    if unidade_id is not None:
        dados["unidadeId"] = str(unidade_id)
    if logs_pendentes_estimados is not None:
        dados["logsPendentesEstimados"] = logs_pendentes_estimados
    envelope = {
        "id": str(uuid4()),
        "tipo": NOME_TERMINAL_OFFLINE,
        "versao": VERSAO_TERMINAL_OFFLINE,
        "ocorridoEm": agora.isoformat(),
        "publicadoEm": agora.isoformat(),
        "tenantId": str(tenant_id),
        "dados": dados,
    }
    BARRAMENTO_INTERNO.append(envelope)
    logger.info(
        "evento de dominio publicado",
        extra={"tipo": envelope["tipo"], "id": envelope["id"], "tenantId": envelope["tenantId"]},
    )
    return envelope
