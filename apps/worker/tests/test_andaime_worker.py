"""Testes do andaime dos workers (Fase 0).

Nao testam regra de negocio -- nao existe nenhuma. Testam o que a Fase 0
promete e o que o `infra/docker-compose.yml` exige para os servicos `worker` e
`scheduler` subirem:

* os dois caminhos de importacao declarados em `infra/.env.example` resolvem;
* as oito tarefas do catalogo estao registradas com o nome que a API usara para
  enfileirar;
* as duas rotinas de cron exigidas por `events.yaml` (`origem: scheduler`)
  existem, com horario definido;
* worker e scheduler nao dividem chave de saude no Redis;
* toda tarefa devolve o resultado padrao `PONTO-INT-005` sem levantar excecao.

O nome do arquivo carrega o sufixo `_worker` de proposito: o CI roda
`pytest -q` a partir da RAIZ do monorepo, onde dois arquivos de teste de mesmo
nome em arvores diferentes colidem na importacao.
"""

from __future__ import annotations

import inspect
import pathlib
from typing import Any

import pytest
import yaml
from arq.worker import Worker

from worker.filas import CODIGO_NAO_IMPLEMENTADO, FILA_POR_TAREFA
from worker.main import CHAVE_SAUDE_WORKER, WorkerSettings
from worker.scheduler import (
    CHAVE_SAUDE_SCHEDULER,
    ROTINAS,
    SchedulerSettings,
    verificar_banco_horas_vencendo,
    verificar_terminal_offline,
)
from worker.tarefas import NOMES_DAS_TAREFAS, TAREFAS

EVENTOS = pathlib.Path(__file__).resolve().parents[3] / "packages" / "contracts" / "events.yaml"

#: Parametros que o `arq.worker.Worker` aceita. O ARQ monta o worker lendo, por
#: reflexao, os atributos da classe de settings cujo nome bate com um destes —
#: e **ignora em silencio** todos os outros. E o modo de falha mais traicoeiro
#: da biblioteca: um `max_trys` no lugar de `max_tries` nao levanta erro, so
#: deixa de valer.
PARAMETROS_DO_WORKER = frozenset(inspect.signature(Worker.__init__).parameters) - {"self"}


def _atributos_declarados(classe: type) -> set[str]:
    """Atributos publicos declarados no corpo da classe de settings."""
    return {nome for nome in vars(classe) if not nome.startswith("_")}


# ---------------------------------------------------------------------------
# Pontos de entrada
# ---------------------------------------------------------------------------
def test_worker_settings_registra_todas_as_tarefas_do_catalogo() -> None:
    """`arq worker.main.WorkerSettings` enxerga exatamente as tarefas do catalogo.

    RFC-005 (mesmo tratamento, agora para o worker): a contagem nao fica
    gravada em pedra porque cada fase que acrescenta uma tarefa real ao
    catalogo (`worker.tarefas.NOMES_DAS_TAREFAS`) faria este teste quebrar sem
    motivo -- o que importa e que `WorkerSettings` nunca perca nem duplique
    uma tarefa do catalogo, nao um numero fixo.
    """
    registradas = [funcao.name for funcao in WorkerSettings.functions]
    assert registradas == list(NOMES_DAS_TAREFAS)


def test_toda_tarefa_registrada_tem_fila_declarada() -> None:
    """Tarefa sem fila planejada e tarefa que ninguem sabe onde vai rodar."""
    for nome in NOMES_DAS_TAREFAS:
        assert nome in FILA_POR_TAREFA


@pytest.mark.parametrize("classe", [WorkerSettings, SchedulerSettings])
def test_nenhum_atributo_de_settings_e_ignorado_pelo_arq(classe: type) -> None:
    """Atributo com nome fora da assinatura do `Worker` seria descartado sem aviso."""
    ignorados = _atributos_declarados(classe) - PARAMETROS_DO_WORKER
    assert ignorados == set(), f"{classe.__name__} declara atributo que o ARQ ignora: {ignorados}"


