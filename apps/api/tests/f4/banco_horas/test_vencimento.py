"""Testes de `fn_bh_contas_para_verificacao_vencimento()` (RFC-013,
migration) e da rotina `verificar_banco_horas_vencendo` (T7,
`apps/worker/worker/scheduler.py` + `apps/worker/worker/
banco_horas_vencimento.py`).

Estes testes exercitam o pacote `worker` a partir de `apps/api/tests` --
mesmo padrao de `apps/api/tests/f2/importadores/test_worker_tarefa.py`
(F2): o venv de `apps/api` instala `ponto-worker` em modo editavel
(`apps/api/pyproject.toml` depende de `arq`/redis para a mesma finalidade),
entao `import worker` funciona daqui.
"""

from __future__ import annotations

import datetime as dt
import os

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.apuracao.banco_horas import contas as contas_servico
from app.apuracao.banco_horas import lancamentos as lancamentos_servico
from app.schemas import contrato as esquemas
from tests.f4.banco_horas.conftest import (
    ContextoBancoHoras,
    aplicar_tenant_teste,
    semear_tenant_minimo,
)


@pytest.fixture
def ambiente_worker_banco_horas(url_login_sessao_banco_horas: URL) -> None:
    """Aponta `worker.config.Configuracao` (`DATABASE_URL`) para o mesmo
    banco de teste da fase, autenticado como a MESMA role de LOGIN -- o
    worker tambem passa pelo RLS, nunca por superusuario (ADR-001). Mesmo
    padrao de `tests/f2/importadores/conftest.py` (F2)."""
    os.environ["DATABASE_URL"] = url_login_sessao_banco_horas.render_as_string(hide_password=False)
    from worker.config import obter_configuracao

    obter_configuracao.cache_clear()


@pytest_asyncio.fixture
async def worker_engine_reiniciada(ambiente_worker_banco_horas: None):
    """Descarta a engine cacheada em modulo do `worker` entre testes --
    `pytest-asyncio` abre um event loop novo por teste (`function` scope) e
    uma engine assincrona fica presa ao loop em que nasceu."""
    from worker.banco_horas_vencimento import limpar_barramento, reiniciar_engines_para_teste

    await reiniciar_engines_para_teste()
    limpar_barramento()
    yield
    await reiniciar_engines_para_teste()
    limpar_barramento()


@pytest.mark.asyncio
async def test_fn_bh_contas_para_verificacao_vencimento_cross_tenant(
    sessao_banco_horas: AsyncSession, engine_banco_horas: AsyncEngine
) -> None:
    """Prova de que o SECURITY DEFINER funciona (RFC-013): duas contas
    `aberta` de tenants DIFERENTES aparecem numa unica chamada, por uma
    conexao que NUNCA publicou `app.tenant_id`."""
    contexto_a = await semear_tenant_minimo(sessao_banco_horas, sufixo="crossa")
    contexto_b = await semear_tenant_minimo(sessao_banco_horas, sufixo="crossb")
    await sessao_banco_horas.commit()

    # Conexao NOVA, propria, sem NENHUM `SET LOCAL app.tenant_id` -- exatamente
    # o cenario do cron (sem tenant de entrada).
    async with engine_banco_horas.connect() as conexao:
        resultado = await conexao.execute(
            text("SELECT tenant_id FROM fn_bh_contas_para_verificacao_vencimento()")
        )
        tenants_encontrados = {linha.tenant_id for linha in resultado}

    assert contexto_a.tenant_id in tenants_encontrados
    assert contexto_b.tenant_id in tenants_encontrados


