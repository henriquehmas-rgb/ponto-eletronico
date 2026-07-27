"""Testes de `app.apuracao.banco_horas.quitacoes` (T7): saldo insuficiente,
quitacao efetivada com evento publicado, e os tetos da politica."""

from __future__ import annotations

import datetime as dt

import pytest
from ponto_contracts import Ocorrencia
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.apuracao.banco_horas import contas as contas_servico
from app.apuracao.banco_horas import eventos as eventos_servico
from app.apuracao.banco_horas import lancamentos as lancamentos_servico
from app.apuracao.banco_horas import politicas as politicas_servico
from app.apuracao.banco_horas import quitacoes as servico
from app.core.erros import ErroDeAplicacao
from app.schemas import contrato as esquemas
from tests.f4.banco_horas.conftest import ContextoBancoHoras


@pytest.fixture(autouse=True)
def _barramento_limpo():
    eventos_servico.limpar_barramento()
    yield
    eventos_servico.limpar_barramento()


@pytest.mark.asyncio
async def test_saldo_insuficiente_e_recusado(
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
        descricao="Credito insuficiente",
    )
    await sessao_banco_horas.flush()

    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.criar_quitacao_banco_horas(
            sessao_banco_horas,
            contexto_banco_horas.tenant_id,
            esquemas.BhQuitacaoCriar(
                bhContaId=contexto_banco_horas.bh_conta_id, tipo=esquemas.Tipo28.folha, minutos=500
            ),
        )
    assert excinfo.value.codigo == "PONTO-BH-005"


@pytest.mark.asyncio
async def test_quitacao_efetivada_gera_lancamento_e_publica_evento(
    sessao_banco_horas: AsyncSession, contexto_banco_horas: ContextoBancoHoras
) -> None:
    await lancamentos_servico.lancar(
        sessao_banco_horas,
        tenant_id=contexto_banco_horas.tenant_id,
        bh_conta_id=contexto_banco_horas.bh_conta_id,
        tipo="credito",
        origem="apuracao",
        minutos=600,
        data_competencia=dt.date(2026, 1, 5),
        descricao="Credito para quitar",
    )
    await sessao_banco_horas.flush()

    quitacao = await servico.criar_quitacao_banco_horas(
        sessao_banco_horas,
        contexto_banco_horas.tenant_id,
        esquemas.BhQuitacaoCriar(
            bhContaId=contexto_banco_horas.bh_conta_id,
            tipo=esquemas.Tipo28.folha,
            minutos=200,
            competenciaFolha="2026-02",
        ),
    )
    assert quitacao.status == "efetivada"
    assert quitacao.data_efetivacao is not None

    conta = await contas_servico.obter_conta_banco_horas(
        sessao_banco_horas, contexto_banco_horas.tenant_id, contexto_banco_horas.bh_conta_id
    )
    assert conta.saldo_atual_minutos == 400

    eventos = [
        e
        for e in eventos_servico.BARRAMENTO_INTERNO
        if e["tipo"] == "banco_horas.quitado" and e["dados"]["quitacaoId"] == str(quitacao.id)
    ]
    assert len(eventos) == 1
    dados = eventos[0]["dados"]
    assert dados["contaId"] == str(contexto_banco_horas.bh_conta_id)
    assert dados["colaboradorId"] == str(contexto_banco_horas.colaborador_id)
    assert dados["tipo"] == "folha"
    assert dados["minutos"] == 200
    assert dados["saldoAposMinutos"] == 400
    assert "lancamentoId" in dados
    assert "dataEfetivacao" in dados
    campos_obrigatorios = (
        "quitacaoId",
        "contaId",
        "colaboradorId",
        "tipo",
        "minutos",
        "dataEfetivacao",
        "saldoAposMinutos",
    )
    for campo in campos_obrigatorios:
        assert campo in dados


async def _politica_com_teto(
    sessao: AsyncSession,
    contexto: ContextoBancoHoras,
    *,
    bloqueia_extra_no_teto: bool,
    sufixo: str,
):
    politica = await politicas_servico.criar_politica_banco_horas(
        sessao,
        contexto.tenant_id,
        esquemas.BhPoliticaCriar(
            empresaId=contexto.empresa_id,
            codigo=f"POL-TETO-{sufixo}",
            nome="Politica com teto",
            regime=esquemas.Regime.especial,
            periodoMeses=6,
            vigenciaInicio=dt.date(2026, 1, 1),
            tetoPositivoMinutos=100,
            bloqueiaExtraNoTeto=bloqueia_extra_no_teto,
        ),
    )
    conta = await contas_servico.criar_conta_banco_horas(
        sessao,
        contexto.tenant_id,
        esquemas.BhContaCriar(
            vinculoId=contexto.vinculo_id,
            bhPoliticaId=politica.id,
            codigo=f"conta-teto-{sufixo}",
            periodoInicio=dt.date(2026, 1, 1),
        ),
    )
    await sessao.flush()
    return conta


