"""Fumaca de `worker.tarefas.lgpd.expurgo_lgpd` (F14/A3) -- mesmo padrao de
`apps/worker/tests/f11/agendamentos/test_worker_executar_relatorio.py` para
`executar_relatorio`: a logica de negocio (`app.lgpd.expurgo.
aplicar_politicas_vencidas`) ja tem cobertura propria em `apps/api/tests/
f14/lgpd/test_expurgo.py`; este arquivo cobre so a fiacao do wrapper do
worker -- tenant aplicado na sessao propria, `simulacao=True` (padrao) faz
ROLLBACK de verdade sem persistir nada, `simulacao=False` persiste, e o
formato do retorno bate com o que o scheduler/chamador espera.

Entidade escolhida para o cenario: `notificacao` (`_expurgar_notificacao`)
-- a mais simples de semear sem depender de colaborador/vinculo, entre as
tres com implementacao real nesta fase (`biometria`, `sessao`,
`notificacao`)."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

import pytest
import sqlalchemy as sa
from ponto_contracts import Notificacao, PoliticaRetencao, Usuario
from sqlalchemy.ext.asyncio import AsyncSession

from tests.f14.lgpd.conftest import ContextoLgpdWorkerF14

pytestmark = pytest.mark.asyncio


async def _semear_politica_e_notificacao_vencida(
    sessao: AsyncSession, tenant_id: uuid.UUID
) -> uuid.UUID:
    politica = PoliticaRetencao(
        tenant_id=tenant_id,
        entidade="notificacao",
        prazo_dias=1,
        base_legal="politica interna de teste (worker)",
        acao="eliminar",
        ativo=True,
    )
    sessao.add(politica)

    # `ck_notificacoes_destinatario`: usuario_id OU colaborador_id precisa ser
    # nao-nulo -- o mais simples dos dois de semear (sem depender de empresa/
    # unidade/vinculo, que colaborador exigiria).
    usuario = Usuario(
        tenant_id=tenant_id,
        email=f"lgpd-worker-{uuid.uuid4().hex[:8]}@example.com",
        nome_completo="Usuario de teste (expurgo LGPD worker)",
    )
    sessao.add(usuario)
    await sessao.flush()

    notificacao = Notificacao(
        tenant_id=tenant_id,
        usuario_id=usuario.id,
        canal="email",
        evento="teste.evento",
        titulo="Notificacao vencida de teste",
        corpo="corpo de teste",
        criado_em=dt.datetime.now(tz=dt.UTC) - dt.timedelta(days=2),
    )
    sessao.add(notificacao)

    await sessao.commit()
    return notificacao.id


async def _contar_notificacoes(sessao: AsyncSession, tenant_id: uuid.UUID) -> int:
    total = (
        await sessao.execute(
            sa.select(sa.func.count())
            .select_from(Notificacao)
            .where(Notificacao.tenant_id == tenant_id)
        )
    ).scalar_one()
    return int(total)


async def test_simulacao_padrao_avalia_mas_faz_rollback_sem_persistir(
    sessao_worker_f14: AsyncSession,
    contexto_lgpd_worker_f14: ContextoLgpdWorkerF14,
) -> None:
    from worker.tarefas.lgpd import expurgo_lgpd

    tenant_id = contexto_lgpd_worker_f14.tenant_id
    await _semear_politica_e_notificacao_vencida(sessao_worker_f14, tenant_id)

    ctx: dict[str, Any] = {"job_id": "teste-lgpd-simulacao"}
    resultado = await expurgo_lgpd(ctx, tenant_id=str(tenant_id))  # simulacao=True (padrao)

    assert resultado["implementado"] is True
    assert resultado["tenantId"] == str(tenant_id)
    assert resultado["simulacao"] is True
    assert resultado["politicasAvaliadas"] == 1
    assert resultado["resultados"][0]["executado"] is True
    assert resultado["resultados"][0]["registrosAfetados"] == 1

    # ROLLBACK de verdade: a notificacao continua la, e a politica nao
    # avancou `ultima_execucao_em` (a chamada de teste roda numa sessao
    # PROPRIA -- `aplicar_tenant` publica o mesmo tenant para enxergar via RLS).
    await aplicar_tenant_para_leitura(sessao_worker_f14, tenant_id)
    assert await _contar_notificacoes(sessao_worker_f14, tenant_id) == 1


async def test_simulacao_falsa_persiste_e_remove_o_registro_vencido(
    sessao_worker_f14: AsyncSession,
    contexto_lgpd_worker_f14: ContextoLgpdWorkerF14,
) -> None:
    from worker.tarefas.lgpd import expurgo_lgpd

    tenant_id = contexto_lgpd_worker_f14.tenant_id
    await _semear_politica_e_notificacao_vencida(sessao_worker_f14, tenant_id)

    ctx: dict[str, Any] = {"job_id": "teste-lgpd-real"}
    resultado = await expurgo_lgpd(ctx, tenant_id=str(tenant_id), simulacao=False)

    assert resultado["simulacao"] is False
    assert resultado["resultados"][0]["registrosAfetados"] == 1

    await aplicar_tenant_para_leitura(sessao_worker_f14, tenant_id)
    assert await _contar_notificacoes(sessao_worker_f14, tenant_id) == 0


async def aplicar_tenant_para_leitura(sessao: AsyncSession, tenant_id: uuid.UUID) -> None:
    """`expurgo_lgpd` roda numa sessao/engine PROPRIA (`app.db.sessao`,
    engine global do processo) -- a `sessao_worker_f14` do teste precisa
    republicar o tenant apos o `commit()`/ROLLBACK feito por aquela chamada,
    ja que `SET LOCAL` (RLS) so vale dentro da transacao corrente."""
    from tests.f14.lgpd.conftest import aplicar_tenant

    await aplicar_tenant(sessao, tenant_id)
