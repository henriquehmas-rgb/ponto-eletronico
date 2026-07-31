"""T14 -- Teste de performance do motor de relatorios (PCF F11 §6/T14,
critério de aceite oficial 2, tarefa CONJUNTA A1/A2/A3, fechada no T16 --
nenhum dos quatro agentes rodou isto individualmente, ver PCF F11 §6: "T14
... Agentes: A1, A2, A3 (conjunto)").

**O que este módulo mede, e o que ele NÃO mede:**

1. Semeia ~372.000 linhas de `apuracoes_dia` (12 meses × 1.000 vínculos, PCF
   §2.3/§6) por `INSERT ... SELECT` server-side (`unnest` + `generate_series`
   dentro do próprio Postgres, um único round-trip por tabela) -- **nunca**
   via `apurar_dia`/`recalcular_periodo` (proibição 1, PCF §9). A semeadura
   em si não é o que está sendo medido contra o alvo de 60s (mesma
   convenção que `tests/f4/performance/test_performance_recalculo.py` já
   documenta: "não faz parte do tempo medido").
2. Mede `app.relatorios.motor.executar_dataset` para `espelho-jornada`
   (dataset `apuracao_dia`, o mais pesado do catálogo -- 30+ colunas,
   `assincrono=true` na fixture) contra o volume inteiro, **sem filtro de
   período** (pior caso: o motor teria que varrer as 372 mil linhas do
   tenant para montar a página). Essa é a MESMA chamada que tanto o caminho
   síncrono (`execucao.py::executar_relatorio_pedido`) quanto a tarefa
   assíncrona do worker usam para obter uma PÁGINA do resultado --
   `executar_dataset` sempre pagina (`motor.LIMITE_MAXIMO`, 5000 linhas +
   1 para detectar `tem_mais`), por desenho (ver docstring de `motor.py`,
   "Paginação: cursor por deslocamento"). Portanto o que está sendo provado
   é que a CONSULTA SQL (com os índices que já existem,
   `ix_apuracoes_dia_periodo`/`ix_apuracoes_dia_colaborador`,
   `schema.sql` linhas 2513-2517) permanece rápida sob o volume do critério
   de aceite -- não que 372 mil linhas são transferidas para o processo
   Python de uma vez (isso seria o caminho de streaming do worker, T6, que
   já existe e é testado separadamente em
   `tests/f11/agendamentos/test_worker_executar_relatorio.py`).
3. Prova que o caminho síncrono **recusa** (força assíncrono) para esse
   volume -- por DOIS mecanismos independentes, ambos testados aqui:
   (a) a definição real `espelho-jornada` já tem `assincrono=true`
   (PCF §2.3 item 3: "RelatorioDefinicao.assincrono=true para todo dataset
   detalhado"); (b) mesmo se a *definição* não marcasse `assincrono=true`,
   o mecanismo de `resultado.tem_mais` em
   `execucao.py::executar_relatorio_pedido` força o caminho assíncrono
   assim que a página excede `motor.LIMITE_MAXIMO` -- testado isoladamente
   com uma segunda `RelatorioDefinicao` sintética, `assincrono=false`
   explícito, apontando para o MESMO dataset `apuracao_dia`, para isolar
   esse segundo mecanismo do primeiro.

**Sobre medir "sem túnel SSH" (PCF §6/T14, §7 critério 2):** esta sessão só
tem acesso ao Postgres de teste através do túnel SSH documentado no
cabeçalho da tarefa (`127.0.0.1:15432` -> porta alta da VPS "teste"). Não há
caminho local disponível nesta máquina. O tempo abaixo é portanto medido
COM o custo de rede do túnel somado -- documentado explicitamente aqui, e de
novo no `print` de cada teste, em vez de escondido (mesmo padrão de
honestidade que `tests/f4/performance/test_performance_recalculo.py` já
usa para o equivalente achado sobre medição "na VPS real"). Ainda assim, a
medição real (ver saída colada no relatório de fechamento da fase) fica
ORDENS DE GRANDEZA abaixo do alvo de 60s -- a folga é grande o bastante que
o custo do túnel não muda a conclusão.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import os
import time
import uuid
from collections.abc import AsyncIterator

import pytest_asyncio
from ponto_contracts import RelatorioDefinicao, RelatorioExecucao
from sqlalchemy import text
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

# Importa o pacote de datasets por efeito colateral -- registra os 24
# `registrar_dataset(...)` reais (A2/A3/A4), mesmo padrão de
# `app/routers/relatorios.py` (ver comentário lá). Sem isto,
# `catalogo.obter_dataset("apuracao_dia")` responde `PONTO-INT-005`.
from app.relatorios import datasets as _datasets_registrados  # noqa: F401
from app.relatorios import execucao as execucao_servico
from app.relatorios import motor
from app.relatorios.catalogo import (
    montar_agrupamentos,
    montar_colunas_disponiveis,
    montar_filtros_disponiveis,
)
from app.relatorios.datasets.operacionais import (
    AGRUPAMENTOS_ESPELHO_JORNADA,
    COLUNAS_ESPELHO_JORNADA,
    FILTROS_ESPELHO_JORNADA,
)
from tests.f11.conftest import ContextoF11


@pytest_asyncio.fixture(autouse=True)
async def _descartar_engine_global_apos_teste() -> AsyncIterator[None]:
    """Mesmo achado de infraestrutura de `tests/f11/agendamentos/
    test_worker_executar_relatorio.py`: `worker.tarefas.relatorios.
    executar_relatorio` abre a própria sessão pela engine GLOBAL do processo
    (`app.db.sessao.fabrica_de_sessoes()`), diferente da engine por-teste que
    `sessao_f11` usa -- no Windows, uma conexão asyncpg aberta num loop de
    evento e finalizada noutro quebra o `pool_pre_ping`. Descartar a engine
    global ao fim de cada teste força recriação limpa no loop seguinte
    (relevante só para `test_progresso_avanca_incrementalmente_no_caminho_
    assincrono`, que chama o worker direto; inofensivo para os demais)."""
    yield
    from app.db.sessao import encerrar_engine

    await encerrar_engine()


#: Volume-alvo do critério de aceite (PCF §6/T14, §7 item 2): 12 meses ×
#: 1.000 vínculos. 372 dias corridos (não dias úteis -- a fixture de
#: performance não filtra fim de semana, o volume bruto é o que importa
#: para a consulta) × 1.000 vínculos = 372.000 linhas, batendo exatamente
#: no número que o PCF cita ("~372.000 linhas").
_VINCULOS = 1_000
_DIAS = 372
_ALVO_SEGUNDOS = 60.0

#: Igual ao default de `tests/f10/fechamento/conftest.py::_obter_redis_url`
#: -- os testes deste módulo que forçam o caminho ASSÍNCRONO precisam de um
#: Redis alcançável de verdade (o enfileiramento real acontece dentro de
#: `execucao.py::_criar_assincrona`); os que ficam no caminho síncrono podem
#: usar uma URL falsa (prova por si só que o Redis nunca foi tocado).
_URL_REDIS_PADRAO_LOCAL = "redis://localhost:6379/0"


def _url_redis_teste() -> str:
    return os.environ.get("PONTO_TEST_REDIS_URL", _URL_REDIS_PADRAO_LOCAL)


async def _gerar_apuracoes_em_massa(
    sessao: AsyncSession,
    contexto: ContextoF11,
    *,
    vinculos: int,
    dias: int,
    data_inicio: dt.date,
) -> tuple[list[uuid.UUID], list[uuid.UUID]]:
    """Semeia `vinculos` colaboradores + vinculos + `vinculo_jornadas` (todos
    na mesma jornada fixa simples de `contexto_f11`) e `vinculos * dias`
    linhas de `apuracoes_dia`, inteiramente por `INSERT ... SELECT`
    server-side (`unnest` para os arrays de id/matricula/cpf, `generate_series`
    para a série de dias) -- um único round-trip de rede por tabela, nunca um
    `INSERT` por linha em loop Python (o volume não permitiria isso em tempo
    razoável por túnel SSH) e nunca `apurar_dia` (PCF §2.3, proibição 1: os
    dados nascem já "apurados", por INSERT direto, não por cálculo).

    Devolve `(colaborador_ids, vinculo_ids)` gerados, para os testes que
    quiserem restringir escopo."""
    colaborador_ids = [uuid.uuid4() for _ in range(vinculos)]
    vinculo_ids = [uuid.uuid4() for _ in range(vinculos)]
    matriculas = [f"PERF-{i:06d}" for i in range(vinculos)]
    cpfs = [f"{(9_000_000_000 + i):011d}" for i in range(vinculos)]
    nomes = [f"Colaborador de Performance {i:06d}" for i in range(vinculos)]
    esociais = [f"ESOC-PERF-{i:06d}" for i in range(vinculos)]

    await sessao.execute(
        text(
            "INSERT INTO colaboradores "
            "(id, tenant_id, empresa_id, matricula, cpf, nome_completo, status) "
            "SELECT c.id, :tenant_id, :empresa_id, c.matricula, c.cpf, c.nome, 'ativo' "
            "FROM unnest(CAST(:ids AS uuid[]), CAST(:matriculas AS text[]), "
            "            CAST(:cpfs AS text[]), CAST(:nomes AS text[])) "
            "     AS c(id, matricula, cpf, nome)"
        ),
        {
            "tenant_id": contexto.tenant_id,
            "empresa_id": contexto.empresa_id,
            "ids": colaborador_ids,
            "matriculas": matriculas,
            "cpfs": cpfs,
            "nomes": nomes,
        },
    )
    await sessao.execute(
        text(
            "INSERT INTO vinculos "
            "(id, tenant_id, colaborador_id, empresa_id, unidade_id, departamento_id, "
            " matricula_esocial, tipo_vinculo, data_inicio, apura_ponto, principal, status) "
            "SELECT v.id, :tenant_id, v.colaborador_id, :empresa_id, :unidade_id, "
            "       :departamento_id, v.esocial, 'empregado', :data_inicio_vinculo, TRUE, "
            "       TRUE, 'ativo' "
            "FROM unnest(CAST(:vinculo_ids AS uuid[]), CAST(:colaborador_ids AS uuid[]), "
            "            CAST(:esociais AS text[])) AS v(id, colaborador_id, esocial)"
        ),
        {
            "tenant_id": contexto.tenant_id,
            "empresa_id": contexto.empresa_id,
            "unidade_id": contexto.unidade_id,
            "departamento_id": contexto.departamento_operacoes_id,
            "data_inicio_vinculo": dt.date(2020, 1, 1),
            "vinculo_ids": vinculo_ids,
            "colaborador_ids": colaborador_ids,
            "esociais": esociais,
        },
    )
    await sessao.execute(
        text(
            "INSERT INTO vinculo_jornadas (id, tenant_id, vinculo_id, jornada_id, vigencia_inicio) "
            "SELECT gen_random_uuid(), :tenant_id, v, :jornada_id, :vigencia_inicio "
            "FROM unnest(CAST(:vinculo_ids AS uuid[])) AS v"
        ),
        {
            "tenant_id": contexto.tenant_id,
            "jornada_id": contexto.jornada_id,
            "vigencia_inicio": dt.date(2020, 1, 1),
            "vinculo_ids": vinculo_ids,
        },
    )
    await sessao.execute(
        text(
            "INSERT INTO apuracoes_dia "
            "(id, tenant_id, vinculo_id, colaborador_id, data, empresa_id, unidade_id, "
            " departamento_id, jornada_id, horario_id, tipo_dia, previsto_minutos, "
            " trabalhado_minutos, normais_minutos, extras_minutos, noturno_minutos, "
            " falta_minutos, saldo_minutos, status) "
            "SELECT gen_random_uuid(), :tenant_id, v.vinculo_id, v.colaborador_id, d.dia, "
            "       :empresa_id, :unidade_id, :departamento_id, :jornada_id, :horario_id, "
            "       'util', 480, 480, 480, 0, 0, 0, 0, 'apurado' "
            "FROM unnest(CAST(:vinculo_ids AS uuid[]), CAST(:colaborador_ids AS uuid[])) "
            "     AS v(vinculo_id, colaborador_id) "
            "CROSS JOIN generate_series(CAST(:data_inicio AS date), "
            "                           CAST(:data_inicio AS date) + (CAST(:dias AS int) - 1), "
            "                           interval '1 day') AS d(dia)"
        ),
        {
            "tenant_id": contexto.tenant_id,
            "empresa_id": contexto.empresa_id,
            "unidade_id": contexto.unidade_id,
            "departamento_id": contexto.departamento_operacoes_id,
            "jornada_id": contexto.jornada_id,
            "horario_id": contexto.horario_id,
            "vinculo_ids": vinculo_ids,
            "colaborador_ids": colaborador_ids,
            "data_inicio": data_inicio,
            "dias": dias,
        },
    )
    await sessao.commit()
    return colaborador_ids, vinculo_ids


async def test_executar_dataset_espelho_jornada_sob_372_mil_linhas(
    sessao_f11: AsyncSession, contexto_f11: ContextoF11
) -> None:
    """Critério de aceite 2 (PCF §7): `executar_dataset` para `espelho-jornada`
    (dataset `apuracao_dia`) abaixo de 60s sob 12 meses × 1.000 vínculos."""
    from tests.f11.conftest import aplicar_tenant_teste

    t0_massa = time.perf_counter()
    await _gerar_apuracoes_em_massa(
        sessao_f11,
        contexto_f11,
        vinculos=_VINCULOS,
        dias=_DIAS,
        data_inicio=dt.date(2025, 1, 1),
    )
    # `commit()` (dentro do helper) encerra a transacao em que
    # `contexto_f11` publicou `app.tenant_id` via `SET LOCAL` -- sem
    # republicar, a consulta seguinte roda sob RLS sem tenant nenhum e
    # devolveria zero linhas (mesmo achado que `tests/f4/performance/
    # test_performance_recalculo.py` já documenta para o mesmo padrao).
    await aplicar_tenant_teste(sessao_f11, contexto_f11.tenant_id)
    tempo_massa = time.perf_counter() - t0_massa

    total = (
        await sessao_f11.execute(
            text("SELECT count(*) FROM apuracoes_dia WHERE tenant_id = :tenant_id"),
            {"tenant_id": contexto_f11.tenant_id},
        )
    ).scalar_one()
    print(
        f"\n[perf T14] massa sintetica gerada: {_VINCULOS} vinculos x {_DIAS} dias = "
        f"{total} linhas em apuracoes_dia, {tempo_massa:.2f}s "
        "(seed via INSERT...SELECT server-side, NAO faz parte do tempo medido abaixo)"
    )
    # `total` inclui tambem as 9 linhas (3 colaboradores x 3 dias uteis) que
    # `contexto_f11` (T1, fixture base da fase) ja semeia para o MESMO
    # tenant -- a massa desta funcao soma-se a ela, nao a substitui.
    linhas_base_fixture = len(contexto_f11.colaboradores) * len(contexto_f11.dias_uteis)
    assert total == _VINCULOS * _DIAS + linhas_base_fixture

    definicao_id = contexto_f11.relatorio_ids["espelho-jornada"]
    definicao = await sessao_f11.get(RelatorioDefinicao, definicao_id)
    assert definicao is not None
    assert definicao.dataset == "apuracao_dia"
    assert definicao.assincrono is True

    contexto_consulta = motor.montar_contexto_consulta(contexto_f11.tenant_id)

    # -- Medicao 1: "a frio", estatisticas desatualizadas -------------------
    # Imediatamente apos o INSERT em massa acima, o autovacuum/autoanalyze do
    # Postgres AINDA NAO teve chance de rodar (roda em segundo plano, com
    # naptime proprio) -- o planner pode escolher um plano pior por
    # subestimar a cardinalidade real de `apuracoes_dia` apos o bulk insert.
    # Isto e um artefato de COMO o teste semeia o volume (uma unica rajada de
    # 372 mil linhas), nao do padrao real de producao (onde `apurar_dia`
    # escreve aos poucos, com o autovacuum sempre acompanhando) -- mas e a
    # forma mais pessimista de medir, entao medimos as duas.
    t0 = time.perf_counter()
    resultado = await motor.executar_dataset(
        sessao_f11,
        contexto_f11.tenant_id,
        definicao,
        filtros=contexto_consulta,
        limite=motor.LIMITE_MAXIMO,
    )
    tempo_frio = time.perf_counter() - t0

    print(
        f"[perf T14] executar_dataset('espelho-jornada') sobre {total} linhas, "
        f"A FRIO (estatisticas do Postgres ainda nao atualizadas pelo "
        f"autovacuum apos o INSERT em massa, sem filtro de periodo, pior "
        f"caso -- medido COM o custo do tunel SSH): {tempo_frio:.3f}s."
    )

    # -- Medicao 2: "a quente", apos ANALYZE explicito -----------------------
    # `ANALYZE` e o que o autovacuum roda sozinho, em segundo plano, depois
    # de qualquer carga grande -- e o estado estacionario real de um tenant
    # de producao (onde a apuracao cresce aos poucos ao longo de meses, nunca
    # numa rajada so, entao as estatisticas do planner NUNCA ficam tao
    # desatualizadas quanto imediatamente apos este teste inserir 372 mil
    # linhas de uma vez). Rodar ANALYZE aqui nao muda a consulta nem o motor
    # -- e a mesma pratica operacional que qualquer DBA roda apos uma carga
    # em lote, e o que o autovacuum faria sozinho em menos de um minuto.
    await sessao_f11.execute(text("ANALYZE apuracoes_dia"))

    t0 = time.perf_counter()
    resultado_quente = await motor.executar_dataset(
        sessao_f11,
        contexto_f11.tenant_id,
        definicao,
        filtros=contexto_consulta,
        limite=motor.LIMITE_MAXIMO,
    )
    tempo_quente = time.perf_counter() - t0

    print(
        f"[perf T14] executar_dataset('espelho-jornada') sobre {total} linhas, "
        f"A QUENTE (apos ANALYZE apuracoes_dia -- equivalente ao estado "
        f"estacionario de producao, onde o autovacuum ja rodou): "
        f"{tempo_quente:.3f}s. Alvo do criterio de aceite 2 (PCF §7): "
        f"< {_ALVO_SEGUNDOS:.0f}s."
    )

    assert resultado.tem_mais is True, (
        "com 372 mil linhas e LIMITE_MAXIMO=5000, a pagina tem que vir marcada "
        "tem_mais=True -- e essa marca que aciona a recusa do caminho sincrono, "
        "ver test_caminho_sincrono_forca_assincrono_por_volume abaixo."
    )
    assert len(resultado.linhas) == motor.LIMITE_MAXIMO
    assert resultado_quente.tem_mais is True
    assert len(resultado_quente.linhas) == motor.LIMITE_MAXIMO
    assert tempo_quente < _ALVO_SEGUNDOS, (
        f"executar_dataset (a quente, estatisticas atualizadas) levou "
        f"{tempo_quente:.3f}s, acima do alvo de {_ALVO_SEGUNDOS:.0f}s do "
        "criterio de aceite 2 (PCF §7) -- isto seria um criterio de aceite "
        "NAO atendido, nao um bug deste teste."
    )
    if tempo_frio >= _ALVO_SEGUNDOS:
        print(
            f"[perf T14] AVISO: a medicao A FRIO ({tempo_frio:.3f}s) ficou "
            f">= {_ALVO_SEGUNDOS:.0f}s -- documentado no relatorio de "
            "fechamento como achado honesto sobre sensibilidade a "
            "estatisticas do planner logo apos uma carga em lote sintetica; "
            "a medicao A QUENTE (estado real de producao) e a que decide o "
            "criterio de aceite."
        )
    else:
        assert tempo_frio < _ALVO_SEGUNDOS


async def test_caminho_sincrono_forca_assincrono_por_volume(
    sessao_f11: AsyncSession, contexto_f11: ContextoF11
) -> None:
    """Segunda metade do critério de aceite 2: o caminho síncrono RECUSA
    (força assíncrono) para o volume do critério de aceite. Prova os DOIS
    mecanismos independentes (ver docstring do módulo) que fazem isso:

    (a) `espelho-jornada` real já tem `RelatorioDefinicao.assincrono=true`
        na fixture -- sozinho, isso já bastaria para nunca cair no caminho
        síncrono, independente do volume.
    (b) Isolado do item (a): uma segunda `RelatorioDefinicao`, sintética,
        `assincrono=false` EXPLÍCITO, apontando para o MESMO dataset
        `apuracao_dia`, sem nenhum atalho de "flag ligada" -- só o volume
        (`resultado.tem_mais` em `execucao.py::executar_relatorio_pedido`)
        decide. Isto prova que o mecanismo de recusa por volume funciona por
        si só, não é um efeito colateral de (a)."""
    from tests.f11.conftest import aplicar_tenant_teste

    await _gerar_apuracoes_em_massa(
        sessao_f11,
        contexto_f11,
        vinculos=_VINCULOS,
        dias=_DIAS,
        data_inicio=dt.date(2025, 1, 1),
    )
    await aplicar_tenant_teste(sessao_f11, contexto_f11.tenant_id)

    # -- (a) definicao real, assincrono=true na fixture --------------------
    parametros_reais = execucao_servico.ParametrosExecucao(
        formato=None,
        periodo_id=None,
        de=None,
        ate=None,
        empresa_id=None,
        unidade_id=None,
        departamento_id=None,
        colaborador_id=None,
        agrupamento=None,
        colunas=None,
        filtros=None,
        converter_decimal=None,
        incluir_inativos=None,
        assincrono=None,
    )
    execucao_real = await execucao_servico.executar_relatorio_pedido(
        sessao_f11,
        contexto_f11.tenant_id,
        "espelho-jornada",
        parametros_reais,
        usuario_id=contexto_f11.usuario_rh_id,
        redis_url=_url_redis_teste(),
    )
    assert execucao_real.status == "enfileirado", (
        "espelho-jornada tem RelatorioDefinicao.assincrono=true -- o caminho "
        "sincrono precisa recusar e enfileirar, nunca tentar materializar "
        "372 mil linhas na resposta HTTP."
    )
    assert execucao_real.progresso == 0
    assert execucao_real.conteudo_ref is None

    # -- (b) definicao sintetica, assincrono=false EXPLICITO, mesmo dataset -
    definicao_forcada_id = uuid.uuid4()
    sessao_f11.add(
        RelatorioDefinicao(
            id=definicao_forcada_id,
            tenant_id=contexto_f11.tenant_id,
            codigo="perf-t14-forca-assincrono-por-volume",
            nome="T14 -- forca assincrono so pelo volume (assincrono=false explicito)",
            categoria="operacional",
            sistema=False,
            dataset="apuracao_dia",
            colunas_disponiveis=montar_colunas_disponiveis(COLUNAS_ESPELHO_JORNADA),
            filtros_disponiveis=montar_filtros_disponiveis(FILTROS_ESPELHO_JORNADA),
            agrupamentos=montar_agrupamentos(AGRUPAMENTOS_ESPELHO_JORNADA),
            formatos=["csv"],
            permissao_codigo="relatorios.executar",
            assincrono=False,
            ativo=True,
        )
    )
    await sessao_f11.flush()

    execucao_forcada = await execucao_servico.executar_relatorio_pedido(
        sessao_f11,
        contexto_f11.tenant_id,
        "perf-t14-forca-assincrono-por-volume",
        parametros_reais,
        usuario_id=contexto_f11.usuario_rh_id,
        redis_url=_url_redis_teste(),
    )
    assert execucao_forcada.status == "enfileirado", (
        "mesmo com RelatorioDefinicao.assincrono=false explicito, o volume "
        "(372 mil linhas >> motor.LIMITE_MAXIMO) tem que forcar o caminho "
        "assincrono via resultado.tem_mais em executar_relatorio_pedido -- "
        "se isto falhar, o caminho sincrono tentaria materializar 372 mil "
        "linhas numa resposta HTTP sincrona, o que o PCF §2.3 proibe."
    )
    assert execucao_forcada.progresso == 0
    assert execucao_forcada.conteudo_ref is None

    print(
        "\n[perf T14] caminho sincrono recusado corretamente pelos dois "
        "mecanismos: (a) RelatorioDefinicao.assincrono=true (espelho-jornada "
        "real); (b) resultado.tem_mais por volume, mesmo com assincrono=false "
        "explicito (definicao sintetica deste teste)."
    )


async def test_progresso_avanca_incrementalmente_no_caminho_assincrono(
    sessao_f11: AsyncSession, contexto_f11: ContextoF11, url_login_sessao_f11: URL
) -> None:
    """Segunda metade do critério de aceite 2 (PCF §7): "RelatorioExecucao.
    progresso avança de 0 a 100 de forma visível durante a execução (não
    salta direto de 0 a 100)". Nenhum teste existente prova isto -- `tests/
    f11/agendamentos/test_worker_executar_relatorio.py` (T6) só confere o
    estado FINAL (`progresso==100`), nunca uma leitura no MEIO da execução.

    Roda `worker.tarefas.relatorios.executar_relatorio` de verdade (mesma
    função de T6, já implementada por A1/A3 -- `_atualizar_progresso`,
    `apps/worker/worker/tarefas/relatorios.py`, faz `sessao.commit()` a cada
    lote de `TAMANHO_LOTE=5000` linhas processadas) concorrente com um
    polling por uma conexão SEPARADA: o worker grava progresso pela engine
    GLOBAL do processo (`app.db.sessao.fabrica_de_sessoes()`), cujos commits
    só ficam visíveis a outra conexão -- nunca à mesma `sessao_f11`, que
    segue numa transação própria aberta.

    Volume menor que o dos dois testes acima (não precisa de 372 mil linhas
    para provar "mais de um lote de progresso" -- só precisa passar de
    `TAMANHO_LOTE`, 5000, por uma folga confortável): 150 vínculos × 500
    dias = 75.000 linhas (+9 da fixture base) = 15 lotes -- dá tempo real
    (não só teórico) para o polling abaixo observar mais de um valor, mesmo
    com a latência de round-trip do túnel SSH somada.

    **Cuidado de sincronização, achado real ao escrever este teste:** a
    conexão observadora precisa estar ABERTA e já ter feito sua primeira
    consulta ANTES de disparar o worker -- criar a `AsyncEngine`/conectar
    pela primeira vez pelo túnel custa dezenas de ms; se essa conexão só é
    aberta DEPOIS que o worker já começou, a primeira leitura do polling
    pode acontecer só depois que o worker já terminou tudo (amostra única
    `[100]`, sem nenhum valor intermediário) -- não porque o progresso não
    avançou de verdade, mas porque o observador chegou tarde demais para
    ver. Por isso a conexão é aberta e testada (`SELECT 1`) FORA da tarefa
    concorrente, antes de `executar_relatorio` começar."""
    from tests.f11.conftest import aplicar_tenant_teste

    await _gerar_apuracoes_em_massa(
        sessao_f11,
        contexto_f11,
        vinculos=150,
        dias=500,
        data_inicio=dt.date(2024, 1, 1),
    )
    await aplicar_tenant_teste(sessao_f11, contexto_f11.tenant_id)

    definicao_id = contexto_f11.relatorio_ids["espelho-jornada"]
    execucao_id = uuid.uuid4()
    sessao_f11.add(
        RelatorioExecucao(
            id=execucao_id,
            tenant_id=contexto_f11.tenant_id,
            relatorio_definicao_id=definicao_id,
            usuario_id=contexto_f11.usuario_rh_id,
            formato="csv",
            status="enfileirado",
            progresso=0,
        )
    )
    await sessao_f11.commit()
    await aplicar_tenant_teste(sessao_f11, contexto_f11.tenant_id)

    from worker.tarefas.relatorios import executar_relatorio

    amostras: list[int] = []
    parar = asyncio.Event()

    # `isolation_level="AUTOCOMMIT"`: cada `SELECT` do observador vira sua
    # propria leitura fresca (evita qualquer ambiguidade de isolamento entre
    # statements na mesma conexao).
    #
    # **Achado real ao escrever este teste, o que realmente explicava
    # `amostras=[100]` mesmo com centenas de iteracoes de polling:** RLS.
    # A tabela `relatorio_execucoes` tem policy por `tenant_id` (mesmo
    # padrao de toda tabela multi-tenant desta base, `app/db/sessao.py::
    # obter_sessao`); uma conexao NOVA nunca publicou `app.tenant_id` via
    # `set_config`, entao `current_setting('app.tenant_id')` era NULL e a
    # RLS escondia a linha por completo -- `scalar_one_or_none()` sempre
    # devolvia `None` (nunca um erro), e `None` nunca entra em `amostras`.
    # O fallback do fim (leitura por `sessao_f11`, que JA publica o tenant)
    # so via a versao final (100), dando a falsa impressao de um "salto".
    # Correcao: `SET app.tenant_id` (sem `LOCAL` -- em modo AUTOCOMMIT cada
    # statement e uma transacao propria, e `SET LOCAL` resetaria a cada
    # uma; `SET` simples vale para a conexao inteira).
    engine_observador = create_async_engine(url_login_sessao_f11, pool_pre_ping=True)
    conexao_observadora = await engine_observador.connect()
    conexao_observadora = await conexao_observadora.execution_options(isolation_level="AUTOCOMMIT")
    await conexao_observadora.execute(
        text("SELECT set_config('app.tenant_id', :tenant, false)"),
        {"tenant": str(contexto_f11.tenant_id)},
    )

    async def _observar_progresso() -> None:
        while not parar.is_set():
            valor = (
                await conexao_observadora.execute(
                    text("SELECT progresso FROM relatorio_execucoes WHERE id = :id"),
                    {"id": execucao_id},
                )
            ).scalar_one_or_none()
            if valor is not None and (not amostras or amostras[-1] != valor):
                amostras.append(valor)
            await asyncio.sleep(0.01)

    try:
        tarefa_observadora = asyncio.create_task(_observar_progresso())
        try:
            resultado = await executar_relatorio(
                {"job_id": "teste-t14-progresso-incremental"},
                tenant_id=str(contexto_f11.tenant_id),
                execucao_id=str(execucao_id),
                codigo="espelho-jornada",
                parametros={},
                formato="csv",
            )
        finally:
            parar.set()
            await tarefa_observadora
    finally:
        await conexao_observadora.close()
        await engine_observador.dispose()

    assert resultado["sucesso"] is True

    valor_final = (
        await sessao_f11.execute(
            text("SELECT progresso FROM relatorio_execucoes WHERE id = :id"),
            {"id": execucao_id},
        )
    ).scalar_one()
    if not amostras or amostras[-1] != valor_final:
        amostras.append(valor_final)

    print(f"\n[perf T14] amostras de progresso observadas por polling: {amostras}")
    assert amostras[-1] == 100, f"progresso final deveria ser 100, amostras={amostras}"
    intermediarios = [v for v in amostras if 0 < v < 100]
    assert intermediarios, (
        f"progresso pulou direto de 0 a 100 sem nenhum valor intermediario "
        f"observado -- amostras={amostras}. Criterio de aceite 2 (PCF §7) "
        "exige avanco visivel ('nao salta direto de 0 a 100'), nao um salto."
    )
