"""Testes de `app.apuracao.banco_horas.consulta` (T6): extrato, saldo e o
simulador -- em especial a prova de que `simularBancoHoras` nunca grava
nada."""

from __future__ import annotations

import datetime as dt

import pytest
import sqlalchemy as sa
from ponto_contracts import BhConta, BhLancamento
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.apuracao.banco_horas import consulta as servico
from app.apuracao.banco_horas import lancamentos as lancamentos_servico
from app.schemas import contrato as esquemas
from tests.f4.banco_horas.conftest import ContextoBancoHoras


async def _contar_lancamentos(sessao: AsyncSession, contexto: ContextoBancoHoras) -> int:
    resultado = await sessao.execute(
        select(sa.func.count())
        .where(
            BhLancamento.tenant_id == contexto.tenant_id,
            BhLancamento.bh_conta_id == contexto.bh_conta_id,
        )
        .select_from(BhLancamento)
    )
    return int(resultado.scalar_one())


@pytest.mark.asyncio
async def test_simular_banco_horas_nao_grava_nada(
    sessao_banco_horas: AsyncSession, contexto_banco_horas: ContextoBancoHoras
) -> None:
    await lancamentos_servico.lancar(
        sessao_banco_horas,
        tenant_id=contexto_banco_horas.tenant_id,
        bh_conta_id=contexto_banco_horas.bh_conta_id,
        tipo="credito",
        origem="apuracao",
        minutos=200,
        data_competencia=dt.date(2026, 1, 5),
        descricao="Credito antes da simulacao",
    )
    await sessao_banco_horas.flush()

    total_antes = await _contar_lancamentos(sessao_banco_horas, contexto_banco_horas)
    conta_antes = await sessao_banco_horas.get(BhConta, contexto_banco_horas.bh_conta_id)
    assert conta_antes is not None
    saldo_antes = conta_antes.saldo_atual_minutos

    resposta = await servico.simular_banco_horas(
        sessao_banco_horas,
        contexto_banco_horas.tenant_id,
        esquemas.SimulacaoBancoRequisicao(
            contaId=contexto_banco_horas.bh_conta_id, minutosCompensar=90
        ),
    )

    total_depois = await _contar_lancamentos(sessao_banco_horas, contexto_banco_horas)
    await sessao_banco_horas.refresh(conta_antes)

    assert total_depois == total_antes
    assert conta_antes.saldo_atual_minutos == saldo_antes
    assert resposta.saldo_atual_minutos == saldo_antes
    assert resposta.impacto_minutos == -90
    assert resposta.saldo_simulado_minutos == saldo_antes - 90


@pytest.mark.asyncio
async def test_obter_saldo_banco_horas_reflete_conta(
    sessao_banco_horas: AsyncSession, contexto_banco_horas: ContextoBancoHoras
) -> None:
    await lancamentos_servico.lancar(
        sessao_banco_horas,
        tenant_id=contexto_banco_horas.tenant_id,
        bh_conta_id=contexto_banco_horas.bh_conta_id,
        tipo="credito",
        origem="apuracao",
        minutos=300,
        data_competencia=dt.date(2026, 1, 5),
        descricao="Credito do saldo",
    )
    await sessao_banco_horas.flush()

    saldo = await servico.obter_saldo_banco_horas(
        sessao_banco_horas, contexto_banco_horas.tenant_id, contexto_banco_horas.colaborador_id
    )
    assert saldo.saldo_minutos == 300
    assert saldo.conta_codigo == "normal"


@pytest.mark.asyncio
async def test_obter_extrato_banco_horas_agrega_creditos_e_debitos(
    sessao_banco_horas: AsyncSession, contexto_banco_horas: ContextoBancoHoras
) -> None:
    await lancamentos_servico.lancar(
        sessao_banco_horas,
        tenant_id=contexto_banco_horas.tenant_id,
        bh_conta_id=contexto_banco_horas.bh_conta_id,
        tipo="credito",
        origem="apuracao",
        minutos=200,
        data_competencia=dt.date(2026, 1, 5),
        descricao="Credito",
    )
    await lancamentos_servico.lancar(
        sessao_banco_horas,
        tenant_id=contexto_banco_horas.tenant_id,
        bh_conta_id=contexto_banco_horas.bh_conta_id,
        tipo="debito",
        origem="apuracao",
        minutos=-50,
        data_competencia=dt.date(2026, 1, 6),
        descricao="Debito",
    )

    extrato = await servico.obter_extrato_banco_horas(
        sessao_banco_horas, contexto_banco_horas.tenant_id, contexto_banco_horas.colaborador_id
    )
    assert extrato.creditos_minutos == 200
    assert extrato.debitos_minutos == 50
    assert extrato.saldo_final_minutos == 150
    assert len(extrato.lancamentos) == 2


