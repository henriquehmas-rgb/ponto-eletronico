"""Prova campo a campo, contra `packages/contracts/events.yaml`, que os três
eventos publicados por A2 (`periodo.fechado`, `periodo.reaberto`,
`espelho.assinado`) carregam todos os campos `required` do contrato --
critério de aceite 11 do PCF F10. Mesmo padrão de checagem manual que
`tests/f4/banco_horas/test_vencimento.py` já usa para `banco_horas.vencendo`.
"""

from __future__ import annotations

import datetime as dt

import pytest
from ponto_contracts import ApuracaoDia, Fechamento, Periodo

from app.schemas import contrato as esquemas
from app.workflow.fechamento.assinatura import assinar_espelho
from app.workflow.fechamento.espelho import gerar_espelho_do_vinculo
from app.workflow.fechamento.eventos import BARRAMENTO_INTERNO, limpar_barramento
from app.workflow.fechamento.servico import reabrir_fechamento
from tests.f10.conftest import ContextoF10, aplicar_tenant_teste

#: `events.yaml`, campo a campo.
_REQUERIDOS_PERIODO_FECHADO = (
    "fechamentoId",
    "periodoId",
    "empresaId",
    "escopo",
    "dataInicio",
    "dataFim",
    "fechadoEm",
)
_REQUERIDOS_PERIODO_REABERTO = (
    "fechamentoId",
    "periodoId",
    "empresaId",
    "reabertoEm",
    "reabertoPor",
    "motivo",
)
_REQUERIDOS_ESPELHO_ASSINADO = (
    "espelhoId",
    "colaboradorId",
    "vinculoId",
    "periodoId",
    "signatarioTipo",
    "metodo",
    "carimboTempo",
    "hashAssinado",
)


@pytest.fixture(autouse=True)
def _barramento_limpo():
    limpar_barramento()
    yield


@pytest.fixture(autouse=True)
async def _encerrar_engine_worker():
    """`test_periodo_fechado_...` abaixo chama `processar_fechamento`
    (worker), que abre sessão própria via `app.db.sessao.fabrica_de_
    sessoes()` -- mesmo achado de infraestrutura de teste documentado em
    `tests/f10/fechamento/test_worker_tarefas.py`: descartar a engine
    memorizada ao fim de CADA teste (enquanto o *event loop* ainda está
    vivo) evita que o teste seguinte herde uma conexão presa a um loop já
    fechado."""
    yield
    from app.db.sessao import encerrar_engine

    await encerrar_engine()
    limpar_barramento()


async def _periodo(sessao, contexto: ContextoF10) -> Periodo:
    return await sessao.get(Periodo, contexto.periodo_id)


@pytest.mark.asyncio
async def test_periodo_fechado_tem_todos_os_campos_required(
    sessao_f10, contexto_f10: ContextoF10
) -> None:
    from worker.tarefas.fechamento import processar_fechamento

    periodo = await _periodo(sessao_f10, contexto_f10)
    sessao_f10.add(
        ApuracaoDia(
            tenant_id=contexto_f10.tenant_id,
            vinculo_id=contexto_f10.vinculo_id,
            colaborador_id=contexto_f10.colaborador_id,
            data=periodo.data_inicio,
            empresa_id=contexto_f10.empresa_id,
            tipo_dia="util",
            previsto_minutos=480,
            trabalhado_minutos=480,
            status="apurado",
        )
    )
    fechamento = Fechamento(
        tenant_id=contexto_f10.tenant_id,
        periodo_id=periodo.id,
        empresa_id=contexto_f10.empresa_id,
        escopo="empresa",
        status="em_andamento",
    )
    sessao_f10.add(fechamento)
    await sessao_f10.flush()
    await sessao_f10.commit()
    await aplicar_tenant_teste(sessao_f10, contexto_f10.tenant_id)

    await processar_fechamento(
        {"job_id": "teste-eventos-1"},
        tenant_id=str(contexto_f10.tenant_id),
        fechamento_id=str(fechamento.id),
        gerar_espelhos=False,
        usuario_id=str(contexto_f10.rh_usuario_id),
    )

    eventos = [e for e in BARRAMENTO_INTERNO if e["tipo"] == "periodo.fechado"]
    assert len(eventos) == 1
    dados = eventos[0]["dados"]
    for campo in _REQUERIDOS_PERIODO_FECHADO:
        assert campo in dados, f"campo required '{campo}' ausente em periodo.fechado"
    assert dados["escopo"] == "empresa"


@pytest.mark.asyncio
async def test_periodo_reaberto_tem_todos_os_campos_required(
    sessao_f10, contexto_f10: ContextoF10
) -> None:
    periodo = await _periodo(sessao_f10, contexto_f10)
    fechamento = Fechamento(
        tenant_id=contexto_f10.tenant_id,
        periodo_id=periodo.id,
        empresa_id=contexto_f10.empresa_id,
        escopo="empresa",
        status="fechado",
        fechado_em=dt.datetime.now(tz=dt.UTC),
        fechado_por=contexto_f10.rh_usuario_id,
    )
    sessao_f10.add(fechamento)
    await sessao_f10.flush()
    await sessao_f10.commit()
    await aplicar_tenant_teste(sessao_f10, contexto_f10.tenant_id)

    await reabrir_fechamento(
        sessao_f10,
        contexto_f10.tenant_id,
        fechamento.id,
        esquemas.ReaberturaRequisicao(motivo="Erro de digitacao no ponto do dia 5 (teste)."),
        usuario_id=contexto_f10.rh_usuario_id,
    )

    eventos = [e for e in BARRAMENTO_INTERNO if e["tipo"] == "periodo.reaberto"]
    assert len(eventos) == 1
    dados = eventos[0]["dados"]
    for campo in _REQUERIDOS_PERIODO_REABERTO:
        assert campo in dados, f"campo required '{campo}' ausente em periodo.reaberto"


@pytest.mark.asyncio
async def test_espelho_assinado_tem_todos_os_campos_required(
    sessao_f10, contexto_f10: ContextoF10
) -> None:
    periodo = await _periodo(sessao_f10, contexto_f10)
    espelho = await gerar_espelho_do_vinculo(
        sessao_f10,
        contexto_f10.tenant_id,
        periodo,
        contexto_f10.vinculo_id,
        "previo",
        usuario_id=contexto_f10.rh_usuario_id,
    )

    await assinar_espelho(
        sessao_f10,
        contexto_f10.tenant_id,
        espelho.id,
        esquemas.AssinaturaEspelhoRequisicao(hashSha256=espelho.hash_sha256, aceite=True),
        usuario_id=contexto_f10.colaborador_usuario_id,
    )

    eventos = [e for e in BARRAMENTO_INTERNO if e["tipo"] == "espelho.assinado"]
    assert len(eventos) == 1
    dados = eventos[0]["dados"]
    for campo in _REQUERIDOS_ESPELHO_ASSINADO:
        assert campo in dados, f"campo required '{campo}' ausente em espelho.assinado"
