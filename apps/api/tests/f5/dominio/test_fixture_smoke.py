"""Fumaca da fixture da fase (T1): sobe, semeia e derruba sem erro.

Prova, minimamente, que `contexto_f5` semeia exatamente o que o PCF pede:
tenant, empresa, unidade (com geocerca e allowlist), REP-P ativo (com
`nsr_sequencias` correspondente), colaborador com vinculo `apura_ponto=true`
ativo, e dispositivo `celular` com `dispositivo_vinculos` ativo.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.f5.conftest import ContextoF5


async def test_fixture_sobe_e_semeia_sem_erro(
    sessao_f5: AsyncSession, contexto_f5: ContextoF5
) -> None:
    assert contexto_f5.tenant_id is not None
    assert contexto_f5.rep_p_id is not None

    tenant = (
        await sessao_f5.execute(
            text("SELECT status FROM tenants WHERE id = :id"), {"id": contexto_f5.tenant_id}
        )
    ).first()
    assert tenant is not None and tenant.status == "ativo"

    rep_p = (
        await sessao_f5.execute(
            text("SELECT status FROM rep_ps WHERE id = :id"), {"id": contexto_f5.rep_p_id}
        )
    ).first()
    assert rep_p is not None and rep_p.status == "ativo"

    sequencia = (
        await sessao_f5.execute(
            text(
                "SELECT proximo_nsr, ultimo_nsr_emitido FROM nsr_sequencias " "WHERE rep_p_id = :id"
            ),
            {"id": contexto_f5.rep_p_id},
        )
    ).first()
    assert sequencia is not None
    assert sequencia.proximo_nsr == 1
    assert sequencia.ultimo_nsr_emitido == 0

    vinculo = (
        await sessao_f5.execute(
            text("SELECT apura_ponto, status FROM vinculos WHERE id = :id"),
            {"id": contexto_f5.vinculo_id},
        )
    ).first()
    assert vinculo is not None
    assert vinculo.apura_ponto is True
    assert vinculo.status == "ativo"

    dispositivo_vinculo = (
        await sessao_f5.execute(
            text("SELECT status FROM dispositivo_vinculos WHERE id = :id"),
            {"id": contexto_f5.dispositivo_vinculo_id},
        )
    ).first()
    assert dispositivo_vinculo is not None
    assert dispositivo_vinculo.status == "ativo"

    rede = (
        await sessao_f5.execute(
            text("SELECT cidr FROM redes_permitidas WHERE unidade_id = :id"),
            {"id": contexto_f5.unidade_id},
        )
    ).first()
    assert rede is not None
