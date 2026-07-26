"""Cobertura complementar de `app.jornada.calendario.feriados`: listagem e
paginacao por cursor de `feriado_conjuntos`, filtro por `unidadeId` sem
nenhum conjunto associado, filtro por `tipo`/`de`/`ate` e paginacao por
cursor da listagem efetiva de feriados (ordenada por `nome`)."""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.jornada.calendario import feriados as servico
from app.schemas import contrato as esquemas
from tests.f3.conftest import ContextoF3

pytestmark = pytest.mark.asyncio


async def test_listar_feriado_conjuntos_filtra_abrangencia_uf_e_ativo(
    sessao_f3: AsyncSession, contexto_f3: ContextoF3
) -> None:
    await servico.criar_feriado_conjunto(
        sessao_f3,
        contexto_f3.tenant_id,
        esquemas.FeriadoConjuntoCriar(
            codigo="LISTAR-ESTADUAL",
            nome="Estadual SP",
            abrangencia=esquemas.Abrangencia.estadual,
            uf="SP",
            ativo=True,
        ),
    )
    linhas, _ = await servico.listar_feriado_conjuntos(
        sessao_f3, contexto_f3.tenant_id, abrangencia="estadual", uf="SP", ativo=True
    )
    assert any(c.codigo == "LISTAR-ESTADUAL" for c in linhas)


async def test_listar_feriado_conjuntos_filtra_por_unidade(
    sessao_f3: AsyncSession, contexto_f3: ContextoF3
) -> None:
    conjunto = await servico.criar_feriado_conjunto(
        sessao_f3,
        contexto_f3.tenant_id,
        esquemas.FeriadoConjuntoCriar(
            codigo="LISTAR-POR-UNIDADE",
            nome="Nacional associado a SP",
            abrangencia=esquemas.Abrangencia.nacional,
            unidade_ids=[contexto_f3.unidade_sp_id],
        ),
    )
    linhas_sp, _ = await servico.listar_feriado_conjuntos(
        sessao_f3, contexto_f3.tenant_id, unidade_id=contexto_f3.unidade_sp_id
    )
    linhas_ba, _ = await servico.listar_feriado_conjuntos(
        sessao_f3, contexto_f3.tenant_id, unidade_id=contexto_f3.unidade_ba_id
    )
    assert any(c.id == conjunto.id for c in linhas_sp)
    assert not any(c.id == conjunto.id for c in linhas_ba)


async def test_listar_feriado_conjuntos_pagina_por_cursor(
    sessao_f3: AsyncSession, contexto_f3: ContextoF3
) -> None:
    for i in range(3):
        await servico.criar_feriado_conjunto(
            sessao_f3,
            contexto_f3.tenant_id,
            esquemas.FeriadoConjuntoCriar(
                codigo=f"PAG-CONJ-{i}",
                nome=f"Conjunto pag {i}",
                abrangencia=esquemas.Abrangencia.nacional,
            ),
        )
    primeira, paginacao = await servico.listar_feriado_conjuntos(
        sessao_f3, contexto_f3.tenant_id, limite=1, ordenar="codigo:asc"
    )
    assert len(primeira) == 1
    assert paginacao.tem_mais is True
    assert paginacao.proximo_cursor

    segunda, _ = await servico.listar_feriado_conjuntos(
        sessao_f3,
        contexto_f3.tenant_id,
        limite=1,
        ordenar="codigo:asc",
        cursor=paginacao.proximo_cursor,
    )
    assert len(segunda) == 1
    assert segunda[0].id != primeira[0].id


async def test_listar_feriados_unidade_sem_nenhum_conjunto_devolve_vazio(
    sessao_f3: AsyncSession, contexto_f3: ContextoF3
) -> None:
    """`unidade_ba` nao tem nenhum conjunto associado nesta fixture: o
    caminho de saida antecipada (sem consulta a `feriados`) devolve pagina
    vazia, nao erro."""
    linhas, paginacao = await servico.listar_feriados(
        sessao_f3, contexto_f3.tenant_id, unidade_id=contexto_f3.unidade_ba_id, ano=2030
    )
    assert linhas == []
    assert paginacao.tem_mais is False


async def test_listar_feriados_filtra_por_tipo_e_intervalo_de_datas(
    sessao_f3: AsyncSession, contexto_f3: ContextoF3
) -> None:
    conjunto = await servico.criar_feriado_conjunto(
        sessao_f3,
        contexto_f3.tenant_id,
        esquemas.FeriadoConjuntoCriar(
            codigo="TIPO-E-INTERVALO",
            nome="Tipo e intervalo",
            abrangencia=esquemas.Abrangencia.nacional,
            unidade_ids=[contexto_f3.unidade_sp_id],
        ),
    )
    await servico.criar_feriado(
        sessao_f3,
        contexto_f3.tenant_id,
        esquemas.FeriadoCriar(
            feriado_conjunto_id=conjunto.id,
            nome="Ponto facultativo de teste",
            data=dt.date(2024, 12, 24),
            tipo=esquemas.Tipo23.ponto_facultativo,
            movel=False,
            integral=True,
        ),
    )
    linhas, _ = await servico.listar_feriados(
        sessao_f3,
        contexto_f3.tenant_id,
        unidade_id=contexto_f3.unidade_sp_id,
        ano=2024,
        tipo="ponto_facultativo",
        de=dt.date(2024, 12, 1),
        ate=dt.date(2024, 12, 31),
    )
    assert any(f.nome == "Ponto facultativo de teste" for f in linhas)

    fora_do_intervalo, _ = await servico.listar_feriados(
        sessao_f3,
        contexto_f3.tenant_id,
        unidade_id=contexto_f3.unidade_sp_id,
        ano=2024,
        tipo="ponto_facultativo",
        de=dt.date(2025, 1, 1),
        ate=dt.date(2025, 1, 31),
    )
    assert not any(f.nome == "Ponto facultativo de teste" for f in fora_do_intervalo)