def test_scheduler_settings_registra_as_duas_rotinas_de_cron() -> None:
    """`arq worker.scheduler.SchedulerSettings` tem as rotinas com horario definido."""
    crons = SchedulerSettings.cron_jobs
    assert sorted(job.name for job in crons) == sorted(ROTINAS)
    for job in crons:
        # `None` em todos os campos significaria "a cada segundo".
        assert (job.hour, job.minute, job.second) != (None, None, None)


def test_scheduler_nao_registra_as_tarefas_pesadas() -> None:
    """Cron roda no proprio processo: AFD de 12 meses nao pode entrar aqui."""
    assert list(SchedulerSettings.functions) == []


def test_worker_e_scheduler_nao_dividem_chave_de_saude() -> None:
    """Chave compartilhada faria `arq --check` de um responder pela vida do outro."""
    assert CHAVE_SAUDE_WORKER != CHAVE_SAUDE_SCHEDULER
    assert WorkerSettings.health_check_key == CHAVE_SAUDE_WORKER
    assert SchedulerSettings.health_check_key == CHAVE_SAUDE_SCHEDULER


def test_filas_do_worker_e_do_scheduler_sao_distintas() -> None:
    """O scheduler nao disputa a fila do worker."""
    assert WorkerSettings.queue_name != SchedulerSettings.queue_name


# ---------------------------------------------------------------------------
# Contrato de eventos
# ---------------------------------------------------------------------------
def test_todo_evento_com_origem_scheduler_tem_rotina_produtora() -> None:
    """`events.yaml` declara 2 eventos de origem scheduler; ambos tem produtor."""
    catalogo = yaml.safe_load(EVENTOS.read_text(encoding="utf-8"))
    do_scheduler = {
        evento["nome"] for evento in catalogo["eventos"] if evento.get("origem") == "scheduler"
    }
    cobertos = {meta["evento"] for meta in ROTINAS.values()}
    assert do_scheduler, "events.yaml deveria declarar eventos com origem scheduler"
    assert do_scheduler <= cobertos


# ---------------------------------------------------------------------------
# Resultado padrao do andaime
# ---------------------------------------------------------------------------
#: Tarefas do catalogo que ja saem do andaime (fase dona ja as implementou de
#: verdade). RFC-005 (mesmo tratamento, agora para o worker): este teste so
#: cobre o CONTRATO de andaime (stub que nunca levanta excecao); a tarefa real
#: precisa de banco/Redis de verdade e e testada pela propria fase dona --
#: `importar_colaboradores` (F2/A3) tem sua cobertura em
#: `apps/api/tests/f2/importadores/test_worker_tarefa.py`;
#: `apurar_dia`/`recalcular_periodo` (F4) em
#: `apps/api/tests/f4/dominio/test_apurar_dia_worker.py` e
#: `apps/api/tests/f4/performance/test_performance_recalculo.py`;
#: `sincronizar_terminal` (F6/A2) em `apps/device-gw/tests/f6/provisionamento/
#: test_sincronizar_terminal.py`; `processar_fechamento`/`gerar_espelhos`
#: (F10) em `apps/api/tests/f10/fechamento/test_worker_tarefas.py`;
#: `executar_relatorio` (F11) em
#: `apps/api/tests/f11/agendamentos/test_worker_executar_relatorio.py`;
#: `gerar_afd`/`gerar_aej` (F12) em `apps/api/tests/f12/afd/test_gerador.py`
#: e `apps/api/tests/f12/aej/test_gerador.py`; `enviar_webhook` (F13/A3) em
#: `apps/api/tests/f13/webhooks/**`; `importar_arquivo_generico` (F13/A8) em
#: `apps/api/tests/f13/importadores/**`; `exportar_folha` (F13/A5) em
#: `apps/api/tests/f13/folha/comum/test_execucao.py` (ponta a ponta, via
#: `app.integracoes.folha.comum.execucao.executar_exportacao_folha`, que
#: `exportar_folha` chama por import tardio); `processar_fila_notificacoes`
#: (F10) em `apps/api/tests/f10/notificacao/test_processar_fila_notificacoes.py`;
#: `expurgo_lgpd` (F14/A3) em `apps/worker/tests/f14/lgpd/test_expurgo_lgpd.py`
#: (fiacao do wrapper) e `apps/api/tests/f14/lgpd/test_expurgo.py` (logica de
#: negocio, `app.lgpd.expurgo.aplicar_politicas_vencidas`).
_TAREFAS_JA_IMPLEMENTADAS = frozenset(
    {
        "importar_colaboradores",
        "apurar_dia",
        "recalcular_periodo",
        "processar_fechamento",
        "gerar_espelhos",
        "executar_relatorio",
        "gerar_afd",
        "gerar_aej",
        "sincronizar_terminal",
        "enviar_webhook",
        "importar_arquivo_generico",
        "exportar_folha",
        "processar_fila_notificacoes",
        "expurgo_lgpd",
    }
)

