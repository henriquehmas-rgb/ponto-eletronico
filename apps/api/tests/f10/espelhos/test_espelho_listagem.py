"""Testes de `app.workflow.fechamento.espelho` que não são sobre o
`conteudo`/PDF em si (isso já é `test_espelho.py`), e sim sobre o CRUD de
leitura/listagem e a resolução de escopo -- `obter_espelho`,
`listar_espelhos`, `resolver_escopo_espelhos` e `criar_espelhos_assincrono`
não eram exercitados por nenhum teste antes deste arquivo (F10/A2)."""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
from ponto_contracts import AssinaturaEspelho, Periodo

from app.core.erros import ErroDeAplicacao
from app.schemas import contrato as esquemas
from app.workflow.fechamento import espelho as espelho_modulo
from tests.f10.conftest import ContextoF10, aplicar_tenant_teste


async def _periodo(sessao, contexto: ContextoF10) -> Periodo:
    return await sessao.get(Periodo, contexto.periodo_id)


# ---------------------------------------------------------------------------
# `obter_espelho`
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_obter_espelho_inexistente_e_rec_001(sessao_f10, contexto_f10: ContextoF10) -> None:
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await espelho_modulo.obter_espelho(sessao_f10, contexto_f10.tenant_id, uuid.uuid4())
    assert excinfo.value.codigo == "PONTO-REC-001"


# ---------------------------------------------------------------------------
# `gerar_espelho_do_vinculo` -- ramos de erro que `test_espelho.py` não
# cobre (vínculo inexistente; `fechamentoId` que viola a FK no `flush`).
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gerar_espelho_com_vinculo_inexistente_e_rec_001(
    sessao_f10, contexto_f10: ContextoF10
) -> None:
    periodo = await _periodo(sessao_f10, contexto_f10)
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await espelho_modulo.gerar_espelho_do_vinculo(
            sessao_f10,
            contexto_f10.tenant_id,
            periodo,
            uuid.uuid4(),
            "previo",
            usuario_id=contexto_f10.rh_usuario_id,
        )
    assert excinfo.value.codigo == "PONTO-REC-001"


@pytest.mark.asyncio
async def test_gerar_espelho_com_fechamento_inexistente_traduz_integridade(
    sessao_f10, contexto_f10: ContextoF10
) -> None:
    periodo = await _periodo(sessao_f10, contexto_f10)
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await espelho_modulo.gerar_espelho_do_vinculo(
            sessao_f10,
            contexto_f10.tenant_id,
            periodo,
            contexto_f10.vinculo_id,
            "previo",
            fechamento_id=uuid.uuid4(),
            usuario_id=contexto_f10.rh_usuario_id,
        )
    assert excinfo.value.codigo == "PONTO-VAL-001"


# ---------------------------------------------------------------------------
# `listar_espelhos` -- filtros e paginacao por cursor.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_listar_espelhos_filtra_por_tipo_colaborador_vinculo_e_assinado(
    sessao_f10, contexto_f10: ContextoF10
) -> None:
    periodo = await _periodo(sessao_f10, contexto_f10)

    previo = await espelho_modulo.gerar_espelho_do_vinculo(
        sessao_f10,
        contexto_f10.tenant_id,
        periodo,
        contexto_f10.vinculo_id,
        "previo",
        usuario_id=contexto_f10.rh_usuario_id,
    )
    await sessao_f10.commit()
    await aplicar_tenant_teste(sessao_f10, contexto_f10.tenant_id)

    oficial = await espelho_modulo.gerar_espelho_do_vinculo(
        sessao_f10,
        contexto_f10.tenant_id,
        periodo,
        contexto_f10.vinculo_id,
        "oficial",
        usuario_id=contexto_f10.rh_usuario_id,
    )
    await sessao_f10.commit()
    await aplicar_tenant_teste(sessao_f10, contexto_f10.tenant_id)

    # Assina só o oficial, para exercitar os dois ramos do filtro `assinado`.
    sessao_f10.add(
        AssinaturaEspelho(
            tenant_id=contexto_f10.tenant_id,
            espelho_id=oficial.id,
            signatario_tipo="colaborador",
            signatario_colaborador_id=contexto_f10.colaborador_id,
            metodo="aceite_eletronico",
            hash_assinado=oficial.hash_sha256,
            carimbo_tempo=dt.datetime.now(tz=dt.UTC),
            status="assinado",
        )
    )
    await sessao_f10.flush()
    await sessao_f10.commit()
    await aplicar_tenant_teste(sessao_f10, contexto_f10.tenant_id)

    linhas_previo, _ = await espelho_modulo.listar_espelhos(
        sessao_f10,
        contexto_f10.tenant_id,
        periodo_id=periodo.id,
        colaborador_id=contexto_f10.colaborador_id,
        vinculo_id=contexto_f10.vinculo_id,
        tipo="previo",
    )
    assert [e.id for e in linhas_previo] == [previo.id]

    linhas_assinados, _ = await espelho_modulo.listar_espelhos(
        sessao_f10, contexto_f10.tenant_id, periodo_id=periodo.id, assinado=True
    )
    assert [e.id for e in linhas_assinados] == [oficial.id]

    linhas_nao_assinados, _ = await espelho_modulo.listar_espelhos(
        sessao_f10, contexto_f10.tenant_id, periodo_id=periodo.id, assinado=False
    )
    assert [e.id for e in linhas_nao_assinados] == [previo.id]


