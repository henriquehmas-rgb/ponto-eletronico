"""Dataset `adicional-noturno` (item 5, `PROJETO.md` §9, dataset
`apuracao_componentes_noturno`) -- T7 do PCF F11/A2.

**Pronto quando (T7):** prova que a soma das colunas numéricas bate com a
soma direta em `apuracao_componentes` para o mesmo escopo.
"""

from __future__ import annotations

import sqlalchemy as sa
from ponto_contracts import ApuracaoComponente
from sqlalchemy.ext.asyncio import AsyncSession

from app.relatorios.motor import ContextoConsulta
from tests.f11.conftest import ContextoF11
from tests.f11.datasets_operacionais._apoio import executar


async def _soma_direta_noturno(sessao: AsyncSession, tenant_id: object) -> int:
    resultado = await sessao.execute(
        sa.select(sa.func.coalesce(sa.func.sum(ApuracaoComponente.minutos), 0)).where(
            ApuracaoComponente.tenant_id == tenant_id, ApuracaoComponente.categoria == "noturno"
        )
    )
    return int(resultado.scalar_one())


async def test_soma_minutos_bate_com_apuracao_componentes_categoria_noturno(
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
        "adicional-noturno",
        contexto_f11.relatorio_ids,
        filtros=contexto,
    )
    # So o colaborador B tem noturno (15min/dia x 3 dias) -- A e C nao geram componente.
    assert len(resultado.linhas) == 3
    assert all(linha["colaboradorNome"] == colaborador_b.nome for linha in resultado.linhas)
    soma_minutos = sum(linha["minutos"] for linha in resultado.linhas)
    assert soma_minutos == 15 * 3
    assert soma_minutos == await _soma_direta_noturno(sessao_f11, contexto_f11.tenant_id)