@pytest.mark.asyncio
async def test_obter_extrato_filtra_por_tipo_data_e_pagina(
    sessao_banco_horas: AsyncSession, contexto_banco_horas: ContextoBancoHoras
) -> None:
    await lancamentos_servico.lancar(
        sessao_banco_horas,
        tenant_id=contexto_banco_horas.tenant_id,
        bh_conta_id=contexto_banco_horas.bh_conta_id,
        tipo="credito",
        origem="apuracao",
        minutos=100,
        data_competencia=dt.date(2026, 1, 1),
        descricao="Credito de janeiro",
    )
    await lancamentos_servico.lancar(
        sessao_banco_horas,
        tenant_id=contexto_banco_horas.tenant_id,
        bh_conta_id=contexto_banco_horas.bh_conta_id,
        tipo="credito",
        origem="apuracao",
        minutos=50,
        data_competencia=dt.date(2026, 2, 1),
        descricao="Credito de fevereiro",
    )

    apenas_creditos = await servico.obter_extrato_banco_horas(
        sessao_banco_horas,
        contexto_banco_horas.tenant_id,
        contexto_banco_horas.colaborador_id,
        tipo="credito",
        de=dt.date(2026, 1, 15),
        ate=dt.date(2026, 2, 28),
    )
    assert len(apenas_creditos.lancamentos) == 1
    assert apenas_creditos.saldo_inicial_minutos == 100
    assert apenas_creditos.saldo_final_minutos == 150

    primeira_pagina = await servico.obter_extrato_banco_horas(
        sessao_banco_horas,
        contexto_banco_horas.tenant_id,
        contexto_banco_horas.colaborador_id,
        limite=1,
    )
    assert len(primeira_pagina.lancamentos) == 1
    assert primeira_pagina.paginacao.tem_mais is True
    assert primeira_pagina.paginacao.proximo_cursor is not None

    segunda_pagina = await servico.obter_extrato_banco_horas(
        sessao_banco_horas,
        contexto_banco_horas.tenant_id,
        contexto_banco_horas.colaborador_id,
        limite=1,
        cursor=primeira_pagina.paginacao.proximo_cursor,
    )
    assert len(segunda_pagina.lancamentos) == 1
    assert segunda_pagina.lancamentos[0].id != primeira_pagina.lancamentos[0].id


@pytest.mark.asyncio
async def test_obter_saldo_historico_reconstroi_a_partir_do_extrato(
    sessao_banco_horas: AsyncSession, contexto_banco_horas: ContextoBancoHoras
) -> None:
    await lancamentos_servico.lancar(
        sessao_banco_horas,
        tenant_id=contexto_banco_horas.tenant_id,
        bh_conta_id=contexto_banco_horas.bh_conta_id,
        tipo="credito",
        origem="apuracao",
        minutos=100,
        data_competencia=dt.date(2026, 1, 5),
        descricao="Credito de janeiro",
    )
    await lancamentos_servico.lancar(
        sessao_banco_horas,
        tenant_id=contexto_banco_horas.tenant_id,
        bh_conta_id=contexto_banco_horas.bh_conta_id,
        tipo="credito",
        origem="apuracao",
        minutos=50,
        data_competencia=dt.date(2026, 3, 1),
        descricao="Credito de marco",
    )

    saldo_em_fevereiro = await servico.obter_saldo_banco_horas(
        sessao_banco_horas,
        contexto_banco_horas.tenant_id,
        contexto_banco_horas.colaborador_id,
        data_referencia=dt.date(2026, 2, 15),
    )
    assert saldo_em_fevereiro.saldo_minutos == 100

    saldo_agora = await servico.obter_saldo_banco_horas(
        sessao_banco_horas, contexto_banco_horas.tenant_id, contexto_banco_horas.colaborador_id
    )
    assert saldo_agora.saldo_minutos == 150


