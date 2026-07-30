"""Testes de `app.workflow.fechamento.servico` (T5, F10/A2).

Cobre os critérios "pronto quando": `criarFechamento` recusa com
`PONTO-PER-004` quando há pendência bloqueante e `forcar=false`, aceita com
`forcar=true` registrando o total; `reabrirFechamento` sem `motivo`
responde `PONTO-PER-003`; reabertura grava exatamente uma linha em
`auditoria` com `acao='reabrir'` e o motivo em `metadados`/`valor_novo`.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
import sqlalchemy as sa
from ponto_contracts import Auditoria, Fechamento, Periodo

from app.core.erros import ErroDeAplicacao
from app.schemas import contrato as esquemas
from app.workflow.fechamento import servico
from tests.f10.conftest import ContextoF10, aplicar_tenant_teste


async def _periodo(sessao, contexto: ContextoF10) -> Periodo:
    return await sessao.get(Periodo, contexto.periodo_id)


@pytest.mark.asyncio
async def test_criar_fechamento_recusa_com_pendencia_bloqueante_sem_forcar(
    sessao_f10, contexto_f10: ContextoF10
) -> None:
    corpo = esquemas.FechamentoCriar(
        periodoId=contexto_f10.periodo_id,
        escopo=esquemas.Escopo.empresa,
        empresaId=contexto_f10.empresa_id,
        gerarEspelhos=False,
        forcar=False,
    )
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.criar_fechamento(
            sessao_f10,
            contexto_f10.tenant_id,
            corpo,
            usuario_id=contexto_f10.rh_usuario_id,
            redis_url="redis://localhost:6379/0",
        )
    assert excinfo.value.codigo == "PONTO-PER-004"

    total = (
        await sessao_f10.execute(
            sa.select(sa.func.count()).where(
                Fechamento.tenant_id == contexto_f10.tenant_id,
                Fechamento.periodo_id == contexto_f10.periodo_id,
            )
        )
    ).scalar_one()
    assert total == 0


@pytest.mark.asyncio
async def test_criar_fechamento_com_forcar_registra_pendencia_e_enfileira(
    sessao_f10, contexto_f10: ContextoF10, redis_teste_url_f10: str
) -> None:
    periodo = await _periodo(sessao_f10, contexto_f10)
    # `total_pendencias` (comentario da coluna, schema.sql) conta so
    # ocorrencias/solicitacoes abertas -- "dia nao apurado" fica em
    # `bloqueantes`/`apuracoesPendentes`, nao em `total_pendencias`. Uma
    # ocorrencia bloqueante real deixa o teste inequivoco nos dois campos.
    from ponto_contracts import Ocorrencia

    sessao_f10.add(
        Ocorrencia(
            tenant_id=contexto_f10.tenant_id,
            colaborador_id=contexto_f10.colaborador_id,
            vinculo_id=contexto_f10.vinculo_id,
            data=periodo.data_inicio,
            codigo="sem_marcacao",
            severidade="atencao",
            descricao="Dia sem nenhuma marcacao (teste).",
            status="aberta",
        )
    )
    await sessao_f10.flush()

    corpo = esquemas.FechamentoCriar(
        periodoId=contexto_f10.periodo_id,
        escopo=esquemas.Escopo.empresa,
        empresaId=contexto_f10.empresa_id,
        gerarEspelhos=False,
        forcar=True,
    )
    resposta = await servico.criar_fechamento(
        sessao_f10,
        contexto_f10.tenant_id,
        corpo,
        usuario_id=contexto_f10.rh_usuario_id,
        redis_url=redis_teste_url_f10,
    )
    assert resposta.status == esquemas.Status62.enfileirado
    assert resposta.tipo is None  # achado de contrato §2.7 item 3, PCF

    fechamento = await sessao_f10.get(Fechamento, resposta.id)
    assert fechamento is not None
    assert fechamento.status == "em_andamento"
    assert fechamento.total_ocorrencias == 1
    assert fechamento.total_pendencias >= 1


@pytest.mark.asyncio
async def test_criar_fechamento_escopo_equipe_e_recusado(
    sessao_f10, contexto_f10: ContextoF10
) -> None:
    """Achado de contrato: `fechamentos` nao tem coluna `equipe_id`/
    `colaborador_id`, e a trava real (F4) so reconhece empresa/unidade/
    departamento -- ver docstring de `servico.py`."""
    corpo = esquemas.FechamentoCriar(
        periodoId=contexto_f10.periodo_id,
        escopo=esquemas.Escopo.colaborador,
        empresaId=contexto_f10.empresa_id,
        colaboradorId=contexto_f10.colaborador_id,
        forcar=True,
    )
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.criar_fechamento(
            sessao_f10,
            contexto_f10.tenant_id,
            corpo,
            usuario_id=contexto_f10.rh_usuario_id,
            redis_url="redis://localhost:6379/0",
        )
    assert excinfo.value.codigo == "PONTO-VAL-001"


@pytest.mark.asyncio
async def test_criar_fechamento_ja_fechado_e_per_002(sessao_f10, contexto_f10: ContextoF10) -> None:
    periodo = await _periodo(sessao_f10, contexto_f10)
    ja_fechado = Fechamento(
        tenant_id=contexto_f10.tenant_id,
        periodo_id=periodo.id,
        empresa_id=contexto_f10.empresa_id,
        escopo="empresa",
        status="fechado",
        fechado_em=dt.datetime.now(tz=dt.UTC),
        fechado_por=contexto_f10.rh_usuario_id,
    )
    sessao_f10.add(ja_fechado)
    await sessao_f10.flush()
    await sessao_f10.commit()
    await aplicar_tenant_teste(sessao_f10, contexto_f10.tenant_id)

    corpo = esquemas.FechamentoCriar(
        periodoId=contexto_f10.periodo_id,
        escopo=esquemas.Escopo.empresa,
        empresaId=contexto_f10.empresa_id,
        forcar=True,
    )
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.criar_fechamento(
            sessao_f10,
            contexto_f10.tenant_id,
            corpo,
            usuario_id=contexto_f10.rh_usuario_id,
            redis_url="redis://localhost:6379/0",
        )
    assert excinfo.value.codigo == "PONTO-PER-002"


@pytest.mark.asyncio
async def test_reabrir_sem_motivo_e_per_003(sessao_f10, contexto_f10: ContextoF10) -> None:
    periodo = await _periodo(sessao_f10, contexto_f10)
    fechamento = Fechamento(
        tenant_id=contexto_f10.tenant_id,
        periodo_id=periodo.id,
        empresa_id=contexto_f10.empresa_id,
        escopo="empresa",
        status="fechado",
        fechado_em=dt.datetime.now(tz=dt.UTC),
        fechado_por=contexto_f10.rh_usuario_id,
    )
    sessao_f10.add(fechamento)
    await sessao_f10.flush()
    await sessao_f10.commit()
    await aplicar_tenant_teste(sessao_f10, contexto_f10.tenant_id)

    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.reabrir_fechamento(
            sessao_f10,
            contexto_f10.tenant_id,
            fechamento.id,
            esquemas.ReaberturaRequisicao(),
            usuario_id=contexto_f10.rh_usuario_id,
        )
    assert excinfo.value.codigo == "PONTO-PER-003"


@pytest.mark.asyncio
async def test_reabrir_com_motivo_grava_uma_linha_de_auditoria(
    sessao_f10, contexto_f10: ContextoF10
) -> None:
    periodo = await _periodo(sessao_f10, contexto_f10)
    fechamento = Fechamento(
        tenant_id=contexto_f10.tenant_id,
        periodo_id=periodo.id,
        empresa_id=contexto_f10.empresa_id,
        escopo="empresa",
        status="fechado",
        fechado_em=dt.datetime.now(tz=dt.UTC),
        fechado_por=contexto_f10.rh_usuario_id,
    )
    sessao_f10.add(fechamento)
    await sessao_f10.flush()
    await sessao_f10.commit()
    await aplicar_tenant_teste(sessao_f10, contexto_f10.tenant_id)

    motivo = "Atestado medico retroativo entregue pelo colaborador (teste)."
    reaberto = await servico.reabrir_fechamento(
        sessao_f10,
        contexto_f10.tenant_id,
        fechamento.id,
        esquemas.ReaberturaRequisicao(motivo=motivo),
        usuario_id=contexto_f10.rh_usuario_id,
    )
    assert reaberto.status == "reaberto"
    assert reaberto.motivo_reabertura == motivo
    assert reaberto.reaberto_por == contexto_f10.rh_usuario_id

    linhas_auditoria = (
        (
            await sessao_f10.execute(
                sa.select(Auditoria).where(
                    Auditoria.tenant_id == contexto_f10.tenant_id,
                    Auditoria.entidade == "fechamentos",
                    Auditoria.acao == "reabrir",
                    Auditoria.entidade_id == fechamento.id,
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(linhas_auditoria) == 1
    linha = linhas_auditoria[0]
    assert linha.valor_novo["motivo"] == motivo
    assert linha.valor_novo["status"] == "reaberto"
    assert linha.usuario_id == contexto_f10.rh_usuario_id


@pytest.mark.asyncio
async def test_reabrir_fechamento_nao_fechado_e_conf_003(
    sessao_f10, contexto_f10: ContextoF10
) -> None:
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
    await sessao_f10.commit()
    await aplicar_tenant_teste(sessao_f10, contexto_f10.tenant_id)

    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.reabrir_fechamento(
            sessao_f10,
            contexto_f10.tenant_id,
            fechamento.id,
            esquemas.ReaberturaRequisicao(motivo="Motivo de teste com mais de dez caracteres."),
            usuario_id=contexto_f10.rh_usuario_id,
        )
    assert excinfo.value.codigo == "PONTO-CONF-003"


# ---------------------------------------------------------------------------
# `obter_periodo_do_tenant`/`obter_fechamento` -- ramo "nao encontrado"
# (antes deste bloco, os dois só eram exercitados com um id existente do
# próprio tenant, dentro de `criar_fechamento`/`reabrir_fechamento`).
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_obter_periodo_do_tenant_inexistente_e_rec_001(
    sessao_f10, contexto_f10: ContextoF10
) -> None:
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.obter_periodo_do_tenant(sessao_f10, contexto_f10.tenant_id, uuid.uuid4())
    assert excinfo.value.codigo == "PONTO-REC-001"


@pytest.mark.asyncio
async def test_obter_fechamento_inexistente_e_rec_001(
    sessao_f10, contexto_f10: ContextoF10
) -> None:
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.obter_fechamento(sessao_f10, contexto_f10.tenant_id, uuid.uuid4())
    assert excinfo.value.codigo == "PONTO-REC-001"


# ---------------------------------------------------------------------------
# `criar_fechamento` -- validações de corpo que nenhum teste anterior
# cobria (`periodoId`/`empresaId` ausentes, `empresaId` que não bate com o
# período, escopo `unidade`/`departamento` sem o id correspondente, e a
# tradução de uma violação de integridade real no `flush`).
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_criar_fechamento_sem_periodo_id_e_val_001(
    sessao_f10, contexto_f10: ContextoF10
) -> None:
    corpo = esquemas.FechamentoCriar(
        escopo=esquemas.Escopo.empresa, empresaId=contexto_f10.empresa_id, forcar=True
    )
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.criar_fechamento(
            sessao_f10,
            contexto_f10.tenant_id,
            corpo,
            usuario_id=contexto_f10.rh_usuario_id,
            redis_url="redis://localhost:6379/0",
        )
    assert excinfo.value.codigo == "PONTO-VAL-001"


@pytest.mark.asyncio
async def test_criar_fechamento_sem_empresa_id_e_val_001(
    sessao_f10, contexto_f10: ContextoF10
) -> None:
    corpo = esquemas.FechamentoCriar(
        periodoId=contexto_f10.periodo_id, escopo=esquemas.Escopo.empresa, forcar=True
    )
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.criar_fechamento(
            sessao_f10,
            contexto_f10.tenant_id,
            corpo,
            usuario_id=contexto_f10.rh_usuario_id,
            redis_url="redis://localhost:6379/0",
        )
    assert excinfo.value.codigo == "PONTO-VAL-001"


@pytest.mark.asyncio
async def test_criar_fechamento_empresa_id_nao_bate_com_periodo_e_val_001(
    sessao_f10, contexto_f10: ContextoF10
) -> None:
    corpo = esquemas.FechamentoCriar(
        periodoId=contexto_f10.periodo_id,
        escopo=esquemas.Escopo.empresa,
        empresaId=uuid.uuid4(),
        forcar=True,
    )
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.criar_fechamento(
            sessao_f10,
            contexto_f10.tenant_id,
            corpo,
            usuario_id=contexto_f10.rh_usuario_id,
            redis_url="redis://localhost:6379/0",
        )
    assert excinfo.value.codigo == "PONTO-VAL-001"


@pytest.mark.asyncio
async def test_criar_fechamento_escopo_unidade_sem_unidade_id_e_val_001(
    sessao_f10, contexto_f10: ContextoF10
) -> None:
    corpo = esquemas.FechamentoCriar(
        periodoId=contexto_f10.periodo_id,
        escopo=esquemas.Escopo.unidade,
        empresaId=contexto_f10.empresa_id,
        forcar=True,
    )
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.criar_fechamento(
            sessao_f10,
            contexto_f10.tenant_id,
            corpo,
            usuario_id=contexto_f10.rh_usuario_id,
            redis_url="redis://localhost:6379/0",
        )
    assert excinfo.value.codigo == "PONTO-VAL-001"


@pytest.mark.asyncio
async def test_criar_fechamento_escopo_departamento_sem_departamento_id_e_val_001(
    sessao_f10, contexto_f10: ContextoF10
) -> None:
    corpo = esquemas.FechamentoCriar(
        periodoId=contexto_f10.periodo_id,
        escopo=esquemas.Escopo.departamento,
        empresaId=contexto_f10.empresa_id,
        forcar=True,
    )
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.criar_fechamento(
            sessao_f10,
            contexto_f10.tenant_id,
            corpo,
            usuario_id=contexto_f10.rh_usuario_id,
            redis_url="redis://localhost:6379/0",
        )
    assert excinfo.value.codigo == "PONTO-VAL-001"


@pytest.mark.asyncio
async def test_criar_fechamento_com_unidade_inexistente_traduz_integridade(
    sessao_f10, contexto_f10: ContextoF10, redis_teste_url_f10: str
) -> None:
    """Escopo `unidade` com um `unidadeId` que não existe: nenhum vínculo
    resolve nesse escopo (pendência zero, passa a conferência), mas o
    `INSERT` em `fechamentos` viola a FK -- `traduzir_integridade` (T5)
    precisa converter isso em `PONTO-VAL-001` (a constraint da FK não está
    no catálogo `CODIGOS_POR_CONSTRAINT`, então cai no `padrao`)."""
    corpo = esquemas.FechamentoCriar(
        periodoId=contexto_f10.periodo_id,
        escopo=esquemas.Escopo.unidade,
        empresaId=contexto_f10.empresa_id,
        unidadeId=uuid.uuid4(),
        forcar=True,
    )
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.criar_fechamento(
            sessao_f10,
            contexto_f10.tenant_id,
            corpo,
            usuario_id=contexto_f10.rh_usuario_id,
            redis_url=redis_teste_url_f10,
        )
    assert excinfo.value.codigo == "PONTO-VAL-001"


# ---------------------------------------------------------------------------
# `listar_fechamentos` -- nenhum teste anterior chamava esta função; cobre
# os filtros e a paginação por cursor (segunda página via `proximoCursor`).
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_listar_fechamentos_filtra_e_pagina_por_cursor(
    sessao_f10, contexto_f10: ContextoF10
) -> None:
    agora = dt.datetime.now(tz=dt.UTC)
    mais_antigo = Fechamento(
        tenant_id=contexto_f10.tenant_id,
        periodo_id=contexto_f10.periodo_id,
        empresa_id=contexto_f10.empresa_id,
        unidade_id=contexto_f10.unidade_id,
        escopo="unidade",
        status="fechado",
        fechado_em=agora - dt.timedelta(minutes=2),
        criado_em=agora - dt.timedelta(minutes=2),
    )
    mais_novo = Fechamento(
        tenant_id=contexto_f10.tenant_id,
        periodo_id=contexto_f10.periodo_id,
        empresa_id=contexto_f10.empresa_id,
        unidade_id=contexto_f10.unidade_id,
        escopo="unidade",
        status="fechado",
        fechado_em=agora - dt.timedelta(minutes=1),
        criado_em=agora - dt.timedelta(minutes=1),
    )
    sessao_f10.add_all([mais_antigo, mais_novo])
    await sessao_f10.flush()

    linhas, paginacao = await servico.listar_fechamentos(
        sessao_f10,
        contexto_f10.tenant_id,
        periodo_id=contexto_f10.periodo_id,
        empresa_id=contexto_f10.empresa_id,
        unidade_id=contexto_f10.unidade_id,
        escopo="unidade",
        status="fechado",
        ordenar="fechadoEm:desc",
        limite=1,
    )
    assert [f.id for f in linhas] == [mais_novo.id]
    assert paginacao.tem_mais is True
    assert paginacao.proximo_cursor is not None

    segunda_pagina, paginacao_2 = await servico.listar_fechamentos(
        sessao_f10,
        contexto_f10.tenant_id,
        periodo_id=contexto_f10.periodo_id,
        ordenar="fechadoEm:desc",
        limite=1,
        cursor=paginacao.proximo_cursor,
    )
    assert [f.id for f in segunda_pagina] == [mais_antigo.id]
    assert paginacao_2.tem_mais is False


# ---------------------------------------------------------------------------
# `reabrir_fechamento` -- `dataInicio`/`dataFim` informados gravam
# `metadados` (nenhum teste anterior exercitava esse ramo).
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reabrir_com_data_inicio_e_fim_grava_metadados(
    sessao_f10, contexto_f10: ContextoF10
) -> None:
    periodo = await _periodo(sessao_f10, contexto_f10)
    fechamento = Fechamento(
        tenant_id=contexto_f10.tenant_id,
        periodo_id=periodo.id,
        empresa_id=contexto_f10.empresa_id,
        escopo="empresa",
        status="fechado",
        fechado_em=dt.datetime.now(tz=dt.UTC),
        fechado_por=contexto_f10.rh_usuario_id,
    )
    sessao_f10.add(fechamento)
    await sessao_f10.flush()
    await sessao_f10.commit()
    await aplicar_tenant_teste(sessao_f10, contexto_f10.tenant_id)

    await servico.reabrir_fechamento(
        sessao_f10,
        contexto_f10.tenant_id,
        fechamento.id,
        esquemas.ReaberturaRequisicao(
            motivo="Revisao de um sub-intervalo especifico do periodo (teste).",
            dataInicio=periodo.data_inicio,
            dataFim=periodo.data_inicio,
        ),
        usuario_id=contexto_f10.rh_usuario_id,
    )

    linha_auditoria = (
        (
            await sessao_f10.execute(
                sa.select(Auditoria).where(
                    Auditoria.tenant_id == contexto_f10.tenant_id,
                    Auditoria.entidade == "fechamentos",
                    Auditoria.acao == "reabrir",
                    Auditoria.entidade_id == fechamento.id,
                )
            )
        )
        .scalars()
        .one()
    )
    assert linha_auditoria.metadados is not None
    assert linha_auditoria.metadados["dataInicio"] == periodo.data_inicio.isoformat()
    assert linha_auditoria.metadados["dataFim"] == periodo.data_inicio.isoformat()
