"""Dataset `horas-extras` (item 4, `PROJETO.md` §9, dataset
`apuracao_componentes_extra`) -- T7 do PCF F11/A2.

**Pronto quando (T7):** prova que a soma das colunas numéricas bate com a
soma direta em `apuracao_componentes` para o mesmo escopo.
"""

from __future__ import annotations

import sqlalchemy as sa
from ponto_contracts import ApuracaoComponente
from sqlalchemy.ext.asyncio import AsyncSession

from app.relatorios.datasets.operacionais import horas_extras
from app.relatorios.motor import ContextoConsulta
from tests.f11.conftest import ContextoF11
from tests.f11.datasets_operacionais._apoio import executar, executar_bruto


async def _soma_direta_extra(sessao: AsyncSession, tenant_id: object) -> int:
    resultado = await sessao.execute(
        sa.select(sa.func.coalesce(sa.func.sum(ApuracaoComponente.minutos), 0)).where(
            ApuracaoComponente.tenant_id == tenant_id, ApuracaoComponente.categoria == "extra"
        )
    )
    return int(resultado.scalar_one())


async def test_soma_minutos_bate_com_apuracao_componentes_categoria_extra(
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
        "horas-extras",
        contexto_f11.relatorio_ids,
        filtros=contexto,
    )
    # A (30min x 3 dias) + B (60min x 3 dias) = 6 linhas; C nao gera componente.
    assert len(resultado.linhas) == 6
    soma_minutos = sum(linha["minutos"] for linha in resultado.linhas)
    assert soma_minutos == (30 + 60) * 3
    assert soma_minutos == await _soma_direta_extra(sessao_f11, contexto_f11.tenant_id)

    # `codigo` não está em `colunas_disponiveis` da fixture (T1/A1) -- chama
    # a função de consulta diretamente para conferir a rubrica gravada.
    linhas_brutas = await executar_bruto(
        sessao_f11, contexto_f11.tenant_id, horas_extras, filtros=contexto
    )
    assert all(linha["codigo"] == "he50" for linha in linhas_brutas)


async def test_agrupamento_por_colaborador(
    sessao_f11: AsyncSession, contexto_f11: ContextoF11
) -> None:
    colaborador_b = contexto_f11.colaboradores[1]
    contexto = ContextoConsulta(
        tenant_id=contexto_f11.tenant_id,
        de=contexto_f11.dias_uteis[0],
        ate=contexto_f11.dias_uteis[-1],
    )
    resultado = await executar(
        sessao_f11,
        contexto_f11.tenant_id,
        "horas-extras",
        contexto_f11.relatorio_ids,
        filtros=contexto,
        agrupamento="colaborador",
    )
    por_colaborador = {linha["colaborador"]: linha for linha in resultado.linhas}
    assert por_colaborador[colaborador_b.colaborador_id]["minutos"] == 60 * 3
    assert por_colaborador[colaborador_b.colaborador_id]["quantidadeRegistros"] == 3
