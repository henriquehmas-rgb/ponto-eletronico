"""Testes de `app.jornada.modelagem.horarios` (F3 / A1, T2).

Cobre os dois primeiros criterios de aceite da T2 (PCF secao 6): validacao de
`cruzaMeiaNoite` e a unicidade de `codigo` por empresa (`uq_horarios_codigo`).
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.erros import ErroDeAplicacao
from app.jornada.modelagem import horarios as servico
from app.schemas import contrato as esquemas
from tests.f3.conftest import ContextoF3

pytestmark = pytest.mark.asyncio


async def test_criar_horario_com_saida_menor_que_entrada_sem_cruza_meia_noite_e_recusado(
    sessao_f3: AsyncSession, contexto_f3: ContextoF3
) -> None:
    dados = esquemas.HorarioCriar(
        empresa_id=contexto_f3.empresa_id,
        codigo="HOR-NOTURNO-INVALIDO",
        nome="Horario noturno sem flag",
        entrada="22:00",
        saida="06:00",
        carga_minutos=480,
    )
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.criar_horario(sessao_f3, contexto_f3.tenant_id, dados)
    assert excinfo.value.codigo == "PONTO-VAL-001"


async def test_criar_horario_com_saida_menor_que_entrada_e_cruza_meia_noite_e_aceito(
    sessao_f3: AsyncSession, contexto_f3: ContextoF3
) -> None:
    dados = esquemas.HorarioCriar(
        empresa_id=contexto_f3.empresa_id,
        codigo="HOR-NOTURNO-VALIDO",
        nome="Horario noturno com flag",
        entrada="22:00",
        saida="06:00",
        cruza_meia_noite=True,
        carga_minutos=480,
    )
    horario = await servico.criar_horario(sessao_f3, contexto_f3.tenant_id, dados)
    assert horario.cruza_meia_noite is True
    assert horario.entrada is not None
    assert horario.saida is not None


async def test_dois_horarios_com_mesmo_codigo_na_mesma_empresa_colidem(
    sessao_f3: AsyncSession, contexto_f3: ContextoF3
) -> None:
    primeiro = esquemas.HorarioCriar(
        empresa_id=contexto_f3.empresa_id,
        codigo="HOR-DUPLICADO",
        nome="Primeiro",
        carga_minutos=480,
    )
    await servico.criar_horario(sessao_f3, contexto_f3.tenant_id, primeiro)
    await sessao_f3.flush()

    segundo = esquemas.HorarioCriar(
        empresa_id=contexto_f3.empresa_id,
        codigo="HOR-DUPLICADO",
        nome="Segundo",
        carga_minutos=480,
    )
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.criar_horario(sessao_f3, contexto_f3.tenant_id, segundo)
    assert excinfo.value.codigo == "PONTO-CONF-001"


async def test_atualizar_horario_inexistente_e_rec_001(
    sessao_f3: AsyncSession, contexto_f3: ContextoF3
) -> None:
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.atualizar_horario(
            sessao_f3, uuid.uuid4(), esquemas.HorarioAtualizar(nome="Novo nome")
        )
    assert excinfo.value.codigo == "PONTO-REC-001"


async def test_atualizar_horario_com_sucesso(
    sessao_f3: AsyncSession, contexto_f3: ContextoF3
) -> None:
    criado = esquemas.HorarioCriar(
        empresa_id=contexto_f3.empresa_id,
        codigo="HOR-ATUALIZAVEL",
        nome="Original",
        entrada="08:00",
        saida="17:00",
        carga_minutos=480,
    )
    horario = await servico.criar_horario(sessao_f3, contexto_f3.tenant_id, criado)
    await sessao_f3.flush()

    atualizado = await servico.atualizar_horario(
        sessao_f3, horario.id, esquemas.HorarioAtualizar(nome="Renomeado", carga_minutos=440)
    )
    assert atualizado.nome == "Renomeado"
    assert atualizado.carga_minutos == 440


async def test_atualizar_horario_para_saida_menor_sem_flag_e_recusado(
    sessao_f3: AsyncSession, contexto_f3: ContextoF3
) -> None:
    criado = esquemas.HorarioCriar(
        empresa_id=contexto_f3.empresa_id,
        codigo="HOR-VIRA-NOTURNO",
        nome="Diurno",
        entrada="08:00",
        saida="17:00",
        carga_minutos=480,
    )
    horario = await servico.criar_horario(sessao_f3, contexto_f3.tenant_id, criado)
    await sessao_f3.flush()

    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.atualizar_horario(
            sessao_f3, horario.id, esquemas.HorarioAtualizar(saida="04:00")
        )
    assert excinfo.value.codigo == "PONTO-VAL-001"


async def test_listar_horarios_filtra_e_pagina(
    sessao_f3: AsyncSession, contexto_f3: ContextoF3
) -> None:
    for i in range(3):
        dados = esquemas.HorarioCriar(
            empresa_id=contexto_f3.empresa_id,
            codigo=f"HOR-LISTA-{i}",
            nome=f"Horario {i}",
            carga_minutos=480,
            cruza_meia_noite=False,
        )
        await servico.criar_horario(sessao_f3, contexto_f3.tenant_id, dados)
    await sessao_f3.flush()

    primeira_pagina, paginacao = await servico.listar_horarios(
        sessao_f3,
        contexto_f3.tenant_id,
        empresa_id=contexto_f3.empresa_id,
        cruza_meia_noite=False,
        ativo=True,
        limite=2,
        ordenar="codigo:asc",
    )
    assert len(primeira_pagina) == 2
    assert paginacao.tem_mais is True
    assert paginacao.proximo_cursor is not None

    segunda_pagina, paginacao_2 = await servico.listar_horarios(
        sessao_f3,
        contexto_f3.tenant_id,
        empresa_id=contexto_f3.empresa_id,
        cursor=paginacao.proximo_cursor,
        limite=2,
        ordenar="codigo:asc",
    )
    assert len(segunda_pagina) >= 1
    ids_primeira = {h.id for h in primeira_pagina}
    ids_segunda = {h.id for h in segunda_pagina}
    assert ids_primeira.isdisjoint(ids_segunda)
