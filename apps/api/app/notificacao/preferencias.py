"""Preferência de notificação por usuário, evento e canal (T10, A3).

Sem rota HTTP nesta fase: não existe operação no contrato para isto ainda
(achado de contrato, PCF F10 §2.7 item 1 -- `workflow.notificacoes` só tem
`ler`/`criar` semeadas em `CATALOGO_PERMISSOES`, nenhuma operação de
`openapi.yaml` as usa). Este módulo é só a lógica interna, pronta para o dia
em que o endpoint existir; `app.notificacao.motor` é quem a consome hoje.

Ausência de linha em `notificacao_preferencias` significa "usar o padrão do
tenant" (comentário da própria coluna em `schema.sql`) -- este sistema ainda
não tem uma tabela de configuração de notificação por tenant (isso não é
desta fase), então o padrão é SEMPRE habilitado: ausência de configuração
nunca silencia uma notificação por omissão.
"""

from __future__ import annotations

import datetime as dt
from uuid import UUID

import sqlalchemy as sa
from ponto_contracts import NotificacaoPreferencia
from sqlalchemy.ext.asyncio import AsyncSession

#: Coringa que vale para qualquer evento sem linha específica
#: (`notificacao_preferencias.evento`, comentário da coluna em `schema.sql`:
#: "Codigo do evento ou o coringa * para valer em todos").
CORINGA_EVENTO = "*"


async def _buscar_preferencia(
    sessao: AsyncSession, tenant_id: UUID, usuario_id: UUID, evento: str, canal: str
) -> NotificacaoPreferencia | None:
    """A preferência específica do par `evento`+`canal` tem prioridade sobre
    o coringa `*`+`canal`; sem nenhuma das duas, devolve `None`."""
    linhas = await sessao.execute(
        sa.select(NotificacaoPreferencia).where(
            NotificacaoPreferencia.tenant_id == tenant_id,
            NotificacaoPreferencia.usuario_id == usuario_id,
            NotificacaoPreferencia.canal == canal,
            NotificacaoPreferencia.evento.in_((evento, CORINGA_EVENTO)),
        )
    )
    encontradas = {p.evento: p for p in linhas.scalars().all()}
    return encontradas.get(evento) or encontradas.get(CORINGA_EVENTO)


async def esta_habilitado(
    sessao: AsyncSession, tenant_id: UUID, usuario_id: UUID, evento: str, canal: str
) -> bool:
    """Verdadeiro quando o usuário aceita este evento neste canal.

    Ausência de linha (nem específica, nem coringa) = padrão do tenant
    habilitado (ver docstring do módulo).
    """
    preferencia = await _buscar_preferencia(sessao, tenant_id, usuario_id, evento, canal)
    if preferencia is None:
        return True
    return bool(preferencia.habilitado)


async def obter_janela_silencio(
    sessao: AsyncSession, tenant_id: UUID, usuario_id: UUID, evento: str, canal: str
) -> tuple[dt.time | None, dt.time | None]:
    """`(janela_inicio, janela_fim)` da preferência mais específica
    encontrada, ou `(None, None)` quando não há janela configurada (sempre
    pode notificar, a qualquer hora)."""
    preferencia = await _buscar_preferencia(sessao, tenant_id, usuario_id, evento, canal)
    if preferencia is None:
        return None, None
    return preferencia.janela_inicio, preferencia.janela_fim


def dentro_da_janela(agora: dt.time, inicio: dt.time | None, fim: dt.time | None) -> bool:
    """Verdadeiro quando `agora` (hora civil, sem fuso -- já resolvida pelo
    chamador) está dentro de `[inicio, fim]`.

    Sem os dois limites, não há janela de silêncio configurada: sempre
    dentro. Quando `inicio > fim`, a janela atravessa a meia-noite (por
    exemplo `22:00`-`06:00`) -- tratada como a união dos dois trechos do
    relógio, não como intervalo vazio.
    """
    if inicio is None or fim is None:
        return True
    if inicio <= fim:
        return inicio <= agora <= fim
    return agora >= inicio or agora <= fim


def proxima_janela(agora: dt.datetime, inicio: dt.time) -> dt.datetime:
    """Próximo instante em que `inicio` ocorre a partir de `agora` -- hoje,
    se o horário ainda não passou; amanhã, caso contrário. Preserva o fuso
    (`tzinfo`) de `agora`."""
    candidato = agora.replace(
        hour=inicio.hour, minute=inicio.minute, second=inicio.second, microsecond=0
    )
    if candidato <= agora:
        candidato += dt.timedelta(days=1)
    return candidato


async def _buscar_preferencia_exata(
    sessao: AsyncSession, tenant_id: UUID, usuario_id: UUID, evento: str, canal: str
) -> NotificacaoPreferencia | None:
    linha = await sessao.execute(
        sa.select(NotificacaoPreferencia).where(
            NotificacaoPreferencia.tenant_id == tenant_id,
            NotificacaoPreferencia.usuario_id == usuario_id,
            NotificacaoPreferencia.evento == evento,
            NotificacaoPreferencia.canal == canal,
        )
    )
    return linha.scalar_one_or_none()


async def definir_preferencia(
    sessao: AsyncSession,
    tenant_id: UUID,
    usuario_id: UUID,
    evento: str,
    canal: str,
    *,
    habilitado: bool = True,
    janela_inicio: dt.time | None = None,
    janela_fim: dt.time | None = None,
) -> NotificacaoPreferencia:
    """Grava (upsert por `evento`+`canal`+`usuario_id`) a preferência.

    Sem rota HTTP nesta fase (ver docstring do módulo) -- usada hoje só por
    teste e ficará pronta para uma futura tela de preferências sem precisar
    mudar de forma.
    """
    existente = await _buscar_preferencia_exata(sessao, tenant_id, usuario_id, evento, canal)
    if existente is not None:
        existente.habilitado = habilitado
        existente.janela_inicio = janela_inicio
        existente.janela_fim = janela_fim
        await sessao.flush()
        return existente
    nova = NotificacaoPreferencia(
        tenant_id=tenant_id,
        usuario_id=usuario_id,
        evento=evento,
        canal=canal,
        habilitado=habilitado,
        janela_inicio=janela_inicio,
        janela_fim=janela_fim,
    )
    sessao.add(nova)
    await sessao.flush()
    return nova


__all__ = [
    "CORINGA_EVENTO",
    "definir_preferencia",
    "dentro_da_janela",
    "esta_habilitado",
    "obter_janela_silencio",
    "proxima_janela",
]
