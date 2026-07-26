"""Cobertura complementar de `app.jornada.calendario.afastamentos`: paginacao
por cursor, filtros adicionais de listagem e os caminhos de erro que os
testes principais de T6 nao exercitam (tipo/afastamento inexistente,
`_escopo_do_afastamento` com vinculo presente)."""

from __future__ import annotations

import datetime as dt
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.erros import ErroDeAplicacao
from app.jornada.calendario import afastamentos as servico
from app.schemas import contrato as esquemas
from tests.f3.conftest import ContextoF3

pytestmark = pytest.mark.asyncio


async def test_atualizar_tipo_afastamento_inexistente_e_rec_001(
    sessao_f3: AsyncSession, contexto_f3: ContextoF3
) -> None:
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.atualizar_tipo_afastamento(
            sessao_f3,
            contexto_f3.tenant_id,
            uuid4(),
            esquemas.TipoAfastamentoAtualizar(nome="Nao existe"),
        )
    assert excinfo.value.codigo == "PONTO-REC-001"


async def test_listar_tipos_afastamento_filtra_categoria_e_ativo(
    sessao_f3: AsyncSession, contexto_f3: ContextoF3
) -> None:
    await servico.criar_tipo_afastamento(
        sessao_f3,
        contexto_f3.tenant_id,
        esquemas.TipoAfastamentoCriar(
            codigo="ATESTADO-FILTRO",
            nome="Atestado",
            categoria=esquemas.Categoria2.atestado,
            ativo=True,
        ),
    )
    linhas, _ = await servico.listar_tipos_afastamento(
        sessao_f3, contexto_f3.tenant_id, categoria="atestado", ativo=True
    )
    assert all(t.categoria == "atestado" for t in linhas)
    assert all(t.ativo for t in linhas)


async def test_listar_tipos_afastamento_pagina_por_cursor(
    sessao_f3: AsyncSession, contexto_f3: ContextoF3
) -> None:
    for i in range(3):
        await servico.criar_tipo_afastamento(
            sessao_f3,
            contexto_f3.tenant_id,
            esquemas.TipoAfastamentoCriar(
                codigo=f"PAG-TIPO-{i}", nome=f"Tipo pag {i}", categoria=esquemas.Categoria2.outro
            ),
        )
    primeira, paginacao = await servico.listar_tipos_afastamento(
        sessao_f3, contexto_f3.tenant_id, limite=1, ordenar="codigo:asc"
    )
    assert len(primeira) == 1
    assert paginacao.tem_mais is True
    assert paginacao.proximo_cursor

    segunda, _ = await servico.listar_tipos_afastamento(
        sessao_f3,
        contexto_f3.tenant_id,
        limite=1,
        ordenar="codigo:asc",
        cursor=paginacao.proximo_cursor,
    )
    assert len(segunda) == 1
    assert segunda[0].id != primeira[0].id


async def test_afastamento_com_vinculo_resolve_unidade_no_escopo(
    sessao_f3: AsyncSession, contexto_f3: ContextoF3
) -> None:
    """`_escopo_do_afastamento` deve devolver a unidade do vinculo quando
    `vinculo_id` esta presente (exercitado indiretamente via
    `atualizar_afastamento`, que chama a funcao para o PONTO-PER-001)."""
    tipo = await servico.criar_tipo_afastamento(
        sessao_f3,
        contexto_f3.tenant_id,
        esquemas.TipoAfastamentoCriar(
            codigo="COM-VINCULO", nome="Com vinculo", categoria=esquemas.Categoria2.ferias
        ),
    )
    criado = await servico.criar_afastamento(
        sessao_f3,
        contexto_f3.tenant_id,
        esquemas.AfastamentoCriar(
            colaborador_id=contexto_f3.colaborador_sp_id,
            vinculo_id=contexto_f3.vinculo_sp_id,
            tipo_afastamento_id=tipo.id,
            data_inicio=dt.date(2024, 9, 1),
            data_fim=dt.date(2024, 9, 5),
            status=esquemas.Status19.solicitado,
        ),
    )
    atualizado = await servico.atualizar_afastamento(
        sessao_f3,
        contexto_f3.tenant_id,
        criado.id,
        esquemas.AfastamentoAtualizar(motivo="Ajuste de motivo"),
    )
    assert atualizado.motivo == "Ajuste de motivo"


async def test_listar_afastamentos_pagina_por_cursor_e_filtra_por_vinculo_e_tipo(
    sessao_f3: AsyncSession, contexto_f3: ContextoF3
) -> None:
    tipo = await servico.criar_tipo_afastamento(
        sessao_f3,
        contexto_f3.tenant_id,
        esquemas.TipoAfastamentoCriar(
            codigo="PAG-AFAST", nome="Paginacao afastamento", categoria=esquemas.Categoria2.outro
        ),
    )
    for i in range(2):
        await servico.criar_afastamento(
            sessao_f3,
            contexto_f3.tenant_id,
            esquemas.AfastamentoCriar(
                colaborador_id=contexto_f3.colaborador_ba_id,
                vinculo_id=contexto_f3.vinculo_ba_id,
                tipo_afastamento_id=tipo.id,
                data_inicio=dt.date(2024, 10, 1 + i),
                status=esquemas.Status19.solicitado,
            ),
        )
    primeira, paginacao = await servico.listar_afastamentos(
        sessao_f3,
        contexto_f3.tenant_id,
        vinculo_id=contexto_f3.vinculo_ba_id,
        tipo_afastamento_id=tipo.id,
        limite=1,
        ordenar="dataInicio:asc",
    )
    assert len(primeira) == 1
    assert paginacao.tem_mais is True

    segunda, _ = await servico.listar_afastamentos(
        sessao_f3,
        contexto_f3.tenant_id,
        vinculo_id=contexto_f3.vinculo_ba_id,
        tipo_afastamento_id=tipo.id,
        limite=1,
        ordenar="dataInicio:asc",
        cursor=paginacao.proximo_cursor,
    )
    assert len(segunda) == 1
    assert segunda[0].id != primeira[0].id


async def test_listar_afastamentos_filtra_por_empresa_e_intervalo_de_datas(
    sessao_f3: AsyncSession, contexto_f3: ContextoF3
) -> None:
    tipo = await servico.criar_tipo_afastamento(
        sessao_f3,
        contexto_f3.tenant_id,
        esquemas.TipoAfastamentoCriar(
            codigo="FILTRO-EMPRESA", nome="Filtro empresa", categoria=esquemas.Categoria2.outro
        ),
    )
    await servico.criar_afastamento(
        sessao_f3,
        contexto_f3.tenant_id,
        esquemas.AfastamentoCriar(
            colaborador_id=contexto_f3.colaborador_sp_id,
            tipo_afastamento_id=tipo.id,
            data_inicio=dt.date(2024, 11, 10),
            data_fim=dt.date(2024, 11, 15),
            status=esquemas.Status19.aprovado,
        ),
    )
    linhas, _ = await servico.listar_afastamentos(
        sessao_f3,
        contexto_f3.tenant_id,
        empresa_id=contexto_f3.empresa_id,
        de=dt.date(2024, 11, 1),
        ate=dt.date(2024, 11, 30),
    )
    assert len(linhas) >= 1

    fora_do_intervalo, _ = await servico.listar_afastamentos(
        sessao_f3,
        contexto_f3.tenant_id,
        empresa_id=contexto_f3.empresa_id,
        de=dt.date(2025, 1, 1),
        ate=dt.date(2025, 1, 31),
    )
    assert all(a.data_inicio >= dt.date(2025, 1, 1) for a in fora_do_intervalo)