@pytest.mark.asyncio
async def test_simular_por_colaborador_com_saida_prevista_avisa_limitacao(
    sessao_banco_horas: AsyncSession, contexto_banco_horas: ContextoBancoHoras
) -> None:
    resposta = await servico.simular_banco_horas(
        sessao_banco_horas,
        contexto_banco_horas.tenant_id,
        esquemas.SimulacaoBancoRequisicao(
            colaboradorId=contexto_banco_horas.colaborador_id, saidaPrevista="16:00"
        ),
    )
    assert resposta.impacto_minutos == 0
    assert resposta.avisos and "apuracao da jornada" in resposta.avisos[0]


@pytest.mark.asyncio
async def test_simular_sem_colaborador_nem_conta_e_recusado(
    sessao_banco_horas: AsyncSession, contexto_banco_horas: ContextoBancoHoras
) -> None:
    from app.core.erros import ErroDeAplicacao

    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.simular_banco_horas(
            sessao_banco_horas, contexto_banco_horas.tenant_id, esquemas.SimulacaoBancoRequisicao()
        )
    assert excinfo.value.codigo == "PONTO-VAL-001"


@pytest.mark.asyncio
async def test_simular_fora_dos_tetos_e_sinalizado(
    sessao_banco_horas: AsyncSession, contexto_banco_horas: ContextoBancoHoras
) -> None:
    from app.apuracao.banco_horas import contas as contas_servico
    from app.apuracao.banco_horas import politicas as politicas_servico

    politica = await politicas_servico.criar_politica_banco_horas(
        sessao_banco_horas,
        contexto_banco_horas.tenant_id,
        esquemas.BhPoliticaCriar(
            empresaId=contexto_banco_horas.empresa_id,
            codigo="POL-SIMULACAO-TETO",
            nome="Politica com teto para simulacao",
            regime=esquemas.Regime.especial,
            periodoMeses=6,
            vigenciaInicio=dt.date(2026, 1, 1),
            tetoNegativoMinutos=10,
        ),
    )
    conta = await contas_servico.criar_conta_banco_horas(
        sessao_banco_horas,
        contexto_banco_horas.tenant_id,
        esquemas.BhContaCriar(
            vinculoId=contexto_banco_horas.vinculo_id,
            bhPoliticaId=politica.id,
            codigo="conta-simulacao-teto",
            periodoInicio=dt.date(2026, 1, 1),
        ),
    )
    await lancamentos_servico.lancar(
        sessao_banco_horas,
        tenant_id=contexto_banco_horas.tenant_id,
        bh_conta_id=conta.id,
        tipo="credito",
        origem="apuracao",
        minutos=5,
        data_competencia=dt.date(2026, 1, 5),
        descricao="Credito pequeno",
    )

    # `minutosCompensar` simula consumo (debito); 30 min de compensacao sobre
    # um saldo de 5 levaria a -25, alem do teto negativo de 10.
    resposta = await servico.simular_banco_horas(
        sessao_banco_horas,
        contexto_banco_horas.tenant_id,
        esquemas.SimulacaoBancoRequisicao(contaId=conta.id, minutosCompensar=30),
    )
    assert resposta.saldo_simulado_minutos == -25
    assert resposta.dentro_dos_tetos is False


@pytest.mark.asyncio
async def test_resolver_conta_por_codigo_e_por_id(
    sessao_banco_horas: AsyncSession, contexto_banco_horas: ContextoBancoHoras
) -> None:
    from app.apuracao.banco_horas import contas as contas_servico

    outra = await contas_servico.criar_conta_banco_horas(
        sessao_banco_horas,
        contexto_banco_horas.tenant_id,
        esquemas.BhContaCriar(
            vinculoId=contexto_banco_horas.vinculo_id,
            bhPoliticaId=contexto_banco_horas.bh_politica_id,
            codigo="sobreaviso-resolver",
            periodoInicio=dt.date(2026, 1, 1),
        ),
    )

    por_codigo = await servico.obter_saldo_banco_horas(
        sessao_banco_horas,
        contexto_banco_horas.tenant_id,
        contexto_banco_horas.colaborador_id,
        conta_codigo="sobreaviso-resolver",
    )
    assert por_codigo.conta_id == outra.id

    from app.core.erros import ErroDeAplicacao

    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.obter_saldo_banco_horas(
            sessao_banco_horas,
            contexto_banco_horas.tenant_id,
            contexto_banco_horas.colaborador_id,
            conta_codigo="inexistente",
        )
    assert excinfo.value.codigo == "PONTO-REC-001"
