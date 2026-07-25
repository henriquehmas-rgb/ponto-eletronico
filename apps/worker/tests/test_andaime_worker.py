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
def test_worker_settings_registra_as_oito_tarefas_do_catalogo() -> None:
    """`arq worker.main.WorkerSettings` enxerga exatamente as tarefas do catalogo."""
    registradas = [funcao.name for funcao in WorkerSettings.functions]
    assert registradas == list(NOMES_DAS_TAREFAS)
    assert len(registradas) == 8


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
@pytest.mark.asyncio
async def test_toda_tarefa_devolve_nao_implementado_sem_levantar() -> None:
    """Levantar excecao entraria no ciclo de retentativa e poluiria a fila."""
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
        resultado = await tarefa(ctx, **argumentos[tarefa.__name__])
        assert resultado["implementado"] is False
        assert resultado["codigo"] == CODIGO_NAO_IMPLEMENTADO
        assert resultado["tarefa"] == tarefa.__name__


@pytest.mark.asyncio
async def test_rotinas_de_cron_devolvem_nao_implementado_com_a_fase_certa() -> None:
    """A rotina de andaime aponta a fase que a implementa e o evento que produzira."""
    ctx: dict[str, Any] = {"job_id": "teste"}
    for rotina in (verificar_banco_horas_vencendo, verificar_terminal_offline):
        resultado = await rotina(ctx)
        assert resultado["implementado"] is False
        assert resultado["codigo"] == CODIGO_NAO_IMPLEMENTADO
        assert resultado["fase"] == ROTINAS[rotina.__name__]["fase"]
        assert resultado["evento"] == ROTINAS[rotina.__name__]["evento"]
