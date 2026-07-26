"""Entrega de webhooks e sincronizacao de terminais. `enviar_webhook`: F13
(ainda stub, nao editar). `sincronizar_terminal`: F6/A2, implementada nesta
tarefa (T7 do PCF).

**`sincronizar_terminal`** empurra cadastro (hoje: usuarios; ver `_ESCOPO`
abaixo para os demais) para um coletor Control iD. Vive na mesma fila de
integracoes porque as duas tarefas sao curtas e falam com rede de terceiro --
e ficam longe da fila de apuracao, que e longa e nao pode ser atrasada por um
endpoint remoto lento.

**Esta tarefa NAO fala com o terminal diretamente.** Ela monta os comandos no
vocabulario do fabricante (`gateway.provisionamento.comandos`, T7/T8 do PCF)
e entrega ao `device-gw` via `POST /interno/terminais/{numeroSerie}/comandos`
(`gateway/rotas/push.py::enfileirar_comando`, A1/T4), que enfileira para o
proximo ciclo de Push -- o worker nunca abre sessao `login.fcgi` nem fala
`*.fcgi` por conta propria (isso e o `cliente_controlid.py` de dentro do
`device-gw`, usado por A1 no catch-up). `202`/`409 PONTO-TERM-004` (terminal
mudo, comando enfileirado do mesmo jeito) contam como entrega bem-sucedida
desta tarefa; qualquer outra resposta conta como falha, registrada no
resultado sem abortar o restante do lote.
"""

from __future__ import annotations

import datetime as dt
import zlib
from typing import Any
from uuid import UUID

import httpx
import sqlalchemy as sa
from ponto_contracts import Colaborador, Terminal
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from worker.config import obter_configuracao
from worker.filas import resultado_nao_implementado
from worker.log import obter_logger

logger = obter_logger("tarefas.integracoes")

__all__ = [
    "ErroEntregaComando",
    "enviar_webhook",
    "reiniciar_engine_para_testes",
    "sincronizar_terminal",
    "user_id_do_terminal",
]

# =============================================================================
# `user_id_do_terminal` -- COPIA deliberada de
# `apps/device-gw/gateway/provisionamento/comandos.py::user_id_do_terminal`.
# O worker nao pode importar `gateway` em producao (imagens Docker
# separadas -- mesma razao de `worker/tarefas/importacoes.py` duplicar os
# validadores de CPF/PIS da API, ver docstring daquele modulo); mesmo
# algoritmo, mesma fonte. Se o algoritmo mudar, muda nos dois lugares --
# registrado em `docs/backlog.md`.
# =============================================================================


def user_id_do_terminal(matricula: str) -> int:
    """`users.id` deterministico para esta matricula, estavel entre
    sincronizacoes (o mesmo colaborador sempre cai no mesmo `id`)."""
    return zlib.crc32(matricula.encode("utf-8")) + 1


def _montar_comando_criar_usuario(*, user_id: int, matricula: str, nome: str) -> dict[str, Any]:
    return {
        "verb": "POST",
        "endpoint": "create_objects.fcgi",
        "contentType": "application/json",
        "queryString": "",
        "body": {
            "object": "users",
            "values": [{"id": user_id, "registration": matricula, "name": nome}],
        },
    }


# =============================================================================
# Sessao de banco (lazy, self-contained -- mesmo padrao de
# `worker/tarefas/importacoes.py`, duplicado de proposito: os dois modulos
# tem ciclo de vida de engine independente, e a razao de fundo e a mesma —
# `apps/worker` nao importa `apps/api/app/db/sessao.py`, pacotes/imagens
# Docker separadas.)
# =============================================================================

_engine: AsyncEngine | None = None
_fabrica: async_sessionmaker[AsyncSession] | None = None


def _fabrica_de_sessoes() -> async_sessionmaker[AsyncSession]:
    global _engine, _fabrica
    if _fabrica is None:
        config = obter_configuracao()
        _engine = create_async_engine(config.database_url, pool_pre_ping=True)
        _fabrica = async_sessionmaker(_engine, expire_on_commit=False, autoflush=False)
    return _fabrica


async def reiniciar_engine_para_testes() -> None:
    """SOMENTE para teste: descarta a engine cacheada para que a proxima
    chamada crie uma nova, presa ao event loop corrente (mesma razao de
    `worker/tarefas/importacoes.py::reiniciar_engine_para_testes`)."""
    global _engine, _fabrica
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _fabrica = None


async def _aplicar_tenant(sessao: AsyncSession, tenant_id: str) -> None:
    """`SET LOCAL app.tenant_id` -- ADR-001 consequencia (a): o worker nao
    tem requisicao HTTP e precisa publicar o tenant explicitamente em cada
    job."""
    await sessao.execute(
        text("SELECT set_config('app.tenant_id', :tenant, true)"), {"tenant": tenant_id}
    )


