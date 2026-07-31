"""Dataset `atrasos-saidas-antecipadas` (item 7, `PROJETO.md` §9, dataset
`apuracao_dia_atrasos`) -- T8 do PCF F11/A2.

A semente comum de `tests/f11/conftest.py` não preenche `atraso_minutos`/
`saida_antecipada_minutos` (fica 0 por padrão) -- este módulo ajusta uma
linha localmente para exercitar o caso não trivial, mesma regra que a
docstring da fixture já autoriza.
"""

from __future__ import annotations

import sqlalchemy as sa
from ponto_contracts import ApuracaoDia
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.relatorios.motor import ContextoConsulta
from tests.f11.conftest import ContextoF11
from tests.f11.datasets_operacionais._apoio import executar


async def _marcar_atraso(sessao: AsyncSession, contexto_f11: ContextoF11) -> None:
    colaborador_a = contexto_f11.colaboradores[0]
    await sessao.execute(
        text(
            "UPDATE apuracoes_dia SET atraso_minutos = 10, saida_antecipada_minutos = 5, "
            "tolerancia_aplicada_minutos = 5 "
            "WHERE tenant_id = :tenant_id AND colaborador_id = :colaborador_id "
            "AND data = :data"
        ),
        {
            "tenant_id": contexto_f11.tenant_id,
            "colaborador_id": colaborador_a.colaborador_id,
            "data": contexto_f11.dias_uteis[0],
        },
    )
    await sessao.flush()


async def _soma_direta(sessao: AsyncSession, tenant_id: object, coluna: object) -> int:
    resultado = await sessao.execute(
        sa.select(sa.func.coalesce(sa.func.sum(coluna), 0)).where(
            ApuracaoDia.tenant_id == tenant_id
        )
    )
    return int(resultado.scalar_one())


async def test_soma_bate_com_apuracoes_dia(
    sessao_f11: AsyncSession, contexto_f11: ContextoF11
) -> None:
    await _marcar_atraso(sessao_f11, contexto_f11)
    contexto = ContextoConsulta(
        tenant_id=contexto_f11.tenant_id,
        de=contexto_f11.dias_uteis[0],
        ate=contexto_f11.dias_uteis[-1],
    )
    resultado = await executar(
        sessao_f11,
        contexto_f11.tenant_id,
        "atrasos-saidas-antecipadas",
        contexto_f11.relatorio_ids,
        filtros=contexto,
    )
    assert len(resultado.linhas) == 9
    soma_atraso = sum(linha["atrasoMinutos"] for linha in resultado.linhas)
    soma_saida_antecipada = sum(linha["saidaAntecipadaMinutos"] for linha in resultado.linhas)
    assert soma_atraso == 10
    assert soma_saida_antecipada == 5
    assert soma_atraso == await _soma_direta(
        sessao_f11, contexto_f11.tenant_id, ApuracaoDia.atraso_minutos
    )
    assert soma_saida_antecipada == await _soma_direta(
        sessao_f11, contexto_f11.tenant_id, ApuracaoDia.saida_antecipada_minutos
    )


async def test_filtro_somente_com_ocorrencia(
    sessao_f11: AsyncSession, contexto_f11: ContextoF11
) -> None:
    await _marcar_atraso(sessao_f11, contexto_f11)
    contexto = ContextoConsulta(
        tenant_id=contexto_f11.tenant_id,
        de=contexto_f11.dias_uteis[0],
        ate=contexto_f11.dias_uteis[-1],
        filtros={"somenteComOcorrencia": True},
    )
    resultado = await executar(
        sessao_f11,
        contexto_f11.tenant_id,
        "atrasos-saidas-antecipadas",
        contexto_f11.relatorio_ids,
        filtros=contexto,
    )
    assert len(resultado.linhas) == 1
    assert resultado.linhas[0]["atrasoMinutos"] == 10