@pytest.mark.asyncio
async def test_teto_positivo_bloqueia_credito_quando_bloqueia_extra_no_teto(
    sessao_banco_horas: AsyncSession, contexto_banco_horas: ContextoBancoHoras
) -> None:
    conta = await _politica_com_teto(
        sessao_banco_horas, contexto_banco_horas, bloqueia_extra_no_teto=True, sufixo="bloq"
    )
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await lancamentos_servico.lancar(
            sessao_banco_horas,
            tenant_id=contexto_banco_horas.tenant_id,
            bh_conta_id=conta.id,
            tipo="credito",
            origem="apuracao",
            minutos=150,
            data_competencia=dt.date(2026, 1, 5),
            descricao="Credito acima do teto",
        )
    assert excinfo.value.codigo == "PONTO-BH-001"


@pytest.mark.asyncio
async def test_teto_positivo_sinaliza_ocorrencia_quando_nao_bloqueia(
    sessao_banco_horas: AsyncSession, contexto_banco_horas: ContextoBancoHoras
) -> None:
    conta = await _politica_com_teto(
        sessao_banco_horas, contexto_banco_horas, bloqueia_extra_no_teto=False, sufixo="sinal"
    )
    lancamento = await lancamentos_servico.lancar(
        sessao_banco_horas,
        tenant_id=contexto_banco_horas.tenant_id,
        bh_conta_id=conta.id,
        tipo="credito",
        origem="apuracao",
        minutos=150,
        data_competencia=dt.date(2026, 1, 5),
        descricao="Credito acima do teto, sinalizado",
    )
    assert lancamento.minutos_equivalentes == 150

    resultado = await sessao_banco_horas.execute(
        select(Ocorrencia).where(
            Ocorrencia.tenant_id == contexto_banco_horas.tenant_id,
            Ocorrencia.codigo == "banco_teto",
            Ocorrencia.vinculo_id == contexto_banco_horas.vinculo_id,
        )
    )
    ocorrencias = resultado.scalars().all()
    assert len(ocorrencias) == 1
    assert ocorrencias[0].colaborador_id == contexto_banco_horas.colaborador_id


@pytest.mark.asyncio
async def test_quitacao_planejada_nao_efetiva_nem_publica_evento(
    sessao_banco_horas: AsyncSession, contexto_banco_horas: ContextoBancoHoras
) -> None:
    await lancamentos_servico.lancar(
        sessao_banco_horas,
        tenant_id=contexto_banco_horas.tenant_id,
        bh_conta_id=contexto_banco_horas.bh_conta_id,
        tipo="credito",
        origem="apuracao",
        minutos=600,
        data_competencia=dt.date(2026, 1, 5),
        descricao="Credito para quitacao planejada",
    )
    await sessao_banco_horas.flush()

    quitacao = await servico.criar_quitacao_banco_horas(
        sessao_banco_horas,
        contexto_banco_horas.tenant_id,
        esquemas.BhQuitacaoCriar(
            bhContaId=contexto_banco_horas.bh_conta_id,
            tipo=esquemas.Tipo28.folga,
            minutos=200,
            status=esquemas.Status32.planejada,
        ),
    )
    assert quitacao.status == "planejada"
    assert quitacao.data_efetivacao is None

    conta = await contas_servico.obter_conta_banco_horas(
        sessao_banco_horas, contexto_banco_horas.tenant_id, contexto_banco_horas.bh_conta_id
    )
    assert conta.saldo_atual_minutos == 600  # nao debitou nada

    eventos = [e for e in eventos_servico.BARRAMENTO_INTERNO if e["tipo"] == "banco_horas.quitado"]
    assert eventos == []


@pytest.mark.asyncio
async def test_quitacao_expiracao_usa_lancamento_tipo_expiracao(
    sessao_banco_horas: AsyncSession, contexto_banco_horas: ContextoBancoHoras
) -> None:
    from ponto_contracts import BhLancamento
    from sqlalchemy import select as sa_select

    await lancamentos_servico.lancar(
        sessao_banco_horas,
        tenant_id=contexto_banco_horas.tenant_id,
        bh_conta_id=contexto_banco_horas.bh_conta_id,
        tipo="credito",
        origem="apuracao",
        minutos=300,
        data_competencia=dt.date(2026, 1, 5),
        descricao="Credito que vai expirar",
    )
    await sessao_banco_horas.flush()

    quitacao = await servico.criar_quitacao_banco_horas(
        sessao_banco_horas,
        contexto_banco_horas.tenant_id,
        esquemas.BhQuitacaoCriar(
            bhContaId=contexto_banco_horas.bh_conta_id, tipo=esquemas.Tipo28.expiracao, minutos=300
        ),
    )
    resultado = await sessao_banco_horas.execute(
        sa_select(BhLancamento).where(BhLancamento.quitacao_id == quitacao.id)
    )
    lancamento = resultado.scalar_one()
    assert lancamento.tipo == "expiracao"
    assert lancamento.origem == "expiracao"
    assert lancamento.minutos == -300