def _agora() -> dt.datetime:
    return dt.datetime.now(tz=dt.UTC)


# =============================================================================
# Entrega ao device-gw
# =============================================================================


class ErroEntregaComando(RuntimeError):
    """Falha ao entregar um comando ao `device-gw` (rede, HTTP >= 500 ou
    formato de resposta inesperado). **Nao** cobre `409 PONTO-TERM-004`
    ("terminal mudo, comando enfileirado do mesmo jeito"): isso e sucesso do
    ponto de vista desta tarefa -- o comando entra na fila e sai no proximo
    contato do equipamento, exatamente como o modo Push preve."""


async def _entregar_comando(
    cliente_http: httpx.AsyncClient,
    *,
    base_url: str,
    numero_serie: str,
    comando: dict[str, Any],
) -> None:
    url = f"{base_url}/interno/terminais/{numero_serie}/comandos"
    try:
        resposta = await cliente_http.post(url, json=comando)
    except httpx.HTTPError as exc:
        raise ErroEntregaComando(f"device-gw inacessivel para {numero_serie}: {exc}") from exc
    if resposta.status_code in (202, 409):
        return
    raise ErroEntregaComando(
        f"device-gw respondeu {resposta.status_code} ao entregar comando para {numero_serie}."
    )


# =============================================================================
# Escopo da sincronizacao
# =============================================================================

#: `completo` cobre as cinco categorias; os demais valores restringem a uma
#: so. Mapeamento identico ao que `apps/api/app/terminais/servico.py`
#: (A1, T3) produz a partir de `SincronizacaoTerminalRequisicao` -- ver
#: `_escopo_de` la.
_CATEGORIAS_POR_ESCOPO: dict[str, frozenset[str]] = {
    "completo": frozenset({"usuarios", "templates", "grupos", "regras", "horarios"}),
    "usuarios": frozenset({"usuarios"}),
    "templates": frozenset({"templates"}),
    "grupos": frozenset({"grupos"}),
    "regras": frozenset({"regras"}),
    "horarios": frozenset({"horarios"}),
}

#: Categorias sem fonte de dado alcancavel nesta fase (ver docstring de cada
#: bloco em `sincronizar_terminal`) -- registradas no resultado como
#: "nao implementado", nunca silenciosamente ignoradas.
_MOTIVO_TEMPLATES = (
    "Sem fonte de foto crua disponivel nesta fase: colaboradores.foto_ref aponta para um "
    "armazenamento de objetos que nenhuma fase ainda integrou de verdade (mesma lacuna "
    "documentada em worker/tarefas/importacoes.py para conteudo_ref; ver docs/backlog.md)."
)
_MOTIVO_GRUPOS_REGRAS_HORARIOS = (
    "Grupos/regras de acesso/faixas de horario dependem do modelo de jornada e escala "
    "(tags jornadas/escalas), que sao da F3 e estao fora do escopo desta fase (PCF F6 secao 4, "
    "'Nao toca'). Registrado em docs/backlog.md para a fase que fechar esse mapeamento."
)


async def enviar_webhook(
    ctx: dict[str, Any],
    *,
    tenant_id: str,
    entrega_id: str,
    webhook_id: str,
    evento: str,
    tentativa: int = 1,
) -> dict[str, Any]:
    """Entrega uma vez o evento ao endpoint do cliente, assinado com HMAC.

    Args:
        ctx: contexto do ARQ.
        tenant_id: tenant dono do dado.
        entrega_id: registro em `webhook_entregas`, que acumula o historico.
        webhook_id: assinatura do cliente (endpoint, segredo e eventos).
        evento: nome do evento no catalogo, por exemplo `marcacao.criada`.
        tentativa: numero da tentativa, base do recuo exponencial.
    """
    logger.info(
        "enviar_webhook recebida",
        extra={
            "jobId": ctx.get("job_id"),
            "tenantId": tenant_id,
            "entregaId": entrega_id,
            "webhookId": webhook_id,
            "evento": evento,
            "tentativa": tentativa,
        },
    )
    return resultado_nao_implementado(
        "enviar_webhook",
        tenant_id=tenant_id,
        entrega_id=entrega_id,
        webhook_id=webhook_id,
        evento=evento,
        tentativa=tentativa,
    )


