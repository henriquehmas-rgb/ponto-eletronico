"""Testes de `app.workflow.fechamento.periodos` (T5, F10/A2)."""

from __future__ import annotations

import datetime as dt

import pytest
from ponto_contracts import Periodo

from app.core.erros import ErroDeAplicacao
from app.schemas import contrato as esquemas
from app.workflow.fechamento import periodos
from tests.f10.conftest import ContextoF10, aplicar_tenant_teste


@pytest.mark.asyncio
async def test_criar_periodo_sucesso(sessao_f10, contexto_f10: ContextoF10) -> None:
    novo = await periodos.criar_periodo(
        sessao_f10,
        contexto_f10.tenant_id,
        esquemas.PeriodoCriar(
            empresaId=contexto_f10.empresa_id,
            codigo="2026-08-teste",
            tipo=esquemas.Tipo30.mensal,
            dataInicio=dt.date(2026, 8, 1),
            dataFim=dt.date(2026, 8, 31),
        ),
        usuario_id=contexto_f10.gestor_usuario_id,
    )
    assert novo.id is not None
    assert novo.status == "aberto"
    assert novo.tipo == "mensal"


@pytest.mark.asyncio
async def test_criar_periodo_data_fim_antes_de_inicio_e_val_007(
    sessao_f10, contexto_f10: ContextoF10
) -> None:
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await periodos.criar_periodo(
            sessao_f10,
            contexto_f10.tenant_id,
            esquemas.PeriodoCriar(
                empresaId=contexto_f10.empresa_id,
                codigo="2026-08-invertido",
                dataInicio=dt.date(2026, 8, 31),
                dataFim=dt.date(2026, 8, 1),
            ),
            usuario_id=contexto_f10.gestor_usuario_id,
        )
    assert excinfo.value.codigo == "PONTO-VAL-007"


@pytest.mark.asyncio
async def test_criar_periodo_codigo_duplicado_e_conf_001(
    sessao_f10, contexto_f10: ContextoF10
) -> None:
    dados = esquemas.PeriodoCriar(
        empresaId=contexto_f10.empresa_id,
        codigo="2026-09-dup",
        dataInicio=dt.date(2026, 9, 1),
        dataFim=dt.date(2026, 9, 30),
    )
    await periodos.criar_periodo(
        sessao_f10, contexto_f10.tenant_id, dados, usuario_id=contexto_f10.gestor_usuario_id
    )
    await sessao_f10.commit()
    await aplicar_tenant_teste(sessao_f10, contexto_f10.tenant_id)

    with pytest.raises(ErroDeAplicacao) as excinfo:
        await periodos.criar_periodo(
            sessao_f10, contexto_f10.tenant_id, dados, usuario_id=contexto_f10.gestor_usuario_id
        )
    assert excinfo.value.codigo == "PONTO-CONF-001"


@pytest.mark.asyncio
async def test_listar_periodos_filtra_por_empresa_e_status(
    sessao_f10, contexto_f10: ContextoF10
) -> None:
    # A fixture ja semeia 1 periodo aberto para a empresa.
    linhas, paginacao = await periodos.listar_periodos(
        sessao_f10,
        contexto_f10.tenant_id,
        empresa_id=contexto_f10.empresa_id,
        status="aberto",
    )
    assert any(p.id == contexto_f10.periodo_id for p in linhas)
    assert paginacao.limite == periodos.normalizar_limite(None)
    assert all(isinstance(p, Periodo) for p in linhas)