@pytest.mark.asyncio
async def test_listar_espelhos_pagina_por_cursor_ordenando_por_versao(
    sessao_f10, contexto_f10: ContextoF10
) -> None:
    periodo = await _periodo(sessao_f10, contexto_f10)

    versao_1 = await espelho_modulo.gerar_espelho_do_vinculo(
        sessao_f10,
        contexto_f10.tenant_id,
        periodo,
        contexto_f10.vinculo_id,
        "oficial",
        usuario_id=contexto_f10.rh_usuario_id,
    )
    await sessao_f10.commit()
    await aplicar_tenant_teste(sessao_f10, contexto_f10.tenant_id)

    versao_2 = await espelho_modulo.gerar_espelho_do_vinculo(
        sessao_f10,
        contexto_f10.tenant_id,
        periodo,
        contexto_f10.vinculo_id,
        "oficial",
        usuario_id=contexto_f10.rh_usuario_id,
    )
    assert versao_2.versao == 2
    await sessao_f10.commit()
    await aplicar_tenant_teste(sessao_f10, contexto_f10.tenant_id)

    primeira_pagina, paginacao = await espelho_modulo.listar_espelhos(
        sessao_f10,
        contexto_f10.tenant_id,
        periodo_id=periodo.id,
        ordenar="versao:asc",
        limite=1,
    )
    assert [e.id for e in primeira_pagina] == [versao_1.id]
    assert paginacao.tem_mais is True
    assert paginacao.proximo_cursor is not None

    segunda_pagina, paginacao_2 = await espelho_modulo.listar_espelhos(
        sessao_f10,
        contexto_f10.tenant_id,
        periodo_id=periodo.id,
        ordenar="versao:asc",
        limite=1,
        cursor=paginacao.proximo_cursor,
    )
    assert [e.id for e in segunda_pagina] == [versao_2.id]
    assert paginacao_2.tem_mais is False


@pytest.mark.asyncio
async def test_listar_espelhos_filtra_por_fechamento(sessao_f10, contexto_f10: ContextoF10) -> None:
    from ponto_contracts import Fechamento

    periodo = await _periodo(sessao_f10, contexto_f10)
    fechamento = Fechamento(
        tenant_id=contexto_f10.tenant_id,
        periodo_id=periodo.id,
        empresa_id=contexto_f10.empresa_id,
        escopo="empresa",
        status="em_andamento",
    )
    sessao_f10.add(fechamento)
    await sessao_f10.flush()

    espelho = await espelho_modulo.gerar_espelho_do_vinculo(
        sessao_f10,
        contexto_f10.tenant_id,
        periodo,
        contexto_f10.vinculo_id,
        "oficial",
        fechamento_id=fechamento.id,
        usuario_id=contexto_f10.rh_usuario_id,
    )

    linhas, _ = await espelho_modulo.listar_espelhos(
        sessao_f10, contexto_f10.tenant_id, fechamento_id=fechamento.id
    )
    assert [e.id for e in linhas] == [espelho.id]


