"""Testes de `app.workflow.fechamento.escopo` (F10/A2).

`resolver_vinculos_do_escopo` só era exercitado, antes deste arquivo, pelo
ramo `escopo='empresa'` (via `calcular_conferencia`/`criarFechamento`) --
nenhum teste cobria os outros quatro ramos (`unidade`/`departamento`/
`colaborador`/`equipe`) nem o valor de escopo inválido. Cobre aqui cada
ramo: a validação do parâmetro obrigatório ausente e o caminho feliz que
efetivamente resolve o vínculo esperado.
"""

from __future__ import annotations

import uuid

import pytest
from ponto_contracts import Departamento, Equipe, EquipeMembro

from app.core.erros import ErroDeAplicacao
from app.workflow.fechamento import escopo as escopo_modulo
from tests.f10.conftest import ContextoF10


@pytest.mark.asyncio
async def test_escopo_invalido_e_val_001(sessao_f10, contexto_f10: ContextoF10) -> None:
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await escopo_modulo.resolver_vinculos_do_escopo(
            sessao_f10,
            contexto_f10.tenant_id,
            escopo="planeta",
            empresa_id=contexto_f10.empresa_id,
        )
    assert excinfo.value.codigo == "PONTO-VAL-001"


@pytest.mark.asyncio
async def test_escopo_unidade_sem_unidade_id_e_recusado(
    sessao_f10, contexto_f10: ContextoF10
) -> None:
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await escopo_modulo.resolver_vinculos_do_escopo(
            sessao_f10, contexto_f10.tenant_id, escopo="unidade", empresa_id=contexto_f10.empresa_id
        )
    assert excinfo.value.codigo == "PONTO-VAL-001"


@pytest.mark.asyncio
async def test_escopo_unidade_resolve_o_vinculo_da_unidade(
    sessao_f10, contexto_f10: ContextoF10
) -> None:
    vinculos = await escopo_modulo.resolver_vinculos_do_escopo(
        sessao_f10,
        contexto_f10.tenant_id,
        escopo="unidade",
        empresa_id=contexto_f10.empresa_id,
        unidade_id=contexto_f10.unidade_id,
    )
    assert [v.id for v in vinculos] == [contexto_f10.vinculo_id]


@pytest.mark.asyncio
async def test_escopo_departamento_sem_departamento_id_e_recusado(
    sessao_f10, contexto_f10: ContextoF10
) -> None:
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await escopo_modulo.resolver_vinculos_do_escopo(
            sessao_f10,
            contexto_f10.tenant_id,
            escopo="departamento",
            empresa_id=contexto_f10.empresa_id,
        )
    assert excinfo.value.codigo == "PONTO-VAL-001"


@pytest.mark.asyncio
async def test_escopo_departamento_resolve_o_vinculo_do_departamento(
    sessao_f10, contexto_f10: ContextoF10
) -> None:
    departamento_id = uuid.uuid4()
    sessao_f10.add(
        Departamento(
            id=departamento_id,
            tenant_id=contexto_f10.tenant_id,
            empresa_id=contexto_f10.empresa_id,
            codigo=f"DEP-{uuid.uuid4().hex[:8]}",
            nome="Departamento de Teste F10 (escopo)",
        )
    )
    await sessao_f10.flush()
    from ponto_contracts import Vinculo

    vinculo = await sessao_f10.get(Vinculo, contexto_f10.vinculo_id)
    assert vinculo is not None
    vinculo.departamento_id = departamento_id
    await sessao_f10.flush()

    vinculos = await escopo_modulo.resolver_vinculos_do_escopo(
        sessao_f10,
        contexto_f10.tenant_id,
        escopo="departamento",
        empresa_id=contexto_f10.empresa_id,
        departamento_id=departamento_id,
    )
    assert [v.id for v in vinculos] == [contexto_f10.vinculo_id]


@pytest.mark.asyncio
async def test_escopo_colaborador_sem_colaborador_id_e_recusado(
    sessao_f10, contexto_f10: ContextoF10
) -> None:
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await escopo_modulo.resolver_vinculos_do_escopo(
            sessao_f10,
            contexto_f10.tenant_id,
            escopo="colaborador",
            empresa_id=contexto_f10.empresa_id,
        )
    assert excinfo.value.codigo == "PONTO-VAL-001"


