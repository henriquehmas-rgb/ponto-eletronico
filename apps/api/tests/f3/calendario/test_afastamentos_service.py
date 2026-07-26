"""Testes de `app.jornada.calendario.afastamentos` contra o banco real (T6).

Cobre os dois lados da constraint `ex_afastamentos_sobreposicao`, a validacao
de `ck_afastamentos_parcial`/`ck_afastamentos_periodo`, a transicao de
`status` (`PONTO-CONF-003`) e que a consulta de `PONTO-PER-001` nao derruba a
operacao quando nao ha nenhum `fechamentos` na base (caminho sempre
verdadeiro nesta fase, ja que a F10 nao existe ainda).
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.erros import ErroDeAplicacao
from app.jornada.calendario import afastamentos as servico
from app.schemas import contrato as esquemas
from tests.f3.conftest import ContextoF3

pytestmark = pytest.mark.asyncio


async def _criar_tipo(
    sessao: AsyncSession, contexto: ContextoF3, codigo: str = "FERIAS-TESTE"
) -> esquemas.TipoAfastamento:
    return await servico.criar_tipo_afastamento(
        sessao,
        contexto.tenant_id,
        esquemas.TipoAfastamentoCriar(
            codigo=codigo, nome="Ferias de teste", categoria=esquemas.Categoria2.ferias
        ),
    )


async def test_criar_e_listar_tipo_afastamento(
    sessao_f3: AsyncSession, contexto_f3: ContextoF3
) -> None:
    tipo = await _criar_tipo(sessao_f3, contexto_f3, "FERIAS-LISTAR")
    linhas, _ = await servico.listar_tipos_afastamento(sessao_f3, contexto_f3.tenant_id)
    assert any(t.id == tipo.id for t in linhas)


async def test_atualizar_tipo_afastamento(sessao_f3: AsyncSession, contexto_f3: ContextoF3) -> None:
    tipo = await _criar_tipo(sessao_f3, contexto_f3, "FERIAS-ATUALIZAR")
    atualizado = await servico.atualizar_tipo_afastamento(
        sessao_f3,
        contexto_f3.tenant_id,
        tipo.id,
        esquemas.TipoAfastamentoAtualizar(nome="Ferias renomeadas"),
    )
    assert atualizado.nome == "Ferias renomeadas"


async def test_tipo_afastamento_codigo_duplicado_e_conf_001(
    sessao_f3: AsyncSession, contexto_f3: ContextoF3
) -> None:
    await _criar_tipo(sessao_f3, contexto_f3, "DUP-TIPO")
    await sessao_f3.flush()
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await _criar_tipo(sessao_f3, contexto_f3, "DUP-TIPO")
    assert excinfo.value.codigo == "PONTO-CONF-001"


async def test_afastamento_parcial_sem_horas_e_val_001(
    sessao_f3: AsyncSession, contexto_f3: ContextoF3
) -> None:
    tipo = await _criar_tipo(sessao_f3, contexto_f3, "PARCIAL-SEM-HORA")
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.criar_afastamento(
            sessao_f3,
            contexto_f3.tenant_id,
            esquemas.AfastamentoCriar(
                colaborador_id=contexto_f3.colaborador_sp_id,
                tipo_afastamento_id=tipo.id,
                data_inicio=dt.date(2024, 3, 1),
                periodo_parcial=True,
            ),
        )
    assert excinfo.value.codigo == "PONTO-VAL-001"


async def test_afastamento_periodo_invertido_e_val_007(
    sessao_f3: AsyncSession, contexto_f3: ContextoF3
) -> None:
    tipo = await _criar_tipo(sessao_f3, contexto_f3, "PERIODO-INVERTIDO")
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.criar_afastamento(
            sessao_f3,
            contexto_f3.tenant_id,
            esquemas.AfastamentoCriar(
                colaborador_id=contexto_f3.colaborador_sp_id,
                tipo_afastamento_id=tipo.id,
                data_inicio=dt.date(2024, 3, 10),
                data_fim=dt.date(2024, 3, 1),
            ),
        )
    assert excinfo.value.codigo == "PONTO-VAL-007"


async def test_dois_afastamentos_integrais_aprovados_sobrepostos_e_val_010(
    sessao_f3: AsyncSession, contexto_f3: ContextoF3
) -> None:
    """Criterio de aceite 8 / T6: os dois lados da constraint EXCLUDE."""
    tipo = await _criar_tipo(sessao_f3, contexto_f3, "SOBREPOSICAO-INTEGRAL")
    await servico.criar_afastamento(
        sessao_f3,
        contexto_f3.tenant_id,
        esquemas.AfastamentoCriar(
            colaborador_id=contexto_f3.colaborador_sp_id,
            tipo_afastamento_id=tipo.id,
            data_inicio=dt.date(2024, 4, 1),
            data_fim=dt.date(2024, 4, 10),
            status=esquemas.Status19.aprovado,
        ),
    )
    await sessao_f3.flush()
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.criar_afastamento(
            sessao_f3,
            contexto_f3.tenant_id,
            esquemas.AfastamentoCriar(
                colaborador_id=contexto_f3.colaborador_sp_id,
                tipo_afastamento_id=tipo.id,
                data_inicio=dt.date(2024, 4, 5),
                data_fim=dt.date(2024, 4, 15),
                status=esquemas.Status19.aprovado,
            ),
        )
    assert excinfo.value.codigo == "PONTO-VAL-010"


async def test_afastamento_parcial_pode_coexistir_com_integral(
    sessao_f3: AsyncSession, contexto_f3: ContextoF3
) -> None:
    """Afastamentos parciais ficam fora da regra de exclusao por natureza
    (PCF, secao 2) -- podem coexistir com um integral aprovado no mesmo dia."""
    tipo = await _criar_tipo(sessao_f3, contexto_f3, "COEXISTE-PARCIAL")
    await servico.criar_afastamento(
        sessao_f3,
        contexto_f3.tenant_id,
        esquemas.AfastamentoCriar(
            colaborador_id=contexto_f3.colaborador_ba_id,
            tipo_afastamento_id=tipo.id,
            data_inicio=dt.date(2024, 5, 1),
            data_fim=dt.date(2024, 5, 10),
            status=esquemas.Status19.aprovado,
        ),
    )
    await sessao_f3.flush()
    parcial = await servico.criar_afastamento(
        sessao_f3,
        contexto_f3.tenant_id,
        esquemas.AfastamentoCriar(
            colaborador_id=contexto_f3.colaborador_ba_id,
            tipo_afastamento_id=tipo.id,
            data_inicio=dt.date(2024, 5, 5),
            data_fim=dt.date(2024, 5, 5),
            periodo_parcial=True,
            hora_inicio="08:00",
            hora_fim="10:00",
            status=esquemas.Status19.aprovado,
        ),
    )
    assert parcial.periodo_parcial is True


async def test_obter_atualizar_e_excluir_afastamento(
    sessao_f3: AsyncSession, contexto_f3: ContextoF3
) -> None:
    tipo = await _criar_tipo(sessao_f3, contexto_f3, "CRUD-BASICO")
    criado = await servico.criar_afastamento(
        sessao_f3,
        contexto_f3.tenant_id,
        esquemas.AfastamentoCriar(
            colaborador_id=contexto_f3.colaborador_sem_unidade_id,
            tipo_afastamento_id=tipo.id,
            data_inicio=dt.date(2024, 6, 1),
            data_fim=dt.date(2024, 6, 5),
            status=esquemas.Status19.solicitado,
        ),
    )
    encontrado = await servico.obter_afastamento(sessao_f3, contexto_f3.tenant_id, criado.id)
    assert encontrado.id == criado.id

    # PONTO-PER-001: sem nenhum `fechamentos` na base, a operacao nunca e
    # derrubada (caminho sempre verdadeiro nesta fase -- a F10 nao existe).
    atualizado = await servico.atualizar_afastamento(
        sessao_f3,
        contexto_f3.tenant_id,
        criado.id,
        esquemas.AfastamentoAtualizar(status=esquemas.Status19.aprovado),
    )
    assert atualizado.status == "aprovado"

    await servico.excluir_afastamento(sessao_f3, contexto_f3.tenant_id, criado.id)
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.obter_afastamento(sessao_f3, contexto_f3.tenant_id, criado.id)
    assert excinfo.value.codigo == "PONTO-REC-001"


async def test_reaprovar_cancelado_e_conf_003(
    sessao_f3: AsyncSession, contexto_f3: ContextoF3
) -> None:
    tipo = await _criar_tipo(sessao_f3, contexto_f3, "TRANSICAO-INVALIDA")
    criado = await servico.criar_afastamento(
        sessao_f3,
        contexto_f3.tenant_id,
        esquemas.AfastamentoCriar(
            colaborador_id=contexto_f3.colaborador_sem_unidade_id,
            tipo_afastamento_id=tipo.id,
            data_inicio=dt.date(2024, 7, 1),
            data_fim=dt.date(2024, 7, 5),
            status=esquemas.Status19.solicitado,
        ),
    )
    await servico.atualizar_afastamento(
        sessao_f3,
        contexto_f3.tenant_id,
        criado.id,
        esquemas.AfastamentoAtualizar(status=esquemas.Status19.cancelado),
    )
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.atualizar_afastamento(
            sessao_f3,
            contexto_f3.tenant_id,
            criado.id,
            esquemas.AfastamentoAtualizar(status=esquemas.Status19.aprovado),
        )
    assert excinfo.value.codigo == "PONTO-CONF-003"


async def test_listar_afastamentos_filtra_por_colaborador_e_status(
    sessao_f3: AsyncSession, contexto_f3: ContextoF3
) -> None:
    tipo = await _criar_tipo(sessao_f3, contexto_f3, "LISTAGEM-FILTRO")
    await servico.criar_afastamento(
        sessao_f3,
        contexto_f3.tenant_id,
        esquemas.AfastamentoCriar(
            colaborador_id=contexto_f3.colaborador_sp_id,
            tipo_afastamento_id=tipo.id,
            data_inicio=dt.date(2024, 8, 1),
            data_fim=dt.date(2024, 8, 5),
            status=esquemas.Status19.aprovado,
        ),
    )
    linhas, _ = await servico.listar_afastamentos(
        sessao_f3,
        contexto_f3.tenant_id,
        colaborador_id=contexto_f3.colaborador_sp_id,
        status="aprovado",
    )
    assert all(a.colaborador_id == contexto_f3.colaborador_sp_id for a in linhas)
    assert all(a.status == "aprovado" for a in linhas)
