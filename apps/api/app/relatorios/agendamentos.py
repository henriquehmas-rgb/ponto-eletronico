"""Módulo interno de agendamento de relatório (T11, F11/A3).

`listar_agendamentos`/`criar_agendamento` operam direto sobre
`relatorio_agendamentos` sob RLS -- consumidos pelos dois handlers HTTP de
`app/routers/relatorios.py` (`listarAgendamentosRelatorio`/
`criarAgendamentoRelatorio`, seção "Agendamento -- ownership de A3",
arquivo compartilhado com A1 conforme PCF §5).

`criar_agendamento` valida `cron` com `croniter` (achado de contrato
registrado em `apps/api/pyproject.toml`, bloco F11: o PCF só manda
adicionar `croniter` no worker, mas a validação E o cálculo do primeiro
`proxima_execucao_em` acontecem aqui, na API, no momento da criação) e
recusa `relatorioDefinicaoId` inexistente com `PONTO-REC-001`. Depois da
criação, `worker/scheduler.py::verificar_agendamentos_relatorio` (mesmo
`croniter`, agora no worker) recalcula `proxima_execucao_em` a cada
disparo -- ver módulo irmão `apps/worker/worker/relatorios_agendamentos_
verificacao.py`.

Só as duas operações que o contrato expõe existem (`listarAgendamentos
Relatorio`/`criarAgendamentoRelatorio`); não há `atualizar`/`excluir`
(achado de contrato herdado, PCF §2.8 item 2 -- não invento as rotas).
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from typing import Any
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import sqlalchemy as sa
from croniter import CroniterBadCronError, croniter
from ponto_contracts import RelatorioAgendamento, RelatorioDefinicao
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.erros import ErroDeAplicacao
from app.relatorios.paginacao import (
    CampoOrdenacao,
    codificar_cursor,
    executar_pagina,
    interpretar_ordenar,
    montar_paginacao,
    normalizar_limite,
)
from app.schemas import contrato as esquemas

CODIGO_CORPO_INVALIDO = "PONTO-VAL-001"
CODIGO_RECURSO_NAO_ENCONTRADO = "PONTO-REC-001"
CODIGO_CONFLITO = "PONTO-CONF-001"

#: Padrão da tabela (`relatorio_agendamentos.fuso_horario`, `schema.sql` §16).
FUSO_PADRAO = "America/Sao_Paulo"

_CAMPOS_ORDENACAO: dict[str, CampoOrdenacao] = {
    "proximaExecucaoEm": CampoOrdenacao(
        RelatorioAgendamento.proxima_execucao_em, dt.datetime.fromisoformat
    ),
    "nome": CampoOrdenacao(RelatorioAgendamento.nome, str),
}


def _validar_cron(cron: str) -> None:
    """`PONTO-VAL-001` quando a expressão não é uma expressão cron válida
    (`croniter.is_valid`, a mesma biblioteca que `worker/scheduler.py::
    verificar_agendamentos_relatorio` usa para recalcular depois -- nunca
    duas validações divergentes para o mesmo formato)."""
    if not croniter.is_valid(cron):
        raise ErroDeAplicacao(
            CODIGO_CORPO_INVALIDO, detalhe=f"cron nao e uma expressao cron valida: {cron!r}."
        )


def _resolver_fuso(fuso_horario: str | None) -> ZoneInfo:
    fuso = fuso_horario or FUSO_PADRAO
    try:
        return ZoneInfo(fuso)
    except ZoneInfoNotFoundError as exc:
        raise ErroDeAplicacao(
            CODIGO_CORPO_INVALIDO, detalhe=f"fusoHorario desconhecido: {fuso!r}."
        ) from exc


def calcular_proxima_execucao(
    cron: str, *, fuso_horario: str | None, referencia: dt.datetime | None = None
) -> dt.datetime:
    """Próximo disparo de `cron`, interpretado no fuso indicado (nunca no
    fuso do servidor -- `schema.sql`, comentário de `relatorio_
    agendamentos`). `referencia` é o instante-base (padrão: agora, no fuso
    resolvido); parâmetro exposto para o teste de idempotência da varredura
    do scheduler poder simular "logo depois do disparo anterior" sem
    esperar o relógio real."""
    _validar_cron(cron)
    fuso = _resolver_fuso(fuso_horario)
    base = referencia or dt.datetime.now(tz=fuso)
    if base.tzinfo is None:
        base = base.replace(tzinfo=fuso)
    try:
        proxima: dt.datetime = croniter(cron, base).get_next(dt.datetime)
    except CroniterBadCronError as exc:
        raise ErroDeAplicacao(
            CODIGO_CORPO_INVALIDO, detalhe=f"cron nao e uma expressao cron valida: {cron!r}."
        ) from exc
    return proxima


async def _carregar_definicao(
    sessao: AsyncSession, tenant_id: UUID, relatorio_definicao_id: UUID
) -> RelatorioDefinicao:
    definicao = await sessao.get(RelatorioDefinicao, relatorio_definicao_id)
    if definicao is None or definicao.tenant_id != tenant_id or definicao.excluido_em is not None:
        raise ErroDeAplicacao(
            CODIGO_RECURSO_NAO_ENCONTRADO, detalhe="relatorioDefinicaoId nao encontrado."
        )
    return definicao


async def criar_agendamento(
    sessao: AsyncSession,
    tenant_id: UUID,
    dados: esquemas.RelatorioAgendamentoCriar,
    *,
    usuario_id_solicitante: UUID | None,
) -> RelatorioAgendamento:
    """`POST /v1/relatorios/agendamentos`. `usuarioId` do corpo, quando
    ausente, cai para o sujeito autenticado -- sempre um agendamento tem
    dono, mesmo que o cliente não informe explicitamente."""
    await _carregar_definicao(sessao, tenant_id, dados.relatorio_definicao_id)

    fuso_horario = dados.fuso_horario or FUSO_PADRAO
    proxima_execucao_em = calcular_proxima_execucao(dados.cron, fuso_horario=fuso_horario)
    usuario_id = dados.usuario_id or usuario_id_solicitante

    agendamento = RelatorioAgendamento(
        id=uuid4(),
        tenant_id=tenant_id,
        relatorio_definicao_id=dados.relatorio_definicao_id,
        usuario_id=usuario_id,
        nome=dados.nome,
        parametros=dados.parametros or {},
        formato=_valor(dados.formato) or "pdf",
        cron=dados.cron,
        fuso_horario=fuso_horario,
        canal=_valor(dados.canal) or "email",
        destinatarios=list(dados.destinatarios or []),
        ativo=dados.ativo if dados.ativo is not None else True,
        proxima_execucao_em=proxima_execucao_em,
        criado_por=usuario_id_solicitante,
    )
    sessao.add(agendamento)
    try:
        await sessao.flush()
    except sa.exc.IntegrityError as exc:
        raise ErroDeAplicacao(
            CODIGO_CONFLITO, detalhe="Ja existe um agendamento com este nome neste tenant."
        ) from exc
    return agendamento


async def listar_agendamentos(
    sessao: AsyncSession,
    tenant_id: UUID,
    *,
    relatorio_definicao_id: UUID | None = None,
    usuario_id: UUID | None = None,
    canal: str | None = None,
    ativo: bool | None = None,
    cursor: str | None = None,
    limite: int | None = None,
    ordenar: str | None = None,
) -> tuple[Sequence[RelatorioAgendamento], esquemas.Paginacao]:
    """`GET /v1/relatorios/agendamentos`."""
    ordenacao = interpretar_ordenar(
        ordenar, campos_aceitos=frozenset(_CAMPOS_ORDENACAO), padrao="proximaExecucaoEm"
    )
    limite_efetivo = normalizar_limite(limite)

    consulta = sa.select(RelatorioAgendamento).where(
        RelatorioAgendamento.tenant_id == tenant_id,
        RelatorioAgendamento.excluido_em.is_(None),
    )
    if relatorio_definicao_id is not None:
        consulta = consulta.where(
            RelatorioAgendamento.relatorio_definicao_id == relatorio_definicao_id
        )
    if usuario_id is not None:
        consulta = consulta.where(RelatorioAgendamento.usuario_id == usuario_id)
    if canal is not None:
        consulta = consulta.where(RelatorioAgendamento.canal == canal)
    if ativo is not None:
        consulta = consulta.where(RelatorioAgendamento.ativo == ativo)

    campo = _CAMPOS_ORDENACAO[ordenacao.campo]
    linhas, tem_mais = await executar_pagina(
        sessao,
        consulta,
        ordenacao=ordenacao,
        campo=campo,
        coluna_id=RelatorioAgendamento.id,
        cursor=cursor,
        limite=limite_efetivo,
    )
    atributo = "proxima_execucao_em" if ordenacao.campo == "proximaExecucaoEm" else "nome"
    proximo_cursor = None
    if tem_mais and linhas:
        ultimo = linhas[-1]
        proximo_cursor = codificar_cursor(ordenacao, getattr(ultimo, atributo), ultimo.id)
    paginacao = montar_paginacao(
        proximo_cursor=proximo_cursor, tem_mais=tem_mais, limite=limite_efetivo
    )
    return linhas, paginacao


def _valor(bruto: Any) -> Any:
    """Enum gerado pelo pydantic (`Formato3`/`Canal5`) devolve `.value` --
    mesmo utilitário que `app.workflow.fechamento.espelho._valor` (F10) já
    usa para o mesmo padrão."""
    return bruto.value if hasattr(bruto, "value") else bruto


__all__ = [
    "FUSO_PADRAO",
    "calcular_proxima_execucao",
    "criar_agendamento",
    "listar_agendamentos",
]
