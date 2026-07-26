"""Ponto de entrada do processo `scheduler` (ARQ com `cron`).

E este modulo que `infra/docker-compose.yml` executa no servico `scheduler`::

    arq worker.scheduler.SchedulerSettings                # producao
    arq worker.scheduler.SchedulerSettings --watch /app   # desenvolvimento

O caminho de importacao e contrato: `infra/.env.example` declara
`ARQ_SCHEDULER_SETTINGS=worker.scheduler.SchedulerSettings`, o `command` do
container usa essa variavel e o `healthcheck` roda `arq --check` sobre ela
(o servico exporta o valor tambem como `ARQ_WORKER_SETTINGS`, que e o nome que
o healthcheck le).

Por que um processo separado do `worker`
----------------------------------------

No ARQ, `cron_jobs` sao executados **pelo proprio processo** que os declara, e
nao enfileirados para outro consumir. Se o `worker` acumulasse as duas funcoes,
uma geracao de AFD de 12 meses segurando todas as vagas de `max_jobs` atrasaria
a rotina que detecta terminal fora do ar — justamente a rotina cuja utilidade e
ser pontual. Por isso o scheduler roda com `ARQ_SCHEDULER_MAX_JOBS=2` (compose)
e nao registra nenhuma das oito tarefas pesadas: quando houver trabalho de
verdade, ele **enfileira** para o `worker` com `ctx["redis"].enqueue_job(...)`.

Duas rotinas sao exigidas pelo catalogo de eventos
--------------------------------------------------

`packages/contracts/events.yaml` declara exatamente dois eventos com
`origem: scheduler`. Sem estas rotinas eles nao teriam produtor possivel:

======================== ===================================================
`banco_horas.vencendo`   "Rotina diaria do scheduler que projeta o vencimento
                         por conta aberta" — dispara uma vez por antecedencia
                         configurada (padrao 30, 15 e 7 dias), por conta.
`terminal.offline`       "Quando a rotina de saude constata ausencia de contato
                         acima do limite configurado para o modo de comunicacao
                         do terminal."
======================== ===================================================

Fase 0 entrega ANDAIME: o cron esta definido e registrado, e o corpo devolve um
resultado marcado como nao implementado (`PONTO-INT-005`). A projecao de
vencimento chega na F4 (Banco de Horas) e a deteccao de terminal mudo na F6
(Integracao Control iD).
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from typing import Any, ClassVar, Final

from arq.connections import RedisSettings
from arq.cron import CronJob, cron

from worker.config import Configuracao, obter_configuracao
from worker.filas import CODIGO_NAO_IMPLEMENTADO, FILA_MANUTENCAO
from worker.log import configurar_log, obter_logger

# `montar_redis` vem de `worker.main` para que os dois processos leiam a mesma
# `REDIS_URL` do mesmo jeito. O import traz junto o `WorkerSettings`, que e
# construido no import de `main` — sao apenas objetos em memoria, sem I/O e sem
# nada registrado: o scheduler continua sem conhecer as oito tarefas pesadas.
from worker.main import montar_redis
from worker.terminais_saude import (
    TerminalAtivo,
    gravar_amostra_saude,
    ja_esta_marcado_offline,
    limite_offline_minutos,
    listar_terminais_ativos_cross_tenant,
    publicar_terminal_offline,
)

logger = obter_logger("scheduler")

#: Chave propria de saude: worker e scheduler dividem o mesmo Redis, e chave
#: compartilhada faria o `arq --check` de um responder pela vida do outro.
CHAVE_SAUDE_SCHEDULER: Final[str] = "ponto:scheduler:health"

INTERVALO_SAUDE_S: Final[int] = 20

#: Fase de FASES-E-AGENTES.md que implementa cada rotina, e evento do catalogo
#: que ela passara a produzir. Documental na Fase 0 — e o que impede a rotina de
#: virar orfa: quem chegar na F4 e na F6 encontra o ponteiro pronto.
ROTINAS: Final[dict[str, dict[str, str]]] = {
    "verificar_banco_horas_vencendo": {"fase": "F4", "evento": "banco_horas.vencendo"},
    "verificar_terminal_offline": {"fase": "F6", "evento": "terminal.offline"},
}


def _resultado_rotina(rotina: str, **contexto: Any) -> dict[str, Any]:
    """Resultado padrao das rotinas de andaime do scheduler.

    Espelha `worker.filas.resultado_nao_implementado` de proposito, sem reusa-lo:
    aquela funcao consulta os mapas das **oito tarefas do catalogo**, e as
    rotinas de cron nao pertencem a esse catalogo (a API nao as enfileira por
    nome; quem as dispara e o relogio). Reusar produziria `fase: "?"` e a fila
    errada — informacao pior do que nenhuma.

    Devolve em vez de levantar pela mesma razao das tarefas: excecao entraria no
    ciclo de retentativa do ARQ e encheria o log de falha que nao e falha.
    """
    meta = ROTINAS.get(rotina, {})
    return {
        "implementado": False,
        "codigo": CODIGO_NAO_IMPLEMENTADO,
        "rotina": rotina,
        "fase": meta.get("fase", "?"),
        "evento": meta.get("evento", ""),
        "executadoEm": dt.datetime.now(tz=dt.UTC).isoformat(),
        "contexto": contexto,
    }


async def verificar_banco_horas_vencendo(ctx: dict[Any, Any]) -> dict[str, Any]:
    """Projeta o vencimento das contas de banco de horas abertas. Implementacao na F4.

    O que a F4 fara aqui, para que o cron ja esteja no horario certo: percorrer
    as contas abertas por tenant, comparar o vencimento de cada bloco de saldo
    com as antecedencias da politica (padrao 30, 15 e 7 dias) e publicar
    `banco_horas.vencendo` uma vez por antecedencia e por conta — nunca duas
    vezes para o mesmo par, o que exige marca de "ja avisado" persistida.

    Roda de madrugada, depois da virada do dia e antes do expediente: o aviso
    precisa chegar ao gestor no comeco do dia util, e a projecao le muita linha.
    """
    logger.info(
        "rotina verificar_banco_horas_vencendo disparada",
        extra={"jobId": ctx.get("job_id"), "evento": "banco_horas.vencendo"},
    )
    return _resultado_rotina("verificar_banco_horas_vencendo")


async def verificar_terminal_offline(ctx: dict[Any, Any]) -> dict[str, Any]:
    """Detecta coletor sem sinal ha mais tempo que o tolerado (F6/T9).

    Compara `ultimo_contato_em` de cada terminal `ativo`, de TODOS os
    tenants, com o limite do **modo de comunicacao** do equipamento
    (`worker.terminais_saude.limite_offline_minutos` — Push, Monitor e
    polling/direto toleram folgas diferentes, documentado la). Grava uma
    amostra em `terminal_saude` a cada verificacao (append-only) e publica
    `terminal.offline` **so na transicao** para offline — nunca a cada
    varredura — usando a ultima amostra conhecida como marca de "ja
    avisado" (`ja_esta_marcado_offline`).

    A enumeracao cross-tenant usa uma segunda credencial de banco
    (`database_url_suporte`, RFC-013, interino) porque este e um cron
    global, sem `tenant_id` de entrada — ver docstring de
    `worker/terminais_saude.py`.

    Roda a cada cinco minutos porque marcacao nao se perde quando o terminal
    cai (o equipamento guarda localmente e o catch-up recupera), mas o RH
    precisa saber cedo que a catraca da portaria parou de responder.
    """
    config = obter_configuracao()
    agora = dt.datetime.now(tz=dt.UTC)
    terminais = await listar_terminais_ativos_cross_tenant(config)
    verificados = 0
    alertados = 0

    for terminal in terminais:
        online, minutos_sem_contato = _classificar(terminal, agora)
        if not online:
            estava_offline = await ja_esta_marcado_offline(config, terminal.tenant_id, terminal.id)
        else:
            estava_offline = False

        await gravar_amostra_saude(
            config, tenant_id=terminal.tenant_id, terminal_id=terminal.id, online=online
        )
        verificados += 1

        if not online and not estava_offline:
            publicar_terminal_offline(
                tenant_id=terminal.tenant_id,
                terminal_id=terminal.id,
                empresa_id=terminal.empresa_id,
                numero_serie=terminal.numero_serie,
                fabricante=terminal.fabricante,
                ultimo_contato_em=terminal.ultimo_contato_em,
                minutos_sem_contato=minutos_sem_contato,
                unidade_id=terminal.unidade_id,
            )
            alertados += 1

    logger.info(
        "rotina verificar_terminal_offline concluida",
        extra={
            "jobId": ctx.get("job_id"),
            "evento": "terminal.offline",
            "terminaisVerificados": verificados,
            "alertasPublicados": alertados,
        },
    )
    return {
        "implementado": True,
        "rotina": "verificar_terminal_offline",
        "terminaisVerificados": verificados,
        "alertasPublicados": alertados,
        "executadoEm": agora.isoformat(),
    }


def _classificar(terminal: TerminalAtivo, agora: dt.datetime) -> tuple[bool, int]:
    """Devolve `(online, minutos_sem_contato)`. Terminal que nunca fez
    contato conta como offline, com `minutos_sem_contato` medido como um
    numero grande (nunca `None`, para o payload do evento continuar um
    inteiro valido)."""
    if terminal.ultimo_contato_em is None:
        return False, 10**6
    ultimo = terminal.ultimo_contato_em
    if ultimo.tzinfo is None:
        ultimo = ultimo.replace(tzinfo=dt.UTC)
    minutos_sem_contato = int((agora - ultimo).total_seconds() // 60)
    limite = limite_offline_minutos(terminal.modo_comunicacao, terminal.intervalo_push_segundos)
    return minutos_sem_contato <= limite, minutos_sem_contato


def montar_cron() -> list[CronJob]:
    """Agenda das rotinas periodicas.

    O horario segue o relogio **local do processo**, que o compose fixa em
    `TZ=America/Sao_Paulo` e o Dockerfile materializa instalando `tzdata` e
    apontando `/etc/localtime`. Nao ha `timezone` explicito no `SchedulerSettings`
    porque o parametro do ARQ aceita um `datetime.timezone` — deslocamento
    constante —, e deslocamento constante erra a virada do horario de verao,
    que e exatamente a noite em que ninguem quer descobrir o problema.

    `unique=True` (padrao) e o que impede execucao dupla quando houver mais de
    uma replica do scheduler: a trava fica no proprio Redis.
    """
    return [
        # Diaria, 04:10. Depois da virada do dia (para a projecao enxergar o dia
        # fechado) e bem antes do expediente.
        cron(
            verificar_banco_horas_vencendo,
            name="verificar_banco_horas_vencendo",
            hour=4,
            minute=10,
            second=0,
            timeout=900,
            max_tries=1,
        ),
        # A cada 5 minutos.
        cron(
            verificar_terminal_offline,
            name="verificar_terminal_offline",
            minute={0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55},
            second=0,
            timeout=120,
            max_tries=1,
        ),
    ]


async def ao_iniciar(ctx: dict[Any, Any]) -> None:
    """Prepara o contexto do scheduler e registra a agenda no log de subida."""
    config: Configuracao = obter_configuracao()
    configurar_log(config)
    ctx["config"] = config
    ctx["iniciado_em"] = dt.datetime.now(tz=dt.UTC)
    logger.info(
        "scheduler iniciado",
        extra={
            "ambiente": config.ambiente,
            "versao": config.versao,
            "commit": config.commit,
            "fila": FILA_MANUTENCAO,
            "rotinas": sorted(ROTINAS),
        },
    )


async def ao_encerrar(ctx: dict[Any, Any]) -> None:
    """Encerramento limpo, simetrico ao `ao_iniciar`."""
    logger.info("scheduler encerrado", extra={"rotinas": sorted(ROTINAS)})


_config = obter_configuracao()


class SchedulerSettings:
    """Configuracao lida por reflexao pelo comando `arq`.

    Vale a mesma regra do `WorkerSettings`: atributo cujo nome nao bata com um
    parametro de `arq.worker.Worker` e ignorado sem aviso.
    """

    #: Nenhuma das oito tarefas pesadas. Ver "Por que um processo separado".
    functions: ClassVar[Sequence[Any]] = ()

    cron_jobs: ClassVar[Sequence[CronJob]] = montar_cron()

    #: Fila propria: o scheduler nao disputa `FILA_PADRAO` com o worker.
    queue_name: ClassVar[str] = FILA_MANUTENCAO

    redis_settings: ClassVar[RedisSettings] = montar_redis(_config)

    on_startup: ClassVar[Any] = ao_iniciar
    on_shutdown: ClassVar[Any] = ao_encerrar

    #: `ARQ_SCHEDULER_MAX_JOBS=2` no compose. Rotina de cron e leve e curta; o
    #: trabalho pesado que ela vier a gerar vai para a fila do worker.
    max_jobs: ClassVar[int] = 2

    #: Rotina de cron nao e retentada por padrao (`max_tries=1` em cada `cron`):
    #: se a varredura das 04:10 falhar, a das 04:10 de amanha cobre o buraco, e
    #: repetir uma projecao de vencimento correria o risco de avisar duas vezes.
    retry_jobs: ClassVar[bool] = False

    health_check_key: ClassVar[str] = CHAVE_SAUDE_SCHEDULER
    health_check_interval: ClassVar[int] = INTERVALO_SAUDE_S


__all__ = [
    "CHAVE_SAUDE_SCHEDULER",
    "INTERVALO_SAUDE_S",
    "ROTINAS",
    "SchedulerSettings",
    "ao_encerrar",
    "ao_iniciar",
    "montar_cron",
    "verificar_banco_horas_vencendo",
    "verificar_terminal_offline",
]