# ---------------------------------------------------------------------------
# `resolver_escopo_espelhos`
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolver_escopo_espelhos_com_vinculo_ids_explicitos(
    sessao_f10, contexto_f10: ContextoF10
) -> None:
    outro_vinculo_id = uuid.uuid4()
    resolvidos = await espelho_modulo.resolver_escopo_espelhos(
        sessao_f10,
        contexto_f10.tenant_id,
        esquemas.EspelhoCriar(vinculoIds=[contexto_f10.vinculo_id, outro_vinculo_id]),
    )
    assert resolvidos == [contexto_f10.vinculo_id, outro_vinculo_id]


@pytest.mark.asyncio
async def test_resolver_escopo_espelhos_sem_vinculo_ids_nem_empresa_id_e_val_001(
    sessao_f10, contexto_f10: ContextoF10
) -> None:
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await espelho_modulo.resolver_escopo_espelhos(
            sessao_f10, contexto_f10.tenant_id, esquemas.EspelhoCriar()
        )
    assert excinfo.value.codigo == "PONTO-VAL-001"


@pytest.mark.asyncio
async def test_resolver_escopo_espelhos_por_empresa(sessao_f10, contexto_f10: ContextoF10) -> None:
    resolvidos = await espelho_modulo.resolver_escopo_espelhos(
        sessao_f10, contexto_f10.tenant_id, esquemas.EspelhoCriar(empresaId=contexto_f10.empresa_id)
    )
    assert resolvidos == [contexto_f10.vinculo_id]


@pytest.mark.asyncio
async def test_resolver_escopo_espelhos_por_unidade(sessao_f10, contexto_f10: ContextoF10) -> None:
    resolvidos = await espelho_modulo.resolver_escopo_espelhos(
        sessao_f10,
        contexto_f10.tenant_id,
        esquemas.EspelhoCriar(empresaId=contexto_f10.empresa_id, unidadeId=contexto_f10.unidade_id),
    )
    assert resolvidos == [contexto_f10.vinculo_id]


# ---------------------------------------------------------------------------
# `criar_espelhos_assincrono`
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_criar_espelhos_assincrono_sem_periodo_id_e_val_001(
    sessao_f10, contexto_f10: ContextoF10, redis_teste_url_f10: str
) -> None:
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await espelho_modulo.criar_espelhos_assincrono(
            sessao_f10,
            contexto_f10.tenant_id,
            esquemas.EspelhoCriar(empresaId=contexto_f10.empresa_id),
            usuario_id=contexto_f10.rh_usuario_id,
            redis_url=redis_teste_url_f10,
        )
    assert excinfo.value.codigo == "PONTO-VAL-001"


@pytest.mark.asyncio
async def test_criar_espelhos_assincrono_periodo_inexistente_e_rec_001(
    sessao_f10, contexto_f10: ContextoF10, redis_teste_url_f10: str
) -> None:
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await espelho_modulo.criar_espelhos_assincrono(
            sessao_f10,
            contexto_f10.tenant_id,
            esquemas.EspelhoCriar(periodoId=uuid.uuid4(), empresaId=contexto_f10.empresa_id),
            usuario_id=contexto_f10.rh_usuario_id,
            redis_url=redis_teste_url_f10,
        )
    assert excinfo.value.codigo == "PONTO-REC-001"


@pytest.mark.asyncio
async def test_criar_espelhos_assincrono_enfileira_e_devolve_202(
    sessao_f10, contexto_f10: ContextoF10, redis_teste_url_f10: str
) -> None:
    resposta = await espelho_modulo.criar_espelhos_assincrono(
        sessao_f10,
        contexto_f10.tenant_id,
        esquemas.EspelhoCriar(
            periodoId=contexto_f10.periodo_id,
            empresaId=contexto_f10.empresa_id,
            gerarPdf=False,
        ),
        usuario_id=contexto_f10.rh_usuario_id,
        redis_url=redis_teste_url_f10,
    )
    assert resposta.status == esquemas.Status62.enfileirado
    assert resposta.total_itens == 1
    assert resposta.itens_processados == 0
