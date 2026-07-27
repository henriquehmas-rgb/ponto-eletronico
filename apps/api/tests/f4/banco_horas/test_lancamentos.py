"""Testes de `app.apuracao.banco_horas.lancamentos` (T6): cadeia de hash,
consistencia saldo/soma, consumo FIFO/LIFO e imutabilidade do extrato.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
import sqlalchemy as sa
from ponto_contracts import BhConta, BhLancamento
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.apuracao.banco_horas import contas as contas_servico
from app.apuracao.banco_horas import lancamentos as servico
from app.apuracao.banco_horas import politicas as politicas_servico
from app.core.erros import ErroDeAplicacao
from app.schemas import contrato as esquemas
from tests.f4.banco_horas.conftest import ContextoBancoHoras


@pytest.mark.asyncio
async def test_cadeia_de_hash_encadeia_lancamentos(
    sessao_banco_horas: AsyncSession, contexto_banco_horas: ContextoBancoHoras
) -> None:
    primeiro = await servico.lancar(
        sessao_banco_horas,
        tenant_id=contexto_banco_horas.tenant_id,
        bh_conta_id=contexto_banco_horas.bh_conta_id,
        tipo="credito",
        origem="apuracao",
        minutos=120,
        data_competencia=dt.date(2026, 1, 5),
        descricao="Primeiro credito",
        vence_em=dt.date(2026, 6, 30),
    )
    segundo = await servico.lancar(
        sessao_banco_horas,
        tenant_id=contexto_banco_horas.tenant_id,
        bh_conta_id=contexto_banco_horas.bh_conta_id,
        tipo="credito",
        origem="apuracao",
        minutos=60,
        data_competencia=dt.date(2026, 1, 6),
        descricao="Segundo credito",
        vence_em=dt.date(2026, 6, 30),
    )
    assert primeiro.hash_anterior is None
    assert segundo.hash_anterior == primeiro.hash_registro
    assert segundo.sequencia == primeiro.sequencia + 1
    assert primeiro.hash_registro != segundo.hash_registro


@pytest.mark.asyncio
async def test_soma_lancamentos_bate_com_saldo_da_conta(
    sessao_banco_horas: AsyncSession, contexto_banco_horas: ContextoBancoHoras
) -> None:
    await servico.lancar(
        sessao_banco_horas,
        tenant_id=contexto_banco_horas.tenant_id,
        bh_conta_id=contexto_banco_horas.bh_conta_id,
        tipo="credito",
        origem="apuracao",
        minutos=480,
        data_competencia=dt.date(2026, 1, 5),
        descricao="Credito do dia",
        vence_em=dt.date(2026, 6, 30),
    )
    await servico.lancar(
        sessao_banco_horas,
        tenant_id=contexto_banco_horas.tenant_id,
        bh_conta_id=contexto_banco_horas.bh_conta_id,
        tipo="debito",
        origem="apuracao",
        minutos=-100,
        data_competencia=dt.date(2026, 1, 6),
        descricao="Debito de falta",
    )
    await servico.lancar(
        sessao_banco_horas,
        tenant_id=contexto_banco_horas.tenant_id,
        bh_conta_id=contexto_banco_horas.bh_conta_id,
        tipo="credito",
        origem="apuracao",
        minutos=50,
        data_competencia=dt.date(2026, 1, 7),
        descricao="Outro credito",
        vence_em=dt.date(2026, 6, 30),
    )

    soma = await sessao_banco_horas.execute(
        select(sa.func.coalesce(sa.func.sum(BhLancamento.minutos_equivalentes), 0)).where(
            BhLancamento.tenant_id == contexto_banco_horas.tenant_id,
            BhLancamento.bh_conta_id == contexto_banco_horas.bh_conta_id,
        )
    )
    conta = await sessao_banco_horas.get(BhConta, contexto_banco_horas.bh_conta_id)
    assert conta is not None
    assert soma.scalar_one() == conta.saldo_atual_minutos == 430


async def _criar_conta_com_metodo(
    sessao: AsyncSession, contexto: ContextoBancoHoras, *, metodo_consumo: str, sufixo: str
):
    politica = await politicas_servico.criar_politica_banco_horas(
        sessao,
        contexto.tenant_id,
        esquemas.BhPoliticaCriar(
            empresaId=contexto.empresa_id,
            codigo=f"POL-{sufixo}",
            nome=f"Politica {sufixo}",
            regime=esquemas.Regime.especial,
            periodoMeses=6,
            metodoConsumo=esquemas.MetodoConsumo(metodo_consumo),
            vigenciaInicio=dt.date(2026, 1, 1),
        ),
    )
    conta = await contas_servico.criar_conta_banco_horas(
        sessao,
        contexto.tenant_id,
        esquemas.BhContaCriar(
            vinculoId=contexto.vinculo_id,
            bhPoliticaId=politica.id,
            codigo=f"conta-{sufixo}",
            periodoInicio=dt.date(2026, 1, 1),
        ),
    )
    await sessao.flush()
    return conta


@pytest.mark.asyncio
async def test_consumo_fifo_consome_credito_mais_proximo_do_vencimento_primeiro(
    sessao_banco_horas: AsyncSession, contexto_banco_horas: ContextoBancoHoras
) -> None:
    conta = await _criar_conta_com_metodo(
        sessao_banco_horas, contexto_banco_horas, metodo_consumo="fifo", sufixo="fifo"
    )
    credito_a = await servico.lancar(
        sessao_banco_horas,
        tenant_id=contexto_banco_horas.tenant_id,
        bh_conta_id=conta.id,
        tipo="credito",
        origem="apuracao",
        minutos=60,
        data_competencia=dt.date(2026, 1, 1),
        descricao="Credito A (vence primeiro)",
        vence_em=dt.date(2026, 2, 1),
    )
    credito_b = await servico.lancar(
        sessao_banco_horas,
        tenant_id=contexto_banco_horas.tenant_id,
        bh_conta_id=conta.id,
        tipo="credito",
        origem="apuracao",
        minutos=60,
        data_competencia=dt.date(2026, 1, 2),
        descricao="Credito B (vence no meio)",
        vence_em=dt.date(2026, 3, 1),
    )
    credito_c = await servico.lancar(
        sessao_banco_horas,
        tenant_id=contexto_banco_horas.tenant_id,
        bh_conta_id=conta.id,
        tipo="credito",
        origem="apuracao",
        minutos=60,
        data_competencia=dt.date(2026, 1, 3),
        descricao="Credito C (vence por ultimo)",
        vence_em=dt.date(2026, 4, 1),
    )

    await servico.lancar(
        sessao_banco_horas,
        tenant_id=contexto_banco_horas.tenant_id,
        bh_conta_id=conta.id,
        tipo="debito",
        origem="apuracao",
        minutos=-90,
        data_competencia=dt.date(2026, 1, 10),
        descricao="Debito de falta",
    )

    await sessao_banco_horas.refresh(credito_a)
    await sessao_banco_horas.refresh(credito_b)
    await sessao_banco_horas.refresh(credito_c)
    assert credito_a.consumido_minutos == 60  # esgotado primeiro (vence primeiro)
    assert credito_b.consumido_minutos == 30  # parcialmente consumido
    assert credito_c.consumido_minutos == 0  # intocado


@pytest.mark.asyncio
async def test_consumo_lifo_consome_credito_mais_distante_do_vencimento_primeiro(
    sessao_banco_horas: AsyncSession, contexto_banco_horas: ContextoBancoHoras
) -> None:
    conta = await _criar_conta_com_metodo(
        sessao_banco_horas, contexto_banco_horas, metodo_consumo="lifo", sufixo="lifo"
    )
    credito_a = await servico.lancar(
        sessao_banco_horas,
        tenant_id=contexto_banco_horas.tenant_id,
        bh_conta_id=conta.id,
        tipo="credito",
        origem="apuracao",
        minutos=60,
        data_competencia=dt.date(2026, 1, 1),
        descricao="Credito A (vence primeiro)",
        vence_em=dt.date(2026, 2, 1),
    )
    credito_b = await servico.lancar(
        sessao_banco_horas,
        tenant_id=contexto_banco_horas.tenant_id,
        bh_conta_id=conta.id,
        tipo="credito",
        origem="apuracao",
        minutos=60,
        data_competencia=dt.date(2026, 1, 2),
        descricao="Credito B (vence no meio)",
        vence_em=dt.date(2026, 3, 1),
    )
    credito_c = await servico.lancar(
        sessao_banco_horas,
        tenant_id=contexto_banco_horas.tenant_id,
        bh_conta_id=conta.id,
        tipo="credito",
        origem="apuracao",
        minutos=60,
        data_competencia=dt.date(2026, 1, 3),
        descricao="Credito C (vence por ultimo)",
        vence_em=dt.date(2026, 4, 1),
    )

    await servico.lancar(
        sessao_banco_horas,
        tenant_id=contexto_banco_horas.tenant_id,
        bh_conta_id=conta.id,
        tipo="debito",
        origem="apuracao",
        minutos=-90,
        data_competencia=dt.date(2026, 1, 10),
        descricao="Debito de falta",
    )

    await sessao_banco_horas.refresh(credito_a)
    await sessao_banco_horas.refresh(credito_b)
    await sessao_banco_horas.refresh(credito_c)
    assert credito_c.consumido_minutos == 60  # LIFO: mais distante do vencimento esgota primeiro
    assert credito_b.consumido_minutos == 30
    assert credito_a.consumido_minutos == 0  # intocado


@pytest.mark.asyncio
async def test_update_direto_fora_de_consumido_minutos_falha_42501(
    sessao_banco_horas: AsyncSession, contexto_banco_horas: ContextoBancoHoras
) -> None:
    lancamento = await servico.lancar(
        sessao_banco_horas,
        tenant_id=contexto_banco_horas.tenant_id,
        bh_conta_id=contexto_banco_horas.bh_conta_id,
        tipo="credito",
        origem="apuracao",
        minutos=100,
        data_competencia=dt.date(2026, 1, 5),
        descricao="Credito imutavel",
    )
    await sessao_banco_horas.flush()

    with pytest.raises(DBAPIError) as excinfo:
        await sessao_banco_horas.execute(
            text("UPDATE bh_lancamentos SET descricao = 'alterado' WHERE id = :id"),
            {"id": lancamento.id},
        )
    assert getattr(excinfo.value.orig, "sqlstate", None) == "42501"
    await sessao_banco_horas.rollback()


@pytest.mark.asyncio
async def test_delete_em_bh_lancamentos_falha_42501(
    sessao_banco_horas: AsyncSession, contexto_banco_horas: ContextoBancoHoras
) -> None:
    lancamento = await servico.lancar(
        sessao_banco_horas,
        tenant_id=contexto_banco_horas.tenant_id,
        bh_conta_id=contexto_banco_horas.bh_conta_id,
        tipo="credito",
        origem="apuracao",
        minutos=100,
        data_competencia=dt.date(2026, 1, 5),
        descricao="Credito que nunca sai",
    )
    await sessao_banco_horas.flush()

    with pytest.raises(DBAPIError) as excinfo:
        await sessao_banco_horas.execute(
            text("DELETE FROM bh_lancamentos WHERE id = :id"), {"id": lancamento.id}
        )
    assert getattr(excinfo.value.orig, "sqlstate", None) == "42501"
    await sessao_banco_horas.rollback()


@pytest.mark.asyncio
async def test_update_de_consumido_minutos_e_permitido(
    sessao_banco_horas: AsyncSession, contexto_banco_horas: ContextoBancoHoras
) -> None:
    """Evidencia positiva, espelhando a negativa acima: a UNICA excecao que
    `fn_bh_lancamento_imutavel()` permite realmente funciona."""
    lancamento = await servico.lancar(
        sessao_banco_horas,
        tenant_id=contexto_banco_horas.tenant_id,
        bh_conta_id=contexto_banco_horas.bh_conta_id,
        tipo="credito",
        origem="apuracao",
        minutos=100,
        data_competencia=dt.date(2026, 1, 5),
        descricao="Credito consumivel",
    )
    await sessao_banco_horas.flush()

    await sessao_banco_horas.execute(
        text("UPDATE bh_lancamentos SET consumido_minutos = 40 WHERE id = :id"),
        {"id": lancamento.id},
    )
    await sessao_banco_horas.refresh(lancamento)
    assert lancamento.consumido_minutos == 40


@pytest.mark.asyncio
async def test_lancar_com_minutos_zero_e_recusado(
    sessao_banco_horas: AsyncSession, contexto_banco_horas: ContextoBancoHoras
) -> None:
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.lancar(
            sessao_banco_horas,
            tenant_id=contexto_banco_horas.tenant_id,
            bh_conta_id=contexto_banco_horas.bh_conta_id,
            tipo="credito",
            origem="apuracao",
            minutos=0,
            data_competencia=dt.date(2026, 1, 5),
            descricao="Zero",
        )
    assert excinfo.value.codigo == "PONTO-VAL-001"


@pytest.mark.asyncio
async def test_lancar_em_conta_inexistente_e_rec_001(
    sessao_banco_horas: AsyncSession, contexto_banco_horas: ContextoBancoHoras
) -> None:
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.lancar(
            sessao_banco_horas,
            tenant_id=contexto_banco_horas.tenant_id,
            bh_conta_id=uuid.uuid4(),
            tipo="credito",
            origem="apuracao",
            minutos=10,
            data_competencia=dt.date(2026, 1, 5),
            descricao="Conta inexistente",
        )
    assert excinfo.value.codigo == "PONTO-REC-001"


@pytest.mark.asyncio
async def test_lancar_em_conta_encerrada_falha_bh_004(
    sessao_banco_horas: AsyncSession, contexto_banco_horas: ContextoBancoHoras
) -> None:
    conta = await sessao_banco_horas.get(BhConta, contexto_banco_horas.bh_conta_id)
    assert conta is not None
    conta.status = "encerrada"
    await sessao_banco_horas.flush()

    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.lancar(
            sessao_banco_horas,
            tenant_id=contexto_banco_horas.tenant_id,
            bh_conta_id=contexto_banco_horas.bh_conta_id,
            tipo="credito",
            origem="apuracao",
            minutos=10,
            data_competencia=dt.date(2026, 1, 5),
            descricao="Conta encerrada",
        )
    assert excinfo.value.codigo == "PONTO-BH-004"


@pytest.mark.asyncio
async def test_debito_alem_do_teto_negativo_falha_bh_002(
    sessao_banco_horas: AsyncSession, contexto_banco_horas: ContextoBancoHoras
) -> None:
    politica = await politicas_servico.criar_politica_banco_horas(
        sessao_banco_horas,
        contexto_banco_horas.tenant_id,
        esquemas.BhPoliticaCriar(
            empresaId=contexto_banco_horas.empresa_id,
            codigo="POL-TETO-NEG",
            nome="Politica com teto negativo",
            regime=esquemas.Regime.especial,
            periodoMeses=6,
            vigenciaInicio=dt.date(2026, 1, 1),
            tetoNegativoMinutos=50,
        ),
    )
    conta = await contas_servico.criar_conta_banco_horas(
        sessao_banco_horas,
        contexto_banco_horas.tenant_id,
        esquemas.BhContaCriar(
            vinculoId=contexto_banco_horas.vinculo_id,
            bhPoliticaId=politica.id,
            codigo="conta-teto-neg",
            periodoInicio=dt.date(2026, 1, 1),
        ),
    )
    await sessao_banco_horas.flush()

    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.lancar(
            sessao_banco_horas,
            tenant_id=contexto_banco_horas.tenant_id,
            bh_conta_id=conta.id,
            tipo="debito",
            origem="apuracao",
            minutos=-100,
            data_competencia=dt.date(2026, 1, 5),
            descricao="Debito alem do teto negativo",
        )
    assert excinfo.value.codigo == "PONTO-BH-002"


@pytest.mark.asyncio
async def test_debito_com_saldo_negativo_nao_permitido_falha_bh_002(
    sessao_banco_horas: AsyncSession, contexto_banco_horas: ContextoBancoHoras
) -> None:
    politica = await politicas_servico.criar_politica_banco_horas(
        sessao_banco_horas,
        contexto_banco_horas.tenant_id,
        esquemas.BhPoliticaCriar(
            empresaId=contexto_banco_horas.empresa_id,
            codigo="POL-SEM-NEGATIVO",
            nome="Politica sem saldo negativo",
            regime=esquemas.Regime.especial,
            periodoMeses=6,
            vigenciaInicio=dt.date(2026, 1, 1),
            permiteSaldoNegativo=False,
        ),
    )
    conta = await contas_servico.criar_conta_banco_horas(
        sessao_banco_horas,
        contexto_banco_horas.tenant_id,
        esquemas.BhContaCriar(
            vinculoId=contexto_banco_horas.vinculo_id,
            bhPoliticaId=politica.id,
            codigo="conta-sem-negativo",
            periodoInicio=dt.date(2026, 1, 1),
        ),
    )
    await sessao_banco_horas.flush()

    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.lancar(
            sessao_banco_horas,
            tenant_id=contexto_banco_horas.tenant_id,
            bh_conta_id=conta.id,
            tipo="debito",
            origem="apuracao",
            minutos=-10,
            data_competencia=dt.date(2026, 1, 5),
            descricao="Debito com saldo zerado nao pode ir negativo",
        )
    assert excinfo.value.codigo == "PONTO-BH-002"
