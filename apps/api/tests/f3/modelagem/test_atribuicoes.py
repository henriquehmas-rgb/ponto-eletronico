"""Testes de `app.jornada.modelagem.vinculo_jornadas` e
`app.jornada.modelagem.escala_atribuicoes` (F3 / A1, T4).

Cobre vigencia sem sobreposicao (`PONTO-VAL-010`, criterio de aceite 8) e a
consulta de `PONTO-PER-001` (que nunca derruba a operacao nesta fase, porque
nenhuma fase anterior popula `fechamentos`)."""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
from ponto_contracts import VinculoJornada
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.erros import ErroDeAplicacao
from app.jornada.modelagem import escala_atribuicoes, escalas, jornadas
from app.jornada.modelagem import vinculo_jornadas as servico
from app.schemas import contrato as esquemas
from tests.f3.conftest import ContextoF3


async def _criar_jornada_livre(
    sessao: AsyncSession, contexto: ContextoF3, codigo: str, vigencia_inicio: dt.date
):
    dados = esquemas.JornadaCriar(
        empresa_id=contexto.empresa_id,
        codigo=codigo,
        nome=f"Jornada {codigo}",
        tipo=esquemas.Tipo14.livre,
        vigencia_inicio=vigencia_inicio,
    )
    nova = await jornadas.criar_jornada(sessao, contexto.tenant_id, dados)
    await sessao.flush()
    return nova


async def test_atribuir_segunda_jornada_com_vigencia_sobreposta_e_recusado(
    sessao_f3: AsyncSession, contexto_f3: ContextoF3
) -> None:
    jornada_a = await _criar_jornada_livre(sessao_f3, contexto_f3, "JOR-VIG-A", dt.date(2026, 1, 1))
    jornada_b = await _criar_jornada_livre(sessao_f3, contexto_f3, "JOR-VIG-B", dt.date(2026, 1, 1))

    primeira = esquemas.VinculoJornadaCriar(
        jornada_id=jornada_a.id, vigencia_inicio=dt.date(2026, 1, 1)
    )
    await servico.atribuir_jornada_vinculo(
        sessao_f3, contexto_f3.tenant_id, contexto_f3.vinculo_sp_id, primeira
    )
    await sessao_f3.flush()

    segunda = esquemas.VinculoJornadaCriar(
        jornada_id=jornada_b.id, vigencia_inicio=dt.date(2026, 1, 15)
    )
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.atribuir_jornada_vinculo(
            sessao_f3, contexto_f3.tenant_id, contexto_f3.vinculo_sp_id, segunda
        )
    assert excinfo.value.codigo == "PONTO-VAL-010"


async def test_encerrar_a_primeira_libera_a_atribuicao_seguinte(
    sessao_f3: AsyncSession, contexto_f3: ContextoF3
) -> None:
    jornada_antiga = await _criar_jornada_livre(
        sessao_f3, contexto_f3, "JOR-TROCA-ANTIGA", dt.date(2026, 1, 1)
    )
    jornada_nova = await _criar_jornada_livre(
        sessao_f3, contexto_f3, "JOR-TROCA-NOVA", dt.date(2026, 1, 1)
    )

    primeira = esquemas.VinculoJornadaCriar(
        jornada_id=jornada_antiga.id,
        vigencia_inicio=dt.date(2026, 1, 1),
        vigencia_fim=dt.date(2026, 1, 14),
    )
    await servico.atribuir_jornada_vinculo(
        sessao_f3, contexto_f3.tenant_id, contexto_f3.vinculo_ba_id, primeira
    )
    await sessao_f3.flush()

    segunda = esquemas.VinculoJornadaCriar(
        jornada_id=jornada_nova.id, vigencia_inicio=dt.date(2026, 1, 15)
    )
    # Nao levanta: a vigencia da primeira ja fechou em 14/01, a partir de
    # 15/01 nao ha mais sobreposicao.
    atribuicao_nova = await servico.atribuir_jornada_vinculo(
        sessao_f3, contexto_f3.tenant_id, contexto_f3.vinculo_ba_id, segunda
    )
    assert atribuicao_nova.vigencia_inicio == dt.date(2026, 1, 15)

    # O dia anterior a troca (13/01) ainda resolve para a jornada antiga; o
    # dia da troca em diante (15/01), para a nova -- nenhuma reescrita do
    # passado (criterio de aceite 4).
    vigente_em_13 = await sessao_f3.execute(
        select(VinculoJornada).where(
            VinculoJornada.vinculo_id == contexto_f3.vinculo_ba_id,
            VinculoJornada.vigencia_inicio <= dt.date(2026, 1, 13),
        )
    )
    linha_13 = vigente_em_13.scalars().one()
    assert linha_13.jornada_id == jornada_antiga.id


async def test_atribuir_jornada_a_vinculo_inexistente_e_rec_001(
    sessao_f3: AsyncSession, contexto_f3: ContextoF3
) -> None:
    jornada = await _criar_jornada_livre(
        sessao_f3, contexto_f3, "JOR-VINCULO-INEXISTENTE", dt.date(2026, 1, 1)
    )
    dados = esquemas.VinculoJornadaCriar(jornada_id=jornada.id, vigencia_inicio=dt.date(2026, 1, 1))
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.atribuir_jornada_vinculo(
            sessao_f3, contexto_f3.tenant_id, uuid.uuid4(), dados
        )
    assert excinfo.value.codigo == "PONTO-REC-001"