@pytest.mark.asyncio
async def test_escopo_colaborador_resolve_o_vinculo_do_colaborador(
    sessao_f10, contexto_f10: ContextoF10
) -> None:
    vinculos = await escopo_modulo.resolver_vinculos_do_escopo(
        sessao_f10,
        contexto_f10.tenant_id,
        escopo="colaborador",
        empresa_id=contexto_f10.empresa_id,
        colaborador_id=contexto_f10.colaborador_id,
    )
    assert [v.id for v in vinculos] == [contexto_f10.vinculo_id]


@pytest.mark.asyncio
async def test_escopo_equipe_sem_equipe_id_e_recusado(
    sessao_f10, contexto_f10: ContextoF10
) -> None:
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await escopo_modulo.resolver_vinculos_do_escopo(
            sessao_f10, contexto_f10.tenant_id, escopo="equipe", empresa_id=contexto_f10.empresa_id
        )
    assert excinfo.value.codigo == "PONTO-VAL-001"


@pytest.mark.asyncio
async def test_escopo_equipe_resolve_o_vinculo_do_membro_vigente_no_periodo(
    sessao_f10, contexto_f10: ContextoF10
) -> None:
    """Cobre `equipe_membros` com `periodo_inicio`/`periodo_fim` informados
    (os dois ramos de vigência da subconsulta, escopo.py linhas 87-96)."""
    equipe_id = uuid.uuid4()
    sessao_f10.add(
        Equipe(
            id=equipe_id,
            tenant_id=contexto_f10.tenant_id,
            empresa_id=contexto_f10.empresa_id,
            codigo=f"EQP-{uuid.uuid4().hex[:8]}",
            nome="Equipe de Teste F10 (escopo)",
        )
    )
    await sessao_f10.flush()
    sessao_f10.add(
        EquipeMembro(
            id=uuid.uuid4(),
            tenant_id=contexto_f10.tenant_id,
            equipe_id=equipe_id,
            colaborador_id=contexto_f10.colaborador_id,
            papel="membro",
            vigencia_inicio=contexto_f10.periodo_data_inicio,
            vigencia_fim=None,
        )
    )
    await sessao_f10.flush()

    vinculos = await escopo_modulo.resolver_vinculos_do_escopo(
        sessao_f10,
        contexto_f10.tenant_id,
        escopo="equipe",
        empresa_id=contexto_f10.empresa_id,
        equipe_id=equipe_id,
        periodo_inicio=contexto_f10.periodo_data_inicio,
        periodo_fim=contexto_f10.periodo_data_fim,
    )
    assert [v.id for v in vinculos] == [contexto_f10.vinculo_id]


@pytest.mark.asyncio
async def test_escopo_equipe_nao_resolve_membro_fora_da_vigencia(
    sessao_f10, contexto_f10: ContextoF10
) -> None:
    """Prova negativa: um membro cuja vigência terminou antes do período
    filtrado não deve ser resolvido (garante que a subconsulta de vigência
    de fato filtra, não só "sempre inclui")."""
    import datetime as dt

    equipe_id = uuid.uuid4()
    sessao_f10.add(
        Equipe(
            id=equipe_id,
            tenant_id=contexto_f10.tenant_id,
            empresa_id=contexto_f10.empresa_id,
            codigo=f"EQP-{uuid.uuid4().hex[:8]}",
            nome="Equipe de Teste F10 (escopo, vigencia encerrada)",
        )
    )
    await sessao_f10.flush()
    sessao_f10.add(
        EquipeMembro(
            id=uuid.uuid4(),
            tenant_id=contexto_f10.tenant_id,
            equipe_id=equipe_id,
            colaborador_id=contexto_f10.colaborador_id,
            papel="membro",
            vigencia_inicio=dt.date(2019, 1, 1),
            vigencia_fim=dt.date(2019, 12, 31),
        )
    )
    await sessao_f10.flush()

    vinculos = await escopo_modulo.resolver_vinculos_do_escopo(
        sessao_f10,
        contexto_f10.tenant_id,
        escopo="equipe",
        empresa_id=contexto_f10.empresa_id,
        equipe_id=equipe_id,
        periodo_inicio=contexto_f10.periodo_data_inicio,
        periodo_fim=contexto_f10.periodo_data_fim,
    )
    assert vinculos == []


def test_dias_do_intervalo_inclusive() -> None:
    import datetime as dt

    dias = escopo_modulo.dias_do_intervalo(dt.date(2026, 1, 1), dt.date(2026, 1, 3))
    assert dias == [dt.date(2026, 1, 1), dt.date(2026, 1, 2), dt.date(2026, 1, 3)]
