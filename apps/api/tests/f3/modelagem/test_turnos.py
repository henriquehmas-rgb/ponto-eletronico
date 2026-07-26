"""Testes de `app.jornada.modelagem.turnos` (F3 / A1, T3).

`turnos` e o horario nomeado e sequenciado para revezamento -- cobertura de
CRUD basico e da unicidade de `codigo` por empresa (`uq_turnos_codigo`)."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.erros import ErroDeAplicacao
from app.jornada.modelagem import turnos as servico
from app.schemas import contrato as esquemas
from tests.f3.conftest import ContextoF3


async def test_criar_turno_e_listar(sessao_f3: AsyncSession, contexto_f3: ContextoF3) -> None:
    dados = esquemas.TurnoCriar(
        empresa_id=contexto_f3.empresa_id,
        codigo="TURNO-MANHA",
        nome="Turno da manha",
        tipo=esquemas.Tipo17.diurno,
    )
    turno = await servico.criar_turno(sessao_f3, contexto_f3.tenant_id, dados)
    await sessao_f3.flush()
    assert turno.codigo == "TURNO-MANHA"

    linhas, paginacao = await servico.listar_turnos(
        sessao_f3, contexto_f3.tenant_id, empresa_id=contexto_f3.empresa_id
    )
    assert any(t.id == turno.id for t in linhas)
    assert paginacao.limite == 50


async def test_dois_turnos_com_mesmo_codigo_colidem(
    sessao_f3: AsyncSession, contexto_f3: ContextoF3
) -> None:
    primeiro = esquemas.TurnoCriar(
        empresa_id=contexto_f3.empresa_id, codigo="TURNO-DUP", nome="Primeiro"
    )
    await servico.criar_turno(sessao_f3, contexto_f3.tenant_id, primeiro)
    await sessao_f3.flush()

    segundo = esquemas.TurnoCriar(
        empresa_id=contexto_f3.empresa_id, codigo="TURNO-DUP", nome="Segundo"
    )
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.criar_turno(sessao_f3, contexto_f3.tenant_id, segundo)
    assert excinfo.value.codigo == "PONTO-CONF-001"


async def test_atualizar_turno(sessao_f3: AsyncSession, contexto_f3: ContextoF3) -> None:
    dados = esquemas.TurnoCriar(
        empresa_id=contexto_f3.empresa_id, codigo="TURNO-ATUALIZAR", nome="Original"
    )
    turno = await servico.criar_turno(sessao_f3, contexto_f3.tenant_id, dados)
    await sessao_f3.flush()

    # `TurnoAtualizar` nao expoe `sequencia` no contrato (so `Turno`, a
    # resposta, tem esse campo) -- atualizavel apenas via corpo aceito.
    atualizado = await servico.atualizar_turno(
        sessao_f3, turno.id, esquemas.TurnoAtualizar(nome="Atualizado", cor="#112233")
    )
    assert atualizado.nome == "Atualizado"
    assert atualizado.cor == "#112233"


async def test_atualizar_turno_inexistente_e_rec_001(
    sessao_f3: AsyncSession, contexto_f3: ContextoF3
) -> None:
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.atualizar_turno(
            sessao_f3, uuid.uuid4(), esquemas.TurnoAtualizar(nome="Nao existe")
        )
    assert excinfo.value.codigo == "PONTO-REC-001"


async def test_listar_turnos_filtra_por_tipo_e_ativo(
    sessao_f3: AsyncSession, contexto_f3: ContextoF3
) -> None:
    ativo = esquemas.TurnoCriar(
        empresa_id=contexto_f3.empresa_id,
        codigo="TURNO-NOTURNO-ATIVO",
        nome="Noturno ativo",
        tipo=esquemas.Tipo17.noturno,
        ativo=True,
    )
    inativo = esquemas.TurnoCriar(
        empresa_id=contexto_f3.empresa_id,
        codigo="TURNO-NOTURNO-INATIVO",
        nome="Noturno inativo",
        tipo=esquemas.Tipo17.noturno,
        ativo=False,
    )
    await servico.criar_turno(sessao_f3, contexto_f3.tenant_id, ativo)
    await servico.criar_turno(sessao_f3, contexto_f3.tenant_id, inativo)
    await sessao_f3.flush()

    linhas, _ = await servico.listar_turnos(
        sessao_f3,
        contexto_f3.tenant_id,
        empresa_id=contexto_f3.empresa_id,
        tipo="noturno",
        ativo=True,
    )
    codigos = {t.codigo for t in linhas}
    assert "TURNO-NOTURNO-ATIVO" in codigos
    assert "TURNO-NOTURNO-INATIVO" not in codigos
