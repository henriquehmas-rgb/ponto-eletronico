"""Suporte de banco e de evento para `verificar_terminal_offline`
(`worker/scheduler.py`, T9 do PCF da F6, agente A1).

Modulo NOVO, dedicado, para manter o diff de `worker/scheduler.py` restrito ao
corpo da funcao que e minha (a tabela de ownership da F6 so me da
`verificar_terminal_offline` e a entrada em `montar_cron()` naquele arquivo
compartilhado com F4).

Duas credenciais de banco (RFC-013, interino -- opcao a)
-----------------------------------------------------------

`verificar_terminal_offline` roda **antes** de saber qual tenant verificar: e
um cron global, nao uma tarefa enfileirada por requisicao. A role de
aplicacao (`ponto_app`) nao tem `BYPASSRLS` (ADR-001) e toda tabela de
dominio esta sob `FORCE ROW LEVEL SECURITY` -- sem `app.tenant_id`,
`SELECT * FROM terminais` devolve zero linhas, sempre.

Por isso este modulo usa DUAS conexoes:

* `database_url_suporte` (`worker/config.py`) -- role com `BYPASSRLS`
  (`ponto_suporte`, ja existe em `packages/contracts/schema.sql` secao 20),
  **somente leitura**, usada so para enumerar terminais de todos os tenants.
* `database_url` comum (`ponto_app`) -- usada com `SET LOCAL app.tenant_id`
  para toda escrita (`terminal_saude`), assim que o `tenant_id` de cada linha
  ja e conhecido.

RFC-013 propoe substituir a enumeracao por uma funcao `SECURITY DEFINER`
dedicada (mesmo padrao de `fn_resolve_tenant`/`fn_resolve_terminal`), o que
eliminaria a necessidade da segunda credencial. Ate a decisao, este e o
caminho interino.
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

_engine_suporte: AsyncEngine | None = None
_engine_app: AsyncEngine | None = None
_loop_suporte: asyncio.AbstractEventLoop | None = None
_loop_app: asyncio.AbstractEventLoop | None = None


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


def _engine_de_suporte(config: Configuracao) -> AsyncEngine:
    global _engine_suporte, _loop_suporte
    if _engine_suporte is not None and _loop_mudou(_loop_suporte):
        _engine_suporte = None
        _loop_suporte = None
    if _engine_suporte is None:
        url = config.database_url_suporte or config.database_url
        _engine_suporte = create_async_engine(url, pool_pre_ping=True, pool_size=2)
        try:
            _loop_suporte = asyncio.get_running_loop()
        except RuntimeError:
            _loop_suporte = None
    return _engine_suporte


def _engine_de_aplicacao(config: Configuracao) -> AsyncEngine:
    global _engine_app, _loop_app
    if _engine_app is not None and _loop_mudou(_loop_app):
        _engine_app = None
        _loop_app = None
    if _engine_app is None:
        _engine_app = create_async_engine(config.database_url, pool_pre_ping=True, pool_size=5)
        try:
            _loop_app = asyncio.get_running_loop()
        except RuntimeError:
            _loop_app = None
    return _engine_app


async def reiniciar_engines_para_teste() -> None:
    """Uso exclusivo de teste: descarta as engines entre casos/loops. Nao
    tenta fechar graciosamente uma engine presa a um loop ja encerrado --
    so descarta a referencia (mesmo raciocinio de
    `gateway.dominio.bd.encerrar_engine`)."""
    global _engine_suporte, _engine_app, _loop_suporte, _loop_app
    if _engine_suporte is not None and not _loop_mudou(_loop_suporte):
        await _engine_suporte.dispose()
    if _engine_app is not None and not _loop_mudou(_loop_app):
        await _engine_app.dispose()
    _engine_suporte = None
    _engine_app = None
    _loop_suporte = None
    _loop_app = None


@dataclass(frozen=True, slots=True)
class TerminalAtivo:
    """Recorte de `terminais` que a rotina de saude precisa, de TODOS os
    tenants (por isso vem da conexao com `BYPASSRLS`, so leitura)."""

    id: UUID
    tenant_id: UUID
    numero_serie: str
    empresa_id: UUID
    unidade_id: UUID | None
    fabricante: str
    modo_comunicacao: str
    intervalo_push_segundos: int
    ultimo_contato_em: dt.datetime | None
    ultimo_log_externo_id: int


async def listar_terminais_ativos_cross_tenant(config: Configuracao) -> list[TerminalAtivo]:
    """Enumera terminais `ativo` de TODOS os tenants (RFC-013, interino)."""
    engine = _engine_de_suporte(config)
    async with engine.connect() as conexao:
        resultado = await conexao.execute(
            text(
                "SELECT id, tenant_id, numero_serie, empresa_id, unidade_id, fabricante, "
                "modo_comunicacao, intervalo_push_segundos, ultimo_contato_em, "
                "ultimo_log_externo_id "
                "FROM terminais WHERE status = 'ativo' AND excluido_em IS NULL"
            )
        )
        linhas = resultado.all()
    return [
        TerminalAtivo(
            id=linha.id,
            tenant_id=linha.tenant_id,
            numero_serie=linha.numero_serie,
            empresa_id=linha.empresa_id,
            unidade_id=linha.unidade_id,
            fabricante=linha.fabricante,
            modo_comunicacao=linha.modo_comunicacao,
            intervalo_push_segundos=linha.intervalo_push_segundos,
            ultimo_contato_em=linha.ultimo_contato_em,
            ultimo_log_externo_id=linha.ultimo_log_externo_id,
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
    engine = _engine_de_aplicacao(config)
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
    engine = _engine_de_aplicacao(config)
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
    fabricante: str,
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
        "fabricante": fabricante,
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