#: Mesma logica, para as rotinas de cron do scheduler. `verificar_terminal_offline`
#: (F6/A1) e real; cobertura em `apps/worker/tests/f6/test_verificar_terminal_offline.py`.
#: `verificar_banco_horas_vencendo` (F4/T7/A2) tambem e real; cobertura em
#: `apps/api/tests/f4/banco_horas/test_vencimento.py`.
_ROTINAS_JA_IMPLEMENTADAS = frozenset(
    {"verificar_terminal_offline", "verificar_banco_horas_vencendo"}
)


@pytest.mark.asyncio
async def test_toda_tarefa_devolve_nao_implementado_sem_levantar() -> None:
    """Levantar excecao entraria no ciclo de retentativa e poluiria a fila.

    Cobre so as tarefas que ainda sao stub de andaime -- ver
    `_TAREFAS_JA_IMPLEMENTADAS` para as que ja saem desta regra.
    """
    ctx: dict[str, Any] = {"job_id": "teste", "job_try": 1}
    argumentos: dict[str, dict[str, Any]] = {
        "apurar_dia": {"tenant_id": "t", "vinculo_id": "v", "data": "2026-07-25"},
        "recalcular_periodo": {
            "tenant_id": "t",
            "inicio": "2026-07-01",
            "fim": "2026-07-31",
        },
        "gerar_afd": {
            "tenant_id": "t",
            "rep_p_id": "r",
            "inicio": "2026-07-01",
            "fim": "2026-07-31",
        },
        "gerar_aej": {
            "tenant_id": "t",
            "empresa_id": "e",
            "inicio": "2026-07-01",
            "fim": "2026-07-31",
        },
        "executar_relatorio": {"tenant_id": "t", "execucao_id": "e", "codigo": "espelho-mensal"},
        "enviar_webhook": {
            "tenant_id": "t",
            "entrega_id": "d",
            "webhook_id": "w",
            "evento": "marcacao.criada",
        },
        "sincronizar_terminal": {"tenant_id": "t", "terminal_id": "term"},
        "expurgo_lgpd": {"tenant_id": "t"},
    }
    for tarefa in TAREFAS:
        if tarefa.__name__ in _TAREFAS_JA_IMPLEMENTADAS:
            continue
        resultado = await tarefa(ctx, **argumentos[tarefa.__name__])
        assert resultado["implementado"] is False
        assert resultado["codigo"] == CODIGO_NAO_IMPLEMENTADO
        assert resultado["tarefa"] == tarefa.__name__


@pytest.mark.asyncio
async def test_rotinas_de_cron_devolvem_nao_implementado_com_a_fase_certa() -> None:
    """A rotina de andaime aponta a fase que a implementa e o evento que produzira.

    Cobre so as rotinas que ainda sao stub de andaime -- ver
    `_ROTINAS_JA_IMPLEMENTADAS` para as que ja saem desta regra.
    """
    ctx: dict[str, Any] = {"job_id": "teste"}
    for rotina in (verificar_banco_horas_vencendo, verificar_terminal_offline):
        if rotina.__name__ in _ROTINAS_JA_IMPLEMENTADAS:
            continue
        resultado = await rotina(ctx)
        assert resultado["implementado"] is False
        assert resultado["codigo"] == CODIGO_NAO_IMPLEMENTADO
        assert resultado["fase"] == ROTINAS[rotina.__name__]["fase"]
        assert resultado["evento"] == ROTINAS[rotina.__name__]["evento"]
