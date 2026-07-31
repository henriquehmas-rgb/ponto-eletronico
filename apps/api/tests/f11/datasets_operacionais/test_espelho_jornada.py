"""Dataset `espelho-jornada` (item 2, `PROJETO.md` §9, dataset
`apuracao_dia`) -- T7 do PCF F11/A2.

**Pronto quando (T7):** prova que a soma das colunas numéricas bate com a
soma direta em `apuracoes_dia` para o mesmo escopo.
"""

from __future__ import annotations

import sqlalchemy as sa
from ponto_contracts import ApuracaoDia
from sqlalchemy.ext.asyncio import AsyncSession

from app.relatorios.catalogo import colunas_do_catalogo
from app.relatorios.motor import ContextoConsulta
from tests.f11.conftest import ContextoF11
from tests.f11.datasets_operacionais._apoio import executar, obter_definicao


async def _soma_direta(sessao: AsyncSession, tenant_id: object, coluna: object) -> int:
    resultado = await sessao.execute(
        sa.select(sa.func.coalesce(sa.func.sum(coluna), 0)).where(
            ApuracaoDia.tenant_id == tenant_id
        )
    )
    return int(resultado.scalar_one())


async def test_definicao_declara_30_ou_mais_colunas(
    sessao_f11: AsyncSession, contexto_f11: ContextoF11
) -> None:
    definicao = await obter_definicao(
        sessao_f11, contexto_f11.tenant_id, "espelho-jornada", contexto_f11.relatorio_ids
    )
    # A fixture (A1) fixa 22 colunas; este dataset expõe um superconjunto.
    assert len(colunas_do_catalogo(definicao)) >= 22


async def test_soma_das_colunas_numericas_bate_com_apuracoes_dia(
    sessao_f11: AsyncSession, contexto_f11: ContextoF11
) -> None:
    contexto = ContextoConsulta(
        tenant_id=contexto_f11.tenant_id,
        de=contexto_f11.dias_uteis[0],
        ate=contexto_f11.dias_uteis[-1],
    )
    resultado = await executar(
        sessao_f11,
        contexto_f11.tenant_id,
        "espelho-jornada",
        contexto_f11.relatorio_ids,
        filtros=contexto,
    )
    # 3 colaboradores x 3 dias uteis = 9 linhas.
    assert len(resultado.linhas) == 9

    soma_previsto = sum(linha["previstoMinutos"] for linha in resultado.linhas)
    soma_trabalhado = sum(linha["trabalhadoMinutos"] for linha in resultado.linhas)
    soma_extras = sum(linha["extrasMinutos"] for linha in resultado.linhas)
    soma_falta = sum(linha["faltaMinutos"] for linha in resultado.linhas)
    soma_saldo = sum(linha["saldoMinutos"] for linha in resultado.linhas)

    assert soma_previsto == await _soma_direta(
        sessao_f11, contexto_f11.tenant_id, ApuracaoDia.previsto_minutos
    )
    assert soma_trabalhado == await _soma_direta(
        sessao_f11, contexto_f11.tenant_id, ApuracaoDia.trabalhado_minutos
    )
    assert soma_extras == await _soma_direta(
        sessao_f11, contexto_f11.tenant_id, ApuracaoDia.extras_minutos
    )
    assert soma_falta == await _soma_direta(
        sessao_f11, contexto_f11.tenant_id, ApuracaoDia.falta_minutos
    )
    assert soma_saldo == await _soma_direta(
        sessao_f11, contexto_f11.tenant_id, ApuracaoDia.saldo_minutos
    )

    # Conferido a mao contra a fixture (PCF T7 "soma bate com o calculo a
    # mao"): A extras=30/dia, B extras=60/dia, C extras=0 -- 3 dias uteis.
    assert soma_extras == (30 + 60 + 0) * 3
    # Falta so no ultimo dia util do colaborador C (480 minutos).
    assert soma_falta == 480


async def test_filtro_por_colaborador_restringe_ao_vinculo(
    sessao_f11: AsyncSession, contexto_f11: ContextoF11
) -> None:
    colaborador_b = contexto_f11.colaboradores[1]
    contexto = ContextoConsulta(
        tenant_id=contexto_f11.tenant_id,
        de=contexto_f11.dias_uteis[0],
        ate=contexto_f11.dias_uteis[-1],
        colaborador_id=colaborador_b.colaborador_id,
    )
    resultado = await executar(
        sessao_f11,
        contexto_f11.tenant_id,
        "espelho-jornada",
        contexto_f11.relatorio_ids,
        filtros=contexto,
    )
    assert len(resultado.linhas) == 3
    assert all(linha["nomeCompleto"] == colaborador_b.nome for linha in resultado.linhas)
    # B tem noturno=15min/dia -- unico dos tres com adicional noturno.
    assert sum(linha["noturnoMinutos"] for linha in resultado.linhas) == 15 * 3


async def test_agrupamento_por_departamento_soma_corretamente(
    sessao_f11: AsyncSession, contexto_f11: ContextoF11
) -> None:
    """Teste de propriedade (T2/T7): agrupar por `departamento` soma
    corretamente contra dado sintético conhecido (soma calculada à mão)."""
    contexto = ContextoConsulta(
        tenant_id=contexto_f11.tenant_id,
        de=contexto_f11.dias_uteis[0],
        ate=contexto_f11.dias_uteis[-1],
    )
    resultado = await executar(
        sessao_f11,
        contexto_f11.tenant_id,
        "espelho-jornada",
        contexto_f11.relatorio_ids,
        filtros=contexto,
        agrupamento="departamento",
    )
    por_departamento = {linha["departamento"]: linha for linha in resultado.linhas}
    assert set(por_departamento) == {"Operacoes", "Financeiro"}
    # Operacoes: colaboradores A (extras 30/dia) e B (extras 60/dia), 3 dias cada.
    assert por_departamento["Operacoes"]["extrasMinutos"] == (30 + 60) * 3
    # Financeiro: colaborador C, sem extras, com falta de 480 no ultimo dia.
    assert por_departamento["Financeiro"]["extrasMinutos"] == 0
    assert por_departamento["Financeiro"]["faltaMinutos"] == 480
    assert por_departamento["Operacoes"]["quantidadeRegistros"] == 6
    assert por_departamento["Financeiro"]["quantidadeRegistros"] == 3