async def sincronizar_terminal(
    ctx: dict[str, Any],
    *,
    tenant_id: str,
    terminal_id: str,
    escopo: str = "completo",
    solicitante_id: str | None = None,
    cliente_http: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Sincroniza cadastro e biometria com um coletor Control iD.

    Args:
        ctx: contexto do ARQ.
        tenant_id: tenant dono do dado.
        terminal_id: terminal de destino.
        escopo: `completo` ou o subconjunto a propagar (`usuarios`,
            `templates`, `grupos`, `regras`, `horarios`).
        solicitante_id: quem pediu, para a trilha de auditoria.
        cliente_http: **somente para teste** -- injeta um `httpx.AsyncClient`
            (por exemplo, com `transport=httpx.MockTransport(...)`) para nao
            depender de um `device-gw` real escutando porta nenhuma. Em
            producao, `None` cria um cliente novo, descartado ao final.
    """
    logger.info(
        "sincronizar_terminal recebida",
        extra={
            "jobId": ctx.get("job_id"),
            "tenantId": tenant_id,
            "terminalId": terminal_id,
            "escopo": escopo,
        },
    )
    tenant_uuid = UUID(tenant_id)
    terminal_uuid = UUID(terminal_id)
    config = obter_configuracao()
    fabrica = _fabrica_de_sessoes()

    async with fabrica() as sessao:
        await _aplicar_tenant(sessao, tenant_id)
        terminal = (
            await sessao.execute(
                sa.select(Terminal).where(
                    Terminal.id == terminal_uuid,
                    Terminal.tenant_id == tenant_uuid,
                    Terminal.excluido_em.is_(None),
                )
            )
        ).scalar_one_or_none()
        if terminal is None:
            logger.warning(
                "terminal nao encontrado para sincronizacao",
                extra={"terminalId": terminal_id, "tenantId": tenant_id},
            )
            return {
                "implementado": True,
                "encontrado": False,
                "terminalId": terminal_id,
                "escopo": escopo,
            }

        categorias = _CATEGORIAS_POR_ESCOPO.get(escopo)
        if categorias is None:
            logger.warning("escopo de sincronizacao desconhecido", extra={"escopo": escopo})
            return {
                "implementado": True,
                "encontrado": True,
                "terminalId": terminal_id,
                "escopo": escopo,
                "erro": f"escopo desconhecido: {escopo!r}",
            }

        resultado_usuarios: dict[str, Any] | None = None
        if "usuarios" in categorias:
            linhas = (
                await sessao.execute(
                    sa.select(Colaborador.matricula, Colaborador.nome_completo).where(
                        Colaborador.tenant_id == tenant_uuid,
                        Colaborador.empresa_id == terminal.empresa_id,
                        Colaborador.excluido_em.is_(None),
                        Colaborador.status == "ativo",
                    )
                )
            ).all()

            fechar_cliente = cliente_http is None
            http = cliente_http or httpx.AsyncClient(timeout=config.device_gw_timeout_s)
            enviados = 0
            falhas = 0
            try:
                for matricula, nome in linhas:
                    comando = _montar_comando_criar_usuario(
                        user_id=user_id_do_terminal(matricula), matricula=matricula, nome=nome
                    )
                    try:
                        await _entregar_comando(
                            http,
                            base_url=config.device_gw_base_url,
                            numero_serie=terminal.numero_serie,
                            comando=comando,
                        )
                        enviados += 1
                    except ErroEntregaComando as exc:
                        falhas += 1
                        logger.warning(
                            "falha ao entregar comando de usuario ao device-gw",
                            extra={
                                "terminalId": terminal_id,
                                "matricula": matricula,
                                "erro": str(exc),
                            },
                        )
            finally:
                if fechar_cliente:
                    await http.aclose()
            resultado_usuarios = {"total": len(linhas), "enviados": enviados, "falhas": falhas}

        def _nao_implementado(categoria: str, motivo: str) -> dict[str, Any] | None:
            if categoria not in categorias:
                return None
            return {"enviados": 0, "motivo": motivo}

        resultado_templates = _nao_implementado("templates", _MOTIVO_TEMPLATES)
        resultado_grupos = _nao_implementado("grupos", _MOTIVO_GRUPOS_REGRAS_HORARIOS)
        resultado_regras = _nao_implementado("regras", _MOTIVO_GRUPOS_REGRAS_HORARIOS)
        resultado_horarios = _nao_implementado("horarios", _MOTIVO_GRUPOS_REGRAS_HORARIOS)

        terminal.ultima_sincronizacao_em = _agora()
        await sessao.commit()

    logger.info(
        "sincronizar_terminal concluida",
        extra={
            "terminalId": terminal_id,
            "escopo": escopo,
            "usuarios": resultado_usuarios,
        },
    )
    return {
        "implementado": True,
        "encontrado": True,
        "terminalId": terminal_id,
        "escopo": escopo,
        "usuarios": resultado_usuarios,
        "templates": resultado_templates,
        "grupos": resultado_grupos,
        "regras": resultado_regras,
        "horarios": resultado_horarios,
        "solicitanteId": solicitante_id,
    }
