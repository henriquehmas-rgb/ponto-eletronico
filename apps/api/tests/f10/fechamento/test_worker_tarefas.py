"""Testes de `worker.tarefas.fechamento` (T9, F10/A2) -- `processar_fechamento`
e `gerar_espelhos`, chamados diretamente (sem subir um processo ARQ real,
mesmo padrão que os testes de `worker.tarefas.apuracao` de F4 usam: a
tarefa é uma função `async` comum, o `ctx` é só um dicionário).

**Pré-requisito de ambiente, documentado no relatório da fase:** este
arquivo importa `worker.tarefas.fechamento`, do pacote `ponto-worker`
(`apps/worker`) -- instalado como dependência editável no venv de
`apps/api` só para teste (`pip install -e ../worker --no-deps`), o mesmo
sentido de import que `apps/worker` já faz de `apps/api` em produção
(ADR-009), aqui invertido *só para o processo de teste*, nunca para o
código de aplicação em si (nenhum módulo de `app/**` importa `worker.**`).
Também requer `DATABASE_URL` no ambiente (além de `PONTO_TEST_DATABASE_URL`
que a fixture compartilhada já usa): `processar_fechamento`/`gerar_espelhos`
abrem sua PRÓPRIA sessão via `app.db.sessao.fabrica_de_sessoes()` (mesmo
caminho da produção, onde o worker é um processo à parte, sem a sessão de
teste), que lê `DATABASE_URL` via `app.core.config.Configuracao` -- uma
fonte de configuração completamente diferente da fixture de teste.

**Achado de infraestrutura de teste, documentado em `docs/backlog.md`:**
`app.db.sessao` (congelado, fora do meu ownership) memoriza a `AsyncEngine`
em uma variável de módulo presa ao *event loop* em que nasceu (documentado
no próprio docstring do arquivo, mecanismo já existente para o caso do
`TestClient` síncrono). Quando MAIS DE UM teste desta suíte chama uma tarefa
do worker (cada teste do pytest-asyncio ganha seu próprio *event loop* por
padrão, `asyncio_default_fixture_loop_scope = "function"`), a conexão antiga
pode ser finalizada DEPOIS que o loop que a criou já fechou, e o
encerramento assíncrono da conexão (`asyncpg`) explode com `RuntimeError:
Event loop is closed` -- um problema de infraestrutura de teste, não do
código desta fase (as quatro funções abaixo passam 100% quando rodadas
isoladas, uma de cada vez; ver relatório da fase). `_encerrar_engine_worker`
(fixture abaixo) descarta a engine ao fim de CADA teste, enquanto o loop
daquele teste ainda está vivo, evitando a limpeza tardia."""

from __future__ import annotations

import pytest
from ponto_contracts import ApuracaoDia, Auditoria, Espelho, Fechamento, Periodo
from sqlalchemy import select

from tests.f10.conftest import ContextoF10, aplicar_tenant_teste


@pytest.fixture(autouse=True)
async def _encerrar_engine_worker():
    """Descarta, ao fim de cada teste, a `AsyncEngine` que `app.db.sessao`
    memoriza globalmente -- enquanto o *event loop* deste teste ainda está
    vivo (ver docstring do módulo). Sem isto, o teste seguinte (com um loop
    novo) herda uma conexão presa ao loop anterior, já fechado."""
    yield
    from app.db.sessao import encerrar_engine

    await encerrar_engine()


async def _periodo(sessao, contexto: ContextoF10) -> Periodo:
    return await sessao.get(Periodo, contexto.periodo_id)


async def _semear_apuracoes(sessao, contexto: ContextoF10, periodo: Periodo) -> None:
    sessao.add(
        ApuracaoDia(
            tenant_id=contexto.tenant_id,
            vinculo_id=contexto.vinculo_id,
            colaborador_id=contexto.colaborador_id,
            data=periodo.data_inicio,
            empresa_id=contexto.empresa_id,
            tipo_dia="util",
            previsto_minutos=480,
            trabalhado_minutos=480,
            status="apurado",
        )
    )
    await sessao.flush()


