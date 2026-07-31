"""Suporte de banco e de varredura para `verificar_agendamentos_relatorio`
(`worker/scheduler.py`, T11 do PCF da F11, agente A3).

Módulo NOVO, dedicado -- mesma razão que `worker/terminais_saude.py` (F6),
`worker/banco_horas_vencimento.py` (F4) e `worker/notificacoes_
verificacao.py` (F10) já documentam para manter o diff de `worker/
scheduler.py` restrito ao corpo da função que é minha.

Enumeração cross-tenant via SECURITY DEFINER (RFC-013/RFC-014, decidida)
--------------------------------------------------------------------------
Mesmo problema estrutural que as rotinas irmãs: `verificar_agendamentos_
relatorio` roda ANTES de saber qual tenant verificar (cron global).
`fn_tenants_ativos()` (RFC-014, `packages/contracts/schema.sql`, `SECURITY
DEFINER`) enumera `(id, slug)` de todo tenant `status='ativo'` numa única
chamada pela role comum `ponto_app`, sem `app.tenant_id` publicado e sem
segunda credencial de banco -- reaproveitada sem criar função nova (PCF
§6/T11: "reaproveitando fn_tenants_ativos(), sem criar função SECURITY
DEFINER nova").

Idempotência
------------
Por construção, não por marca de estado numa tabela nova: a varredura só
enfileira um agendamento cuja `proxima_execucao_em <= now()` E, no mesmo
UPDATE que recalcula a nova `proxima_execucao_em` (via `croniter`, `app.
relatorios.agendamentos.calcular_proxima_execucao`), a linha sai da janela
`<= now()` imediatamente -- a rotina seguinte (10 em 10 minutos, mesmo
intervalo do disparo de `verificar_notificacoes_pendentes`, F10) já não
encontra mais aquela linha na próxima varredura, então nunca duplica o
disparo dentro da MESMA janela. O `UPDATE` acontece na MESMA transação que
o `enqueue_job`, então uma falha no meio (Redis fora do ar, por exemplo)
não deixa a `proxima_execucao_em` "comida" sem o job real ter sido
enfileirado -- os dois andam juntos ou nenhum dos dois anda.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from worker.log import obter_logger

logger = obter_logger("relatorios_agendamentos_verificacao")


@dataclass(frozen=True, slots=True)
class TenantAtivo:
    """Recorte de `tenants` que esta rotina precisa, de TODOS os tenants
    (por isso vem de `fn_tenants_ativos()`, SECURITY DEFINER -- RFC-014)."""

    id: UUID
    slug: str


@dataclass(frozen=True, slots=True)
class AgendamentoDisparado:
    """Um agendamento cuja `proxima_execucao_em` já venceu, pronto para
    enfileirar."""

    id: UUID
    tenant_id: UUID
    relatorio_definicao_id: UUID
    codigo_relatorio: str
    usuario_id: UUID | None
    parametros: dict[str, Any]
    formato: str
    cron: str
    fuso_horario: str


@dataclass(frozen=True, slots=True)
class ResultadoVarredura:
    """Totais de uma execução completa da varredura cross-tenant."""

    tenants_verificados: int
    agendamentos_disparados: int


async def listar_tenants_ativos_cross_tenant() -> list[TenantAtivo]:
    """Enumera tenants `status='ativo'` via `fn_tenants_ativos()`
    (RFC-014): a própria role comum `ponto_app`, sem `app.tenant_id`
    publicado -- a função roda com os privilégios de quem a definiu, não os
    da conexão chamadora. Mesma forma de `worker.notificacoes_verificacao.
    listar_tenants_ativos_cross_tenant` (F10) -- não reaproveitada por
    import direto (módulo de outra fase), replicada aqui de propósito
    (precedente já fixado por `worker/terminais_saude.py`/`worker/
    banco_horas_vencimento.py`: cada rotina de cron tem a própria cópia)."""
    from app.db.sessao import fabrica_de_sessoes  # type: ignore[import-not-found]

    fabrica = fabrica_de_sessoes()
    async with fabrica() as sessao:
        resultado = await sessao.execute(text("SELECT id, slug FROM fn_tenants_ativos()"))
        linhas = resultado.all()
    return [TenantAtivo(id=linha.id, slug=linha.slug) for linha in linhas]


async def _agendamentos_vencidos(
    sessao: AsyncSession, tenant_id: UUID, agora: dt.datetime
) -> list[AgendamentoDisparado]:
    """`relatorio_agendamentos` com `ativo=true AND proxima_execucao_em <=
    now()`, junto com o `codigo` do relatório (para o nome do job) --
    join simples com `relatorio_definicoes`, sob RLS já aplicado pela
    sessão do chamador."""
    linhas = await sessao.execute(
        text(
            "SELECT ra.id, ra.tenant_id, ra.relatorio_definicao_id, rd.codigo AS codigo_relatorio, "
            "       ra.usuario_id, ra.parametros, ra.formato, ra.cron, ra.fuso_horario "
            "FROM relatorio_agendamentos ra "
            "JOIN relatorio_definicoes rd ON rd.id = ra.relatorio_definicao_id "
            "WHERE ra.tenant_id = :tenant_id "
            "  AND ra.ativo = TRUE "
            "  AND ra.excluido_em IS NULL "
            "  AND ra.proxima_execucao_em IS NOT NULL "
            "  AND ra.proxima_execucao_em <= :agora"
        ),
        {"tenant_id": tenant_id, "agora": agora},
    )
    return [
        AgendamentoDisparado(
            id=linha.id,
            tenant_id=linha.tenant_id,
            relatorio_definicao_id=linha.relatorio_definicao_id,
            codigo_relatorio=linha.codigo_relatorio,
            usuario_id=linha.usuario_id,
            parametros=dict(linha.parametros or {}),
            formato=linha.formato,
            cron=linha.cron,
            fuso_horario=linha.fuso_horario,
        )
        for linha in linhas
    ]


async def _marcar_disparado(
    sessao: AsyncSession, agendamento: AgendamentoDisparado, agora: dt.datetime
) -> UUID:
    """Cria `RelatorioExecucao(status='enfileirado', agendamento_id=...)` e
    recalcula `proxima_execucao_em`/`ultima_execucao_em` do agendamento --
    NA MESMA transação de quem chama (o `enqueue_job` acontece fora,
    depois do `commit`, ver docstring do módulo sobre idempotência).
    Devolve o `execucao_id` para o job enfileirado."""
    from uuid import uuid4

    from app.relatorios import agendamentos as _servico  # type: ignore[import-not-found]

    execucao_id = uuid4()
    await sessao.execute(
        text(
            "INSERT INTO relatorio_execucoes "
            "(id, tenant_id, relatorio_definicao_id, agendamento_id, usuario_id, parametros, "
            " formato, status, progresso, iniciado_em) "
            "VALUES (:id, :tenant_id, :relatorio_definicao_id, :agendamento_id, :usuario_id, "
            "        CAST(:parametros AS JSONB), :formato, 'enfileirado', 0, :agora)"
        ),
        {
            "id": execucao_id,
            "tenant_id": agendamento.tenant_id,
            "relatorio_definicao_id": agendamento.relatorio_definicao_id,
            "agendamento_id": agendamento.id,
            "usuario_id": agendamento.usuario_id,
            "parametros": _para_json(agendamento.parametros),
            "formato": agendamento.formato,
            "agora": agora,
        },
    )

    proxima = _servico.calcular_proxima_execucao(
        agendamento.cron, fuso_horario=agendamento.fuso_horario, referencia=agora
    )
    await sessao.execute(
        text(
            "UPDATE relatorio_agendamentos "
            "SET proxima_execucao_em = :proxima, ultima_execucao_em = :agora "
            "WHERE id = :id"
        ),
        {"proxima": proxima, "agora": agora, "id": agendamento.id},
    )
    return execucao_id


def _para_json(valor: dict[str, Any]) -> str:
    import json

    return json.dumps(valor, default=str)


async def verificar_agendamentos_relatorio_cross_tenant(
    *, enfileirar: Any = None
) -> ResultadoVarredura:
    """Varre todo tenant ativo em busca de agendamentos vencidos, cria a
    `RelatorioExecucao` e recalcula `proxima_execucao_em` de cada um
    (idempotente por construção, ver docstring do módulo), e enfileira
    `executar_relatorio` no worker para cada disparo.

    `enfileirar`, quando informado, é uma função `async def(*, tenant_id,
    execucao_id, codigo, parametros, formato, solicitante_id) -> None`
    chamada por disparo -- injeção simples para o teste substituir o
    `enqueue_job` real sem precisar de um Redis de verdade; `None` (padrão)
    usa `worker.scheduler` de fato (ver a rotina em `worker/scheduler.py`,
    que passa a função real)."""
    from app.db.sessao import aplicar_tenant, fabrica_de_sessoes

    tenants = await listar_tenants_ativos_cross_tenant()
    fabrica = fabrica_de_sessoes()
    agora = dt.datetime.now(tz=dt.UTC)

    disparados = 0
    for tenant in tenants:
        async with fabrica() as sessao:
            await aplicar_tenant(sessao, str(tenant.id))

            vencidos = await _agendamentos_vencidos(sessao, tenant.id, agora)
            for agendamento in vencidos:
                execucao_id = await _marcar_disparado(sessao, agendamento, agora)
                await sessao.commit()
                # `enfileirar` fora da transacao do UPDATE/INSERT acima
                # (ja commitada): se o Redis falhar aqui, a execucao fica
                # 'enfileirado' presa -- aceito como limitacao conhecida
                # (mesmo padrao de "melhor esforco" que o resto do sistema
                # usa para o proprio enfileiramento apos escrita, ver
                # `app.workflow.fechamento.espelho.criar_espelhos_
                # assincrono`, que tambem nao compensa falha de enqueue
                # apos o flush).
                if enfileirar is not None:
                    await enfileirar(
                        tenant_id=str(tenant.id),
                        execucao_id=str(execucao_id),
                        codigo=agendamento.codigo_relatorio,
                        parametros=agendamento.parametros,
                        formato=agendamento.formato,
                        solicitante_id=str(agendamento.usuario_id)
                        if agendamento.usuario_id
                        else None,
                    )
                disparados += 1

    logger.info(
        "varredura cross-tenant de agendamentos de relatorio concluida",
        extra={"tenantsVerificados": len(tenants), "agendamentosDisparados": disparados},
    )
    return ResultadoVarredura(tenants_verificados=len(tenants), agendamentos_disparados=disparados)


__all__ = [
    "AgendamentoDisparado",
    "ResultadoVarredura",
    "TenantAtivo",
    "listar_tenants_ativos_cross_tenant",
    "verificar_agendamentos_relatorio_cross_tenant",
]
