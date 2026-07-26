"""Prova de vida da fixture da fase (T1): sobe o banco, semeia e derruba sem erro.

Nao testa nenhuma regra de negocio do motor de jornada -- so confirma que
`contexto_f3` semeia exatamente o que o PCF pede (T1 "pronto quando"): 1
tenant, 1 empresa, duas unidades em UFs diferentes e 3 vinculos com
`apura_ponto = TRUE`.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.f3.conftest import ContextoF3


async def test_contexto_f3_semeia_massa_minima(
    sessao_f3: AsyncSession, contexto_f3: ContextoF3
) -> None:
    assert contexto_f3.unidade_sp_uf != contexto_f3.unidade_ba_uf
    assert contexto_f3.unidade_sp_codigo_ibge != contexto_f3.unidade_ba_codigo_ibge

    linha = (
        await sessao_f3.execute(
            text("SELECT count(*) FROM vinculos WHERE tenant_id = :tid AND apura_ponto"),
            {"tid": str(contexto_f3.tenant_id)},
        )
    ).scalar_one()
    assert linha == 3

    linha_unidades = (
        await sessao_f3.execute(
            text("SELECT count(*) FROM unidades WHERE tenant_id = :tid"),
            {"tid": str(contexto_f3.tenant_id)},
        )
    ).scalar_one()
    assert linha_unidades == 2

    # `vinculo_sem_unidade` de fato nao tem unidade -- o caso de borda da
    # secao 2 do PCF (fuso efetivo cai para o da empresa).
    unidade_do_vinculo_sem_unidade = (
        await sessao_f3.execute(
            text("SELECT unidade_id FROM vinculos WHERE id = :vid"),
            {"vid": str(contexto_f3.vinculo_sem_unidade_id)},
        )
    ).scalar_one()
    assert unidade_do_vinculo_sem_unidade is None