async def test_consulta_de_periodo_fechado_nao_derruba_quando_nao_ha_fechamentos(
    sessao_f3: AsyncSession, contexto_f3: ContextoF3
) -> None:
    """Como nenhuma fase anterior a F3 popula `fechamentos`, a consulta de
    `PONTO-PER-001` nunca encontra nada hoje -- mas o codigo precisa rodar
    sem erro (PCF T4, "pronto quando")."""
    jornada = await _criar_jornada_livre(
        sessao_f3, contexto_f3, "JOR-SEM-FECHAMENTO", dt.date(2026, 1, 1)
    )
    dados = esquemas.VinculoJornadaCriar(jornada_id=jornada.id, vigencia_inicio=dt.date(2026, 1, 1))
    atribuicao = await servico.atribuir_jornada_vinculo(
        sessao_f3, contexto_f3.tenant_id, contexto_f3.vinculo_sem_unidade_id, dados
    )
    assert atribuicao.jornada_id == jornada.id


async def test_listar_jornadas_vinculo_com_vigente_em(
    sessao_f3: AsyncSession, contexto_f3: ContextoF3
) -> None:
    antiga = await _criar_jornada_livre(
        sessao_f3, contexto_f3, "JOR-HIST-ANTIGA", dt.date(2026, 1, 1)
    )
    nova = await _criar_jornada_livre(sessao_f3, contexto_f3, "JOR-HIST-NOVA", dt.date(2026, 1, 1))

    await servico.atribuir_jornada_vinculo(
        sessao_f3,
        contexto_f3.tenant_id,
        contexto_f3.vinculo_sp_id,
        esquemas.VinculoJornadaCriar(
            jornada_id=antiga.id,
            vigencia_inicio=dt.date(2026, 1, 1),
            vigencia_fim=dt.date(2026, 1, 31),
        ),
    )
    await sessao_f3.flush()
    await servico.atribuir_jornada_vinculo(
        sessao_f3,
        contexto_f3.tenant_id,
        contexto_f3.vinculo_sp_id,
        esquemas.VinculoJornadaCriar(jornada_id=nova.id, vigencia_inicio=dt.date(2026, 2, 1)),
    )
    await sessao_f3.flush()

    todas, paginacao = await servico.listar_jornadas_vinculo(
        sessao_f3, contexto_f3.tenant_id, contexto_f3.vinculo_sp_id
    )
    assert len(todas) == 2
    assert paginacao.limite == 50

    so_vigente_em_janeiro, _ = await servico.listar_jornadas_vinculo(
        sessao_f3,
        contexto_f3.tenant_id,
        contexto_f3.vinculo_sp_id,
        vigente_em=dt.date(2026, 1, 15),
    )
    assert len(so_vigente_em_janeiro) == 1
    assert so_vigente_em_janeiro[0].jornada_id == antiga.id


async def test_listar_jornadas_vinculo_de_vinculo_inexistente_e_rec_001(
    sessao_f3: AsyncSession, contexto_f3: ContextoF3
) -> None:
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.listar_jornadas_vinculo(sessao_f3, contexto_f3.tenant_id, uuid.uuid4())
    assert excinfo.value.codigo == "PONTO-REC-001"


# ---------------------------------------------------------------------------
# escala_atribuicoes
# ---------------------------------------------------------------------------


async def _criar_escala_12x36(sessao: AsyncSession, contexto: ContextoF3, codigo: str):
    dados = esquemas.EscalaCriar(
        empresa_id=contexto.empresa_id,
        codigo=codigo,
        nome=f"Escala {codigo}",
        tipo=esquemas.Tipo20.field_12x36,
        dias_ciclo=2,
        data_referencia=dt.date(2026, 1, 1),
        ciclos=[
            esquemas.EscalaCiclo(posicao=1, tipo_dia=esquemas.TipoDia1.trabalho, carga_minutos=720),
            esquemas.EscalaCiclo(posicao=2, tipo_dia=esquemas.TipoDia1.folga, carga_minutos=0),
        ],
    )
    nova = await escalas.criar_escala(sessao, contexto.tenant_id, dados)
    await sessao.flush()
    return nova


async def test_atribuir_escala_com_vigencia_sobreposta_e_recusado(
    sessao_f3: AsyncSession, contexto_f3: ContextoF3
) -> None:
    escala = await _criar_escala_12x36(sessao_f3, contexto_f3, "ESC-ATRIB-VIG")

    primeira = esquemas.EscalaAtribuicaoCriar(
        vinculo_id=contexto_f3.vinculo_ba_id, vigencia_inicio=dt.date(2026, 1, 1)
    )
    await escala_atribuicoes.atribuir_escala_vinculo(
        sessao_f3, contexto_f3.tenant_id, escala.id, primeira
    )
    await sessao_f3.flush()

    segunda = esquemas.EscalaAtribuicaoCriar(
        vinculo_id=contexto_f3.vinculo_ba_id, vigencia_inicio=dt.date(2026, 1, 10)
    )
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await escala_atribuicoes.atribuir_escala_vinculo(
            sessao_f3, contexto_f3.tenant_id, escala.id, segunda
        )
    assert excinfo.value.codigo == "PONTO-VAL-010"


async def test_atribuir_escala_com_posicao_inicial_desencontrada(
    sessao_f3: AsyncSession, contexto_f3: ContextoF3
) -> None:
    escala = await _criar_escala_12x36(sessao_f3, contexto_f3, "ESC-ATRIB-POSICAO")

    dados = esquemas.EscalaAtribuicaoCriar(
        vinculo_id=contexto_f3.vinculo_sp_id,
        vigencia_inicio=dt.date(2026, 1, 1),
        posicao_inicial=2,
    )
    atribuicao = await escala_atribuicoes.atribuir_escala_vinculo(
        sessao_f3, contexto_f3.tenant_id, escala.id, dados
    )
    assert atribuicao.posicao_inicial == 2