@pytest.mark.asyncio
async def test_scheduler_publica_vencendo_exatamente_nas_antecedencias_configuradas(
    sessao_banco_horas: AsyncSession,
    contexto_banco_horas: ContextoBancoHoras,
    worker_engine_reiniciada: None,
) -> None:
    """`bh_politicas.dias_pre_aviso` da politica semeada e o padrao do banco,
    `{30,15,7}`. Cria tres contas a distancias diferentes de `periodo_fim`
    (30, 20 e 7 dias) e confere que a rotina publica `banco_horas.vencendo`
    SOMENTE para as duas que batem exatamente uma antecedencia configurada."""
    from worker.banco_horas_vencimento import BARRAMENTO_INTERNO
    from worker.scheduler import verificar_banco_horas_vencendo

    hoje = dt.date.today()

    conta_30 = await contas_servico.criar_conta_banco_horas(
        sessao_banco_horas,
        contexto_banco_horas.tenant_id,
        esquemas.BhContaCriar(
            vinculoId=contexto_banco_horas.vinculo_id,
            bhPoliticaId=contexto_banco_horas.bh_politica_id,
            codigo="vence-30",
            periodoInicio=hoje - dt.timedelta(days=150),
            periodoFim=hoje + dt.timedelta(days=30),
        ),
    )
    conta_7 = await contas_servico.criar_conta_banco_horas(
        sessao_banco_horas,
        contexto_banco_horas.tenant_id,
        esquemas.BhContaCriar(
            vinculoId=contexto_banco_horas.vinculo_id,
            bhPoliticaId=contexto_banco_horas.bh_politica_id,
            codigo="vence-7",
            periodoInicio=hoje - dt.timedelta(days=150),
            periodoFim=hoje + dt.timedelta(days=7),
        ),
    )
    conta_20 = await contas_servico.criar_conta_banco_horas(
        sessao_banco_horas,
        contexto_banco_horas.tenant_id,
        esquemas.BhContaCriar(
            vinculoId=contexto_banco_horas.vinculo_id,
            bhPoliticaId=contexto_banco_horas.bh_politica_id,
            codigo="vence-20-nao-avisa",
            periodoInicio=hoje - dt.timedelta(days=150),
            periodoFim=hoje + dt.timedelta(days=20),
        ),
    )
    for conta in (conta_30, conta_7, conta_20):
        await lancamentos_servico.lancar(
            sessao_banco_horas,
            tenant_id=contexto_banco_horas.tenant_id,
            bh_conta_id=conta.id,
            tipo="credito",
            origem="apuracao",
            minutos=500,
            data_competencia=hoje,
            descricao="Saldo a vencer",
        )
    await sessao_banco_horas.commit()

    resultado = await verificar_banco_horas_vencendo({"job_id": "teste-vencimento"})
    assert resultado["implementado"] is True

    eventos_desta_conta = {
        conta.id: [
            e
            for e in BARRAMENTO_INTERNO
            if e["tipo"] == "banco_horas.vencendo" and e["dados"]["contaId"] == str(conta.id)
        ]
        for conta in (conta_30, conta_7, conta_20)
    }

    assert len(eventos_desta_conta[conta_30.id]) == 1
    assert eventos_desta_conta[conta_30.id][0]["dados"]["diasRestantes"] == 30
    assert eventos_desta_conta[conta_30.id][0]["dados"]["minutosAVencer"] == 500

    assert len(eventos_desta_conta[conta_7.id]) == 1
    assert eventos_desta_conta[conta_7.id][0]["dados"]["diasRestantes"] == 7

    assert eventos_desta_conta[conta_20.id] == []

    # Cada evento tem os `required` de events.yaml.
    for evento in eventos_desta_conta[conta_30.id] + eventos_desta_conta[conta_7.id]:
        dados = evento["dados"]
        for campo in (
            "contaId",
            "colaboradorId",
            "vinculoId",
            "minutosAVencer",
            "venceEm",
            "diasRestantes",
        ):
            assert campo in dados

    # A ocorrencia `banco_vencendo` (PCF secao 2) foi aberta para a conta que
    # avisou.
    await aplicar_tenant_teste(sessao_banco_horas, contexto_banco_horas.tenant_id)
    from ponto_contracts import Ocorrencia
    from sqlalchemy import select

    linhas = await sessao_banco_horas.execute(
        select(Ocorrencia).where(
            Ocorrencia.tenant_id == contexto_banco_horas.tenant_id,
            Ocorrencia.codigo == "banco_vencendo",
        )
    )
    assert len(linhas.scalars().all()) >= 2
