"""Testes de `worker.tarefas.notificacoes.processar_fila_notificacoes`
(T11) contra o banco real -- critério de aceite 5, parte "status avança
para enviada"."""

from __future__ import annotations

import datetime as dt

import pytest
import sqlalchemy as sa
from ponto_contracts import Notificacao
from sqlalchemy.ext.asyncio import AsyncSession

from tests.f10.notificacao.conftest import ContextoNotificacao, aplicar_tenant_teste


async def _criar_notificacao_pendente(
    sessao: AsyncSession,
    contexto: ContextoNotificacao,
    *,
    canal: str,
    agendada_para: dt.datetime | None = None,
) -> Notificacao:
    notificacao = Notificacao(
        tenant_id=contexto.tenant_id,
        usuario_id=contexto.usuario_id,
        canal=canal,
        evento="ajuste.aprovado",
        titulo="Título de teste",
        corpo="Corpo de teste",
        agendada_para=agendada_para,
    )
    sessao.add(notificacao)
    await sessao.flush()
    return notificacao


@pytest.mark.asyncio
async def test_drena_notificacoes_pendentes_e_avanca_status(
    sessao_notificacao: AsyncSession,
    contexto_notificacao: ContextoNotificacao,
    ambiente_worker_notificacao: None,
) -> None:
    from worker.tarefas.notificacoes import processar_fila_notificacoes

    await _criar_notificacao_pendente(sessao_notificacao, contexto_notificacao, canal="push")
    await _criar_notificacao_pendente(sessao_notificacao, contexto_notificacao, canal="email")
    await _criar_notificacao_pendente(sessao_notificacao, contexto_notificacao, canal="in_app")
    await sessao_notificacao.commit()

    resultado = await processar_fila_notificacoes(
        {"job_id": "teste"}, tenant_id=str(contexto_notificacao.tenant_id)
    )
    assert resultado["implementado"] is True
    assert resultado["encontradas"] == 3
    assert resultado["enviadas"] == 3
    assert resultado["falhadas"] == 0

    await aplicar_tenant_teste(sessao_notificacao, contexto_notificacao.tenant_id)
    linhas = await sessao_notificacao.execute(
        sa.select(Notificacao).where(Notificacao.tenant_id == contexto_notificacao.tenant_id)
    )
    for linha in linhas.scalars().all():
        assert linha.status == "enviada"
        assert linha.enviada_em is not None
        assert linha.provedor is not None
        assert linha.tentativas == 1


@pytest.mark.asyncio
async def test_notificacao_agendada_no_futuro_nao_e_drenada(
    sessao_notificacao: AsyncSession,
    contexto_notificacao: ContextoNotificacao,
    ambiente_worker_notificacao: None,
) -> None:
    from worker.tarefas.notificacoes import processar_fila_notificacoes

    futuro = dt.datetime.now(tz=dt.UTC) + dt.timedelta(hours=2)
    await _criar_notificacao_pendente(
        sessao_notificacao, contexto_notificacao, canal="push", agendada_para=futuro
    )
    await sessao_notificacao.commit()

    resultado = await processar_fila_notificacoes(
        {"job_id": "teste"}, tenant_id=str(contexto_notificacao.tenant_id)
    )
    assert resultado["encontradas"] == 0

    await aplicar_tenant_teste(sessao_notificacao, contexto_notificacao.tenant_id)
    linhas = await sessao_notificacao.execute(
        sa.select(Notificacao).where(Notificacao.tenant_id == contexto_notificacao.tenant_id)
    )
    linha = linhas.scalar_one()
    assert linha.status == "pendente"


@pytest.mark.asyncio
async def test_notificacao_agendada_no_passado_e_drenada(
    sessao_notificacao: AsyncSession,
    contexto_notificacao: ContextoNotificacao,
    ambiente_worker_notificacao: None,
) -> None:
    from worker.tarefas.notificacoes import processar_fila_notificacoes

    passado = dt.datetime.now(tz=dt.UTC) - dt.timedelta(minutes=5)
    await _criar_notificacao_pendente(
        sessao_notificacao, contexto_notificacao, canal="push", agendada_para=passado
    )
    await sessao_notificacao.commit()

    resultado = await processar_fila_notificacoes(
        {"job_id": "teste"}, tenant_id=str(contexto_notificacao.tenant_id)
    )
    assert resultado["encontradas"] == 1
    assert resultado["enviadas"] == 1


@pytest.mark.asyncio
async def test_canal_sem_adaptador_fica_retido_com_erro(
    sessao_notificacao: AsyncSession,
    contexto_notificacao: ContextoNotificacao,
    ambiente_worker_notificacao: None,
) -> None:
    from worker.tarefas.notificacoes import processar_fila_notificacoes

    # `sms` nao tem adaptador registrado nesta fase (PCF §2.8): a linha
    # precisa ficar retida com erro, nunca finge sucesso.
    notificacao = Notificacao(
        tenant_id=contexto_notificacao.tenant_id,
        usuario_id=contexto_notificacao.usuario_id,
        canal="sms",
        evento="ajuste.aprovado",
        titulo="Título de teste",
        corpo="Corpo de teste",
    )
    sessao_notificacao.add(notificacao)
    await sessao_notificacao.commit()

    resultado = await processar_fila_notificacoes(
        {"job_id": "teste"}, tenant_id=str(contexto_notificacao.tenant_id)
    )
    assert resultado["semAdaptador"] == 1
    assert resultado["enviadas"] == 0

    await aplicar_tenant_teste(sessao_notificacao, contexto_notificacao.tenant_id)
    linhas = await sessao_notificacao.execute(
        sa.select(Notificacao).where(Notificacao.tenant_id == contexto_notificacao.tenant_id)
    )
    linha = linhas.scalar_one()
    assert linha.status == "pendente"
    assert linha.erro is not None
