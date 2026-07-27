"""Testes de `app.apuracao.banco_horas.contas` (T5).

Cobre a derivacao de `periodoFim` a partir de `bh_politicas.periodo_meses`,
a derivacao de `colaboradorId` a partir do vinculo, e a duplicidade
`uq_bh_contas` (`PONTO-CONF-001`).
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.apuracao.banco_horas import contas as servico
from app.core.erros import ErroDeAplicacao
from app.schemas import contrato as esquemas
from tests.f4.banco_horas.conftest import ContextoBancoHoras


@pytest.mark.asyncio
async def test_periodo_fim_derivado_da_politica_individual_6_meses(
    sessao_banco_horas: AsyncSession, contexto_banco_horas: ContextoBancoHoras
) -> None:
    dados = esquemas.BhContaCriar(
        vinculoId=contexto_banco_horas.vinculo_id,
        bhPoliticaId=contexto_banco_horas.bh_politica_id,
        codigo="sobreaviso",
        periodoInicio=dt.date(2026, 7, 1),
    )
    conta = await servico.criar_conta_banco_horas(
        sessao_banco_horas, contexto_banco_horas.tenant_id, dados
    )
    # Politica de teste: individual, periodo_meses=6 -> 2026-07-01 + 6 meses - 1 dia.
    assert conta.periodo_fim == dt.date(2026, 12, 31)
    assert conta.colaborador_id == contexto_banco_horas.colaborador_id


@pytest.mark.asyncio
async def test_duas_contas_mesmo_vinculo_mesmo_codigo_mesmo_periodo_colidem(
    sessao_banco_horas: AsyncSession, contexto_banco_horas: ContextoBancoHoras
) -> None:
    dados = esquemas.BhContaCriar(
        vinculoId=contexto_banco_horas.vinculo_id,
        bhPoliticaId=contexto_banco_horas.bh_politica_id,
        codigo="feriado",
        periodoInicio=dt.date(2026, 1, 1),
    )
    await servico.criar_conta_banco_horas(sessao_banco_horas, contexto_banco_horas.tenant_id, dados)
    await sessao_banco_horas.flush()

    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.criar_conta_banco_horas(
            sessao_banco_horas, contexto_banco_horas.tenant_id, dados
        )
    assert excinfo.value.codigo == "PONTO-CONF-001"


@pytest.mark.asyncio
async def test_listar_contas_filtra_por_empresa(
    sessao_banco_horas: AsyncSession, contexto_banco_horas: ContextoBancoHoras
) -> None:
    linhas, paginacao = await servico.listar_contas_banco_horas(
        sessao_banco_horas,
        contexto_banco_horas.tenant_id,
        empresa_id=contexto_banco_horas.empresa_id,
    )
    assert len(linhas) >= 1
    assert all(linha.vinculo_id == contexto_banco_horas.vinculo_id for linha in linhas)
    assert paginacao.limite > 0


@pytest.mark.asyncio
async def test_periodo_fim_explicito_menor_que_inicio_e_recusado(
    sessao_banco_horas: AsyncSession, contexto_banco_horas: ContextoBancoHoras
) -> None:
    dados = esquemas.BhContaCriar(
        vinculoId=contexto_banco_horas.vinculo_id,
        bhPoliticaId=contexto_banco_horas.bh_politica_id,
        codigo="invalida",
        periodoInicio=dt.date(2026, 7, 1),
        periodoFim=dt.date(2026, 6, 1),
    )
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.criar_conta_banco_horas(
            sessao_banco_horas, contexto_banco_horas.tenant_id, dados
        )
    assert excinfo.value.codigo == "PONTO-VAL-001"


@pytest.mark.asyncio
async def test_obter_conta_banco_horas_inexistente_e_rec_001(
    sessao_banco_horas: AsyncSession, contexto_banco_horas: ContextoBancoHoras
) -> None:
    import uuid

    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.obter_conta_banco_horas(
            sessao_banco_horas, contexto_banco_horas.tenant_id, uuid.uuid4()
        )
    assert excinfo.value.codigo == "PONTO-REC-001"


@pytest.mark.asyncio
async def test_obter_conta_banco_horas_encontra_a_semeada(
    sessao_banco_horas: AsyncSession, contexto_banco_horas: ContextoBancoHoras
) -> None:
    conta = await servico.obter_conta_banco_horas(
        sessao_banco_horas, contexto_banco_horas.tenant_id, contexto_banco_horas.bh_conta_id
    )
    assert conta.id == contexto_banco_horas.bh_conta_id


@pytest.mark.asyncio
async def test_listar_contas_filtros_colaborador_vinculo_status_e_paginacao(
    sessao_banco_horas: AsyncSession, contexto_banco_horas: ContextoBancoHoras
) -> None:
    for codigo in ("extra-1", "extra-2"):
        await servico.criar_conta_banco_horas(
            sessao_banco_horas,
            contexto_banco_horas.tenant_id,
            esquemas.BhContaCriar(
                vinculoId=contexto_banco_horas.vinculo_id,
                bhPoliticaId=contexto_banco_horas.bh_politica_id,
                codigo=codigo,
                periodoInicio=dt.date(2026, 1, 1),
            ),
        )
    await sessao_banco_horas.flush()

    por_colaborador, _ = await servico.listar_contas_banco_horas(
        sessao_banco_horas,
        contexto_banco_horas.tenant_id,
        colaborador_id=contexto_banco_horas.colaborador_id,
    )
    assert len(por_colaborador) >= 3

    por_vinculo, _ = await servico.listar_contas_banco_horas(
        sessao_banco_horas,
        contexto_banco_horas.tenant_id,
        vinculo_id=contexto_banco_horas.vinculo_id,
    )
    assert len(por_vinculo) >= 3

    por_status, _ = await servico.listar_contas_banco_horas(
        sessao_banco_horas, contexto_banco_horas.tenant_id, status="aberta"
    )
    assert len(por_status) >= 3

    ate_dezembro, _ = await servico.listar_contas_banco_horas(
        sessao_banco_horas, contexto_banco_horas.tenant_id, vence_ate=dt.date(2026, 12, 31)
    )
    assert len(ate_dezembro) >= 3

    sem_saldo_negativo, _ = await servico.listar_contas_banco_horas(
        sessao_banco_horas, contexto_banco_horas.tenant_id, com_saldo_negativo=True
    )
    assert sem_saldo_negativo == []

    primeira_pagina, paginacao_1 = await servico.listar_contas_banco_horas(
        sessao_banco_horas,
        contexto_banco_horas.tenant_id,
        colaborador_id=contexto_banco_horas.colaborador_id,
        limite=1,
        ordenar="saldoAtualMinutos:asc",
    )
    assert len(primeira_pagina) == 1
    assert paginacao_1.tem_mais is True
    assert paginacao_1.proximo_cursor is not None

    segunda_pagina, _ = await servico.listar_contas_banco_horas(
        sessao_banco_horas,
        contexto_banco_horas.tenant_id,
        colaborador_id=contexto_banco_horas.colaborador_id,
        limite=1,
        ordenar="saldoAtualMinutos:asc",
        cursor=paginacao_1.proximo_cursor,
    )
    assert len(segunda_pagina) == 1
    assert segunda_pagina[0].id != primeira_pagina[0].id
