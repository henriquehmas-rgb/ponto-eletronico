"""Prova de fumaça da fixture compartilhada (T1): sobe/derruba o banco sem
erro e semeia exatamente o que a docstring de `conftest.py` promete.
"""

from __future__ import annotations

import sqlalchemy as sa
from ponto_contracts import RelatorioDefinicao
from sqlalchemy.ext.asyncio import AsyncSession

from tests.f11.conftest import ContextoF11


async def test_fixture_semeia_tenant_colaboradores_e_periodo(contexto_f11: ContextoF11) -> None:
    assert contexto_f11.tenant_id is not None
    assert len(contexto_f11.colaboradores) == 3
    assert len(contexto_f11.dias_uteis) == 3
    assert contexto_f11.periodo_data_inicio <= contexto_f11.dias_uteis[0]
    assert contexto_f11.dias_uteis[-1] <= contexto_f11.periodo_data_fim


async def test_fixture_semeia_os_24_relatorios(
    contexto_f11: ContextoF11, sessao_f11: AsyncSession
) -> None:
    assert len(contexto_f11.relatorio_ids) == 24
    linhas = (
        (
            await sessao_f11.execute(
                sa.select(RelatorioDefinicao).where(
                    RelatorioDefinicao.tenant_id == contexto_f11.tenant_id
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(linhas) == 24
    assert all(linha.sistema is True for linha in linhas)
    assert all(linha.ativo is True for linha in linhas)
    codigos = {linha.codigo for linha in linhas}
    assert codigos == set(contexto_f11.relatorio_ids)
    # O item 1 (espelho oficial) e o unico que so exporta PDF (T15).
    espelho_oficial = next(linha for linha in linhas if linha.codigo == "espelho-oficial")
    assert espelho_oficial.formatos == ["pdf"]


async def test_fixture_semeia_apuracao_sintetica_sem_apurar_dia(
    contexto_f11: ContextoF11, sessao_f11: AsyncSession
) -> None:
    from ponto_contracts import ApuracaoDia

    linhas = (
        (
            await sessao_f11.execute(
                sa.select(ApuracaoDia).where(ApuracaoDia.tenant_id == contexto_f11.tenant_id)
            )
        )
        .scalars()
        .all()
    )
    # 3 colaboradores x 3 dias uteis.
    assert len(linhas) == 9
    colaborador_b = contexto_f11.colaboradores[1]
    linhas_b = [linha for linha in linhas if linha.colaborador_id == colaborador_b.colaborador_id]
    assert len(linhas_b) == 3
    assert all(linha.extras_minutos == 60 for linha in linhas_b)
    assert all(linha.noturno_minutos == 15 for linha in linhas_b)