@pytest.mark.asyncio
async def test_processar_fechamento_trava_e_publica_um_periodo_fechado(
    sessao_f10, contexto_f10: ContextoF10
) -> None:
    from worker.tarefas.fechamento import processar_fechamento

    from app.workflow.fechamento.eventos import BARRAMENTO_INTERNO, limpar_barramento

    limpar_barramento()
    periodo = await _periodo(sessao_f10, contexto_f10)
    await _semear_apuracoes(sessao_f10, contexto_f10, periodo)

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

    resultado = await processar_fechamento(
        {"job_id": "teste-1"},
        tenant_id=str(contexto_f10.tenant_id),
        fechamento_id=str(fechamento.id),
        gerar_espelhos=False,
        usuario_id=str(contexto_f10.rh_usuario_id),
    )
    assert resultado["implementado"] is True
    assert resultado["totalVinculos"] == 1

    # `processar_fechamento` comita numa sessao PROPRIA (`app.db.sessao`,
    # producao real de worker) -- `sessao_f10` ainda tem `fechamento` no
    # identity map com o valor de ANTES da chamada (`expire_on_commit=False`
    # na fixture). `refresh` forca reler do banco, mesmo gotcha ja corrigido
    # em `tests/f10/espelhos/test_assinatura.py::test_verificacao_e_
    # recomputacao`.
    await aplicar_tenant_teste(sessao_f10, contexto_f10.tenant_id)
    await sessao_f10.refresh(fechamento)
    assert fechamento.status == "fechado"
    assert fechamento.fechado_em is not None
    assert fechamento.hash_conteudo is not None

    eventos = [e for e in BARRAMENTO_INTERNO if e["tipo"] == "periodo.fechado"]
    assert len(eventos) == 1
    assert eventos[0]["dados"]["fechamentoId"] == str(fechamento.id)

    # A apuracao NAO foi tocada por escrita (proibicao 5 do PCF; ver
    # docstring do worker) -- fechamento_id/status continuam como estavam.
    apuracao = (
        await sessao_f10.execute(
            select(ApuracaoDia).where(
                ApuracaoDia.tenant_id == contexto_f10.tenant_id,
                ApuracaoDia.vinculo_id == contexto_f10.vinculo_id,
                ApuracaoDia.data == periodo.data_inicio,
            )
        )
    ).scalar_one()
    assert apuracao.fechamento_id is None
    assert apuracao.status == "apurado"

    linhas_auditoria = (
        (
            await sessao_f10.execute(
                select(Auditoria).where(
                    Auditoria.tenant_id == contexto_f10.tenant_id,
                    Auditoria.entidade == "fechamentos",
                    Auditoria.acao == "fechar",
                    Auditoria.entidade_id == fechamento.id,
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(linhas_auditoria) == 1

    limpar_barramento()


@pytest.mark.asyncio
async def test_processar_fechamento_gera_espelhos_quando_pedido(
    sessao_f10, contexto_f10: ContextoF10
) -> None:
    from worker.tarefas.fechamento import processar_fechamento

    periodo = await _periodo(sessao_f10, contexto_f10)
    await _semear_apuracoes(sessao_f10, contexto_f10, periodo)

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

    resultado = await processar_fechamento(
        {"job_id": "teste-2"},
        tenant_id=str(contexto_f10.tenant_id),
        fechamento_id=str(fechamento.id),
        gerar_espelhos=True,
        usuario_id=str(contexto_f10.rh_usuario_id),
    )
    assert resultado["espelhosGerados"] == 1

    await aplicar_tenant_teste(sessao_f10, contexto_f10.tenant_id)
    espelhos = (
        (
            await sessao_f10.execute(
                select(Espelho).where(
                    Espelho.tenant_id == contexto_f10.tenant_id,
                    Espelho.fechamento_id == fechamento.id,
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(espelhos) == 1
    assert espelhos[0].tipo == "oficial"
    assert espelhos[0].vinculo_id == contexto_f10.vinculo_id


@pytest.mark.asyncio
async def test_gerar_espelhos_worker_gera_um_por_vinculo(
    sessao_f10, contexto_f10: ContextoF10
) -> None:
    from worker.tarefas.fechamento import gerar_espelhos

    periodo = await _periodo(sessao_f10, contexto_f10)
    await _semear_apuracoes(sessao_f10, contexto_f10, periodo)
    await sessao_f10.commit()
    await aplicar_tenant_teste(sessao_f10, contexto_f10.tenant_id)

    resultado = await gerar_espelhos(
        {"job_id": "teste-3"},
        tenant_id=str(contexto_f10.tenant_id),
        periodo_id=str(periodo.id),
        vinculo_ids=[str(contexto_f10.vinculo_id)],
        tipo="previo",
        gerar_pdf=False,
        usuario_id=str(contexto_f10.rh_usuario_id),
    )
    assert resultado["espelhosGerados"] == 1

    await aplicar_tenant_teste(sessao_f10, contexto_f10.tenant_id)
    espelhos = (
        (
            await sessao_f10.execute(
                select(Espelho).where(
                    Espelho.tenant_id == contexto_f10.tenant_id,
                    Espelho.periodo_id == periodo.id,
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(espelhos) == 1
    assert espelhos[0].tipo == "previo"


@pytest.mark.asyncio
async def test_criar_fechamento_para_periodo_ja_fechado_e_per_002_sincrono(
    sessao_f10, contexto_f10: ContextoF10, redis_teste_url_f10: str
) -> None:
    """ "Uma segunda chamada a criarFechamento para o mesmo periodo/escopo
    ja fechado responde PONTO-PER-002 (via a checagem sincrona da T5, nao
    do worker)" -- critério "pronto quando" de T9, provado fechando de
    verdade via `processar_fechamento` e então tentando `criarFechamento`
    de novo."""
    from worker.tarefas.fechamento import processar_fechamento

    from app.core.erros import ErroDeAplicacao
    from app.schemas import contrato as esquemas
    from app.workflow.fechamento import servico

    periodo = await _periodo(sessao_f10, contexto_f10)
    await _semear_apuracoes(sessao_f10, contexto_f10, periodo)

    corpo = esquemas.FechamentoCriar(
        periodoId=contexto_f10.periodo_id,
        escopo=esquemas.Escopo.empresa,
        empresaId=contexto_f10.empresa_id,
        forcar=True,
    )
    resposta = await servico.criar_fechamento(
        sessao_f10,
        contexto_f10.tenant_id,
        corpo,
        usuario_id=contexto_f10.rh_usuario_id,
        redis_url=redis_teste_url_f10,
    )
    await sessao_f10.commit()
    await aplicar_tenant_teste(sessao_f10, contexto_f10.tenant_id)

    await processar_fechamento(
        {"job_id": "teste-4"},
        tenant_id=str(contexto_f10.tenant_id),
        fechamento_id=str(resposta.id),
        gerar_espelhos=False,
        usuario_id=str(contexto_f10.rh_usuario_id),
    )
    await aplicar_tenant_teste(sessao_f10, contexto_f10.tenant_id)

    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.criar_fechamento(
            sessao_f10,
            contexto_f10.tenant_id,
            corpo,
            usuario_id=contexto_f10.rh_usuario_id,
            redis_url=redis_teste_url_f10,
        )
    assert excinfo.value.codigo == "PONTO-PER-002"
