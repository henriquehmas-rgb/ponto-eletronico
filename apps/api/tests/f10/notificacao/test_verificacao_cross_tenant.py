"""Testes de `worker.notificacoes_verificacao.
verificar_notificacoes_pendentes_cross_tenant` (T11) contra o banco real --
critérios de aceite 5 e 11 (idempotência, dois tenants numa única
varredura)."""

from __future__ import annotations

import datetime as dt

import pytest
import sqlalchemy as sa
from ponto_contracts import Notificacao
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.notificacao import mensagens
from tests.f10.notificacao.conftest import (
    ContextoNotificacao,
    aplicar_tenant_teste,
    semear_tenant_minimo,
)


async def _criar_ocorrencia(
    sessao: AsyncSession, contexto: ContextoNotificacao, *, codigo: str, dias_atras: int = 0
) -> None:
    await sessao.execute(
        text(
            "INSERT INTO ocorrencias "
            "(tenant_id, colaborador_id, vinculo_id, data, codigo, severidade, descricao) "
            "VALUES (:tenant_id, :colaborador_id, :vinculo_id, :data, :codigo, 'atencao', "
            "        :descricao)"
        ),
        {
            "tenant_id": contexto.tenant_id,
            "colaborador_id": contexto.colaborador_id,
            "vinculo_id": contexto.vinculo_id,
            "data": (dt.datetime.now(tz=dt.UTC) - dt.timedelta(days=dias_atras)).date(),
            "codigo": codigo,
            "descricao": f"Ocorrência de teste ({codigo}).",
        },
    )


async def _notificacoes(sessao: AsyncSession, tenant_id, evento: str) -> list[Notificacao]:
    await aplicar_tenant_teste(sessao, tenant_id)
    linhas = await sessao.execute(
        sa.select(Notificacao).where(
            Notificacao.tenant_id == tenant_id, Notificacao.evento == evento
        )
    )
    return list(linhas.scalars().all())


@pytest.mark.asyncio
async def test_varredura_notifica_ocorrencia_cross_tenant_dois_tenants(
    sessao_notificacao: AsyncSession,
    contexto_notificacao: ContextoNotificacao,
    ambiente_worker_notificacao: None,
) -> None:
    from worker.notificacoes_verificacao import (
        verificar_notificacoes_pendentes_cross_tenant,
    )

    contexto_b = await semear_tenant_minimo(sessao_notificacao, sufixo="varredurab")
    await aplicar_tenant_teste(sessao_notificacao, contexto_notificacao.tenant_id)
    await _criar_ocorrencia(sessao_notificacao, contexto_notificacao, codigo="jornada_excedida")
    await aplicar_tenant_teste(sessao_notificacao, contexto_b.tenant_id)
    await _criar_ocorrencia(sessao_notificacao, contexto_b, codigo="sem_marcacao")
    await sessao_notificacao.commit()

    resultado = await verificar_notificacoes_pendentes_cross_tenant()
    assert resultado.tenants_verificados >= 2
    assert resultado.ocorrencias_notificadas >= 2
    assert contexto_notificacao.tenant_id in resultado.tenant_ids
    assert contexto_b.tenant_id in resultado.tenant_ids

    notificacoes_a = await _notificacoes(
        sessao_notificacao, contexto_notificacao.tenant_id, mensagens.NOME_OCORRENCIA_ABERTA
    )
    notificacoes_b = await _notificacoes(
        sessao_notificacao, contexto_b.tenant_id, mensagens.NOME_OCORRENCIA_ABERTA
    )
    assert len(notificacoes_a) >= 1
    assert len(notificacoes_b) >= 1


@pytest.mark.asyncio
async def test_varredura_e_idempotente_nao_duplica_notificacao(
    sessao_notificacao: AsyncSession,
    contexto_notificacao: ContextoNotificacao,
    ambiente_worker_notificacao: None,
) -> None:
    from worker.notificacoes_verificacao import (
        verificar_notificacoes_pendentes_cross_tenant,
    )

    await _criar_ocorrencia(sessao_notificacao, contexto_notificacao, codigo="banco_vencendo")
    await sessao_notificacao.commit()

    primeira = await verificar_notificacoes_pendentes_cross_tenant()
    segunda = await verificar_notificacoes_pendentes_cross_tenant()

    assert primeira.ocorrencias_notificadas >= 1
    # Sem ocorrencia NOVA entre as duas chamadas, a segunda nao deveria
    # notificar de novo a MESMA ocorrencia (NOT EXISTS por entidade+evento).
    assert segunda.ocorrencias_notificadas == 0

    notificacoes = await _notificacoes(
        sessao_notificacao, contexto_notificacao.tenant_id, mensagens.NOME_OCORRENCIA_ABERTA
    )
    # Uma linha por canal aplicavel (so in_app para ocorrencia.aberta), uma
    # vez so -- nunca duplicada pela segunda varredura.
    assert len(notificacoes) == 1


@pytest.mark.asyncio
async def test_varredura_ignora_codigo_de_ocorrencia_fora_do_escopo_desta_rotina(
    sessao_notificacao: AsyncSession,
    contexto_notificacao: ContextoNotificacao,
    ambiente_worker_notificacao: None,
) -> None:
    from worker.notificacoes_verificacao import (
        verificar_notificacoes_pendentes_cross_tenant,
    )

    # `marcacao_impar` nao esta na lista coberta (PCF §2.10: so
    # jornada_excedida/sem_marcacao/banco_vencendo).
    await _criar_ocorrencia(sessao_notificacao, contexto_notificacao, codigo="marcacao_impar")
    await sessao_notificacao.commit()

    await verificar_notificacoes_pendentes_cross_tenant()

    notificacoes = await _notificacoes(
        sessao_notificacao, contexto_notificacao.tenant_id, mensagens.NOME_OCORRENCIA_ABERTA
    )
    assert notificacoes == []


@pytest.mark.asyncio
async def test_varredura_notifica_aprovador_de_solicitacao_com_prazo_vencido(
    sessao_notificacao: AsyncSession,
    contexto_notificacao: ContextoNotificacao,
    ambiente_worker_notificacao: None,
) -> None:
    from worker.notificacoes_verificacao import (
        verificar_notificacoes_pendentes_cross_tenant,
    )

    # A fixture ja semeia uma Aprovacao pendente com prazo_em no passado.
    resultado = await verificar_notificacoes_pendentes_cross_tenant()
    assert resultado.pendencias_notificadas >= 1

    notificacoes = await _notificacoes(
        sessao_notificacao, contexto_notificacao.tenant_id, mensagens.NOME_SOLICITACAO_PENDENTE
    )
    assert any(
        linha.usuario_id == contexto_notificacao.aprovador_usuario_id for linha in notificacoes
    )

    # Idempotencia tambem vale para o lembrete de pendencia.
    resultado_2 = await verificar_notificacoes_pendentes_cross_tenant()
    assert resultado_2.pendencias_notificadas == 0