async def test_listar_feriados_pagina_por_cursor_ordenado_por_nome(
    sessao_f3: AsyncSession, contexto_f3: ContextoF3
) -> None:
    conjunto = await servico.criar_feriado_conjunto(
        sessao_f3,
        contexto_f3.tenant_id,
        esquemas.FeriadoConjuntoCriar(
            codigo="PAG-FERIADO-NOME",
            nome="Pag feriado",
            abrangencia=esquemas.Abrangencia.nacional,
            unidade_ids=[contexto_f3.unidade_sp_id],
        ),
    )
    for i in range(3):
        await servico.criar_feriado(
            sessao_f3,
            contexto_f3.tenant_id,
            esquemas.FeriadoCriar(
                feriado_conjunto_id=conjunto.id,
                nome=f"Feriado ordenado {i}",
                data=dt.date(2024, 3, 1 + i),
                movel=False,
                integral=True,
            ),
        )
    primeira, paginacao = await servico.listar_feriados(
        sessao_f3,
        contexto_f3.tenant_id,
        unidade_id=contexto_f3.unidade_sp_id,
        ano=2024,
        limite=1,
        ordenar="nome:asc",
    )
    assert len(primeira) == 1
    assert paginacao.tem_mais is True

    segunda, _ = await servico.listar_feriados(
        sessao_f3,
        contexto_f3.tenant_id,
        unidade_id=contexto_f3.unidade_sp_id,
        ano=2024,
        limite=1,
        ordenar="nome:asc",
        cursor=paginacao.proximo_cursor,
    )
    assert len(segunda) == 1
    assert segunda[0].id != primeira[0].id


async def test_feriado_fixo_29_fevereiro_em_ano_nao_bissexto_nao_resolve(
    sessao_f3: AsyncSession, contexto_f3: ContextoF3
) -> None:
    """Feriado fixo com `ano` ausente (repete todo ano) definido em 29/02
    nao tem data efetiva num ano nao bissexto -- `resolver_data_feriado`
    devolve `None`, e o feriado nao aparece na listagem daquele ano."""
    conjunto = await servico.criar_feriado_conjunto(
        sessao_f3,
        contexto_f3.tenant_id,
        esquemas.FeriadoConjuntoCriar(
            codigo="FEV-29",
            nome="Fevereiro 29",
            abrangencia=esquemas.Abrangencia.nacional,
            unidade_ids=[contexto_f3.unidade_sp_id],
        ),
    )
    await servico.criar_feriado(
        sessao_f3,
        contexto_f3.tenant_id,
        esquemas.FeriadoCriar(
            feriado_conjunto_id=conjunto.id,
            nome="Feriado bissexto",
            data=dt.date(2024, 2, 29),
            movel=False,
            integral=True,
        ),
    )
    linhas_2025, _ = await servico.listar_feriados(
        sessao_f3, contexto_f3.tenant_id, unidade_id=contexto_f3.unidade_sp_id, ano=2025
    )
    assert not any(f.nome == "Feriado bissexto" for f in linhas_2025)

    linhas_2028, _ = await servico.listar_feriados(
        sessao_f3, contexto_f3.tenant_id, unidade_id=contexto_f3.unidade_sp_id, ano=2028
    )
    assert any(f.nome == "Feriado bissexto" for f in linhas_2028)


async def test_feriado_restrito_a_um_ano_nao_aparece_em_outro(
    sessao_f3: AsyncSession, contexto_f3: ContextoF3
) -> None:
    conjunto = await servico.criar_feriado_conjunto(
        sessao_f3,
        contexto_f3.tenant_id,
        esquemas.FeriadoConjuntoCriar(
            codigo="ANO-ESPECIFICO",
            nome="Ano especifico",
            abrangencia=esquemas.Abrangencia.nacional,
            unidade_ids=[contexto_f3.unidade_sp_id],
        ),
    )
    await servico.criar_feriado(
        sessao_f3,
        contexto_f3.tenant_id,
        esquemas.FeriadoCriar(
            feriado_conjunto_id=conjunto.id,
            nome="Feriado de um ano so",
            data=dt.date(2024, 5, 20),
            ano=2024,
            movel=False,
            integral=True,
        ),
    )
    linhas_2024, _ = await servico.listar_feriados(
        sessao_f3, contexto_f3.tenant_id, unidade_id=contexto_f3.unidade_sp_id, ano=2024
    )
    linhas_2025, _ = await servico.listar_feriados(
        sessao_f3, contexto_f3.tenant_id, unidade_id=contexto_f3.unidade_sp_id, ano=2025
    )
    assert any(f.nome == "Feriado de um ano so" for f in linhas_2024)
    assert not any(f.nome == "Feriado de um ano so" for f in linhas_2025)
