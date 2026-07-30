"""Testes de `app.notificacao.preferencias` contra o banco real (T10)."""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.notificacao import preferencias
from tests.f10.notificacao.conftest import ContextoNotificacao


@pytest.mark.asyncio
async def test_sem_preferencia_gravada_e_habilitado_por_padrao(
    sessao_notificacao: AsyncSession, contexto_notificacao: ContextoNotificacao
) -> None:
    habilitado = await preferencias.esta_habilitado(
        sessao_notificacao,
        contexto_notificacao.tenant_id,
        contexto_notificacao.usuario_id,
        "ajuste.aprovado",
        "push",
    )
    assert habilitado is True


@pytest.mark.asyncio
async def test_preferencia_especifica_desabilitada(
    sessao_notificacao: AsyncSession, contexto_notificacao: ContextoNotificacao
) -> None:
    await preferencias.definir_preferencia(
        sessao_notificacao,
        contexto_notificacao.tenant_id,
        contexto_notificacao.usuario_id,
        "ajuste.aprovado",
        "push",
        habilitado=False,
    )
    habilitado = await preferencias.esta_habilitado(
        sessao_notificacao,
        contexto_notificacao.tenant_id,
        contexto_notificacao.usuario_id,
        "ajuste.aprovado",
        "push",
    )
    assert habilitado is False
    # Outro canal, mesmo evento, continua no padrao (habilitado).
    ainda_habilitado = await preferencias.esta_habilitado(
        sessao_notificacao,
        contexto_notificacao.tenant_id,
        contexto_notificacao.usuario_id,
        "ajuste.aprovado",
        "email",
    )
    assert ainda_habilitado is True


@pytest.mark.asyncio
async def test_preferencia_coringa_desabilita_todos_os_eventos_daquele_canal(
    sessao_notificacao: AsyncSession, contexto_notificacao: ContextoNotificacao
) -> None:
    await preferencias.definir_preferencia(
        sessao_notificacao,
        contexto_notificacao.tenant_id,
        contexto_notificacao.usuario_id,
        preferencias.CORINGA_EVENTO,
        "email",
        habilitado=False,
    )
    habilitado = await preferencias.esta_habilitado(
        sessao_notificacao,
        contexto_notificacao.tenant_id,
        contexto_notificacao.usuario_id,
        "ajuste.aprovado",
        "email",
    )
    assert habilitado is False


@pytest.mark.asyncio
async def test_preferencia_especifica_tem_prioridade_sobre_coringa(
    sessao_notificacao: AsyncSession, contexto_notificacao: ContextoNotificacao
) -> None:
    await preferencias.definir_preferencia(
        sessao_notificacao,
        contexto_notificacao.tenant_id,
        contexto_notificacao.usuario_id,
        preferencias.CORINGA_EVENTO,
        "email",
        habilitado=False,
    )
    await preferencias.definir_preferencia(
        sessao_notificacao,
        contexto_notificacao.tenant_id,
        contexto_notificacao.usuario_id,
        "ajuste.aprovado",
        "email",
        habilitado=True,
    )
    habilitado = await preferencias.esta_habilitado(
        sessao_notificacao,
        contexto_notificacao.tenant_id,
        contexto_notificacao.usuario_id,
        "ajuste.aprovado",
        "email",
    )
    assert habilitado is True


@pytest.mark.asyncio
async def test_janela_de_silencio_gravada_e_lida(
    sessao_notificacao: AsyncSession, contexto_notificacao: ContextoNotificacao
) -> None:
    await preferencias.definir_preferencia(
        sessao_notificacao,
        contexto_notificacao.tenant_id,
        contexto_notificacao.usuario_id,
        "ajuste.aprovado",
        "push",
        habilitado=True,
        janela_inicio=dt.time(8, 0),
        janela_fim=dt.time(18, 0),
    )
    inicio, fim = await preferencias.obter_janela_silencio(
        sessao_notificacao,
        contexto_notificacao.tenant_id,
        contexto_notificacao.usuario_id,
        "ajuste.aprovado",
        "push",
    )
    assert inicio == dt.time(8, 0)
    assert fim == dt.time(18, 0)


@pytest.mark.asyncio
async def test_definir_preferencia_e_upsert(
    sessao_notificacao: AsyncSession, contexto_notificacao: ContextoNotificacao
) -> None:
    primeira = await preferencias.definir_preferencia(
        sessao_notificacao,
        contexto_notificacao.tenant_id,
        contexto_notificacao.usuario_id,
        "ajuste.aprovado",
        "push",
        habilitado=True,
    )
    segunda = await preferencias.definir_preferencia(
        sessao_notificacao,
        contexto_notificacao.tenant_id,
        contexto_notificacao.usuario_id,
        "ajuste.aprovado",
        "push",
        habilitado=False,
    )
    assert primeira.id == segunda.id
    habilitado = await preferencias.esta_habilitado(
        sessao_notificacao,
        contexto_notificacao.tenant_id,
        contexto_notificacao.usuario_id,
        "ajuste.aprovado",
        "push",
    )
    assert habilitado is False
