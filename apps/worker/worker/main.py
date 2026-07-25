"""Ponto de entrada do processo `worker` (ARQ sobre Redis 7).

E este modulo que `infra/docker-compose.yml` executa no servico `worker`::

    arq worker.main.WorkerSettings                # producao
    arq worker.main.WorkerSettings --watch /app   # desenvolvimento (override dev)

O caminho de importacao e contrato: `infra/.env.example` declara
`ARQ_WORKER_SETTINGS=worker.main.WorkerSettings`, o `command` do container usa
essa variavel e o `healthcheck` do mesmo container roda
`arq --check "$ARQ_WORKER_SETTINGS"`. Renomear a classe ou o modulo quebra os
tres de uma vez.

**Estado desta versao.** Fase 0 entrega ANDAIME. As oito tarefas do catalogo
(`worker/tarefas/__init__.py`) estao registradas com nome, fila e assinatura
definitivos e devolvem `PONTO-INT-005`. Nenhum calculo acontece aqui: a
apuracao chega na F4, os arquivos fiscais na F12, os relatorios na F11, os
webhooks na F13.

Tres decisoes que ficam visiveis no codigo abaixo
-------------------------------------------------

1. **Nenhuma conexao com PostgreSQL na subida.** Igual ao `apps/api`: o
   processo precisa subir e responder ao `arq --check` mesmo com o banco fora.
   Conectar no `on_startup` transformaria indisponibilidade de dependencia em
   *crash loop*, que e mais dificil de diagnosticar e ainda tira do ar o unico
   sinal que diria o que esta errado. O engine sobe na F4, sob demanda.
2. **Uma fila so na Fase 0.** `worker/filas.py` ja separa as seis filas
   definitivas, mas um unico processo consome `FILA_PADRAO` enquanto nada tem
   custo real. A partir da F4 basta subir replicas apontando
   `ARQ_WORKER_SETTINGS` para uma subclasse com outro `queue_name`; nenhuma
   linha de tarefa muda.
3. **Retentativa e do ARQ, nao da tarefa.** As tarefas de andaime *devolvem*
   um resultado marcado como nao implementado em vez de levantar excecao —
   levantar entraria no ciclo de retentativa e ficaria batendo no Redis ate
   esgotar `max_tries`, poluindo fila e log com falha que nao e falha (ver
   `worker/filas.py`).
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from typing import Any, ClassVar, Final

from arq.connections import RedisSettings
from arq.worker import Function, func

from worker.config import Configuracao, obter_configuracao
from worker.filas import FILA_PADRAO
from worker.log import configurar_log, obter_logger
from worker.tarefas import NOMES_DAS_TAREFAS, TAREFAS

logger = obter_logger("main")

#: Chave no Redis onde o ARQ grava o batimento de saude do worker. Explicita, e
#: nao derivada do `queue_name`, porque worker e scheduler dividem o mesmo Redis
#: e um health check que colide diz "saudavel" sobre o processo errado.
CHAVE_SAUDE_WORKER: Final[str] = "ponto:worker:health"

#: De quanto em quanto tempo o batimento e regravado. O ARQ da a chave um TTL de
#: `intervalo + 1` segundos; o `healthcheck` do compose consulta a cada 30 s.
#: 20 s deixa margem para uma regravacao perdida sem derrubar o container.
INTERVALO_SAUDE_S: Final[int] = 20


def montar_redis(config: Configuracao) -> RedisSettings:
    """Traduz `REDIS_URL` para o `RedisSettings` que o ARQ espera.

    O ARQ nao aceita URL: quer host, porta, banco e senha separados. A quebra
    vive em `Configuracao.redis` para que worker e scheduler leiam a mesma
    variavel de ambiente que a API (`REDIS_URL`, do bloco `x-python-env` do
    compose) e ninguem precise manter duas formas de dizer a mesma coisa.
    """
    destino = config.redis
    senha = destino.senha.get_secret_value()
    return RedisSettings(
        host=destino.host,
        port=destino.port,
        database=destino.database,
        password=senha or None,
        conn_timeout=10,
        conn_retries=5,
        conn_retry_delay=2,
    )


def montar_funcoes(config: Configuracao) -> list[Function]:
    """Envolve cada tarefa do catalogo com os limites de execucao do processo.

    `arq.worker.func` e o jeito nativo de registrar: fixa o **nome** com que a
    tarefa e enfileirada (o nome e contrato — a API enfileira por ele) e permite
    prazo, retencao de resultado e numero de tentativas por tarefa. Na Fase 0
    todas usam os mesmos limites, vindos da configuracao; a partir da F12 a
    geracao de AFD provavelmente vai querer prazo proprio, e o lugar de mexer
    ja esta pronto.
    """
    return [
        func(
            tarefa,
            name=tarefa.__name__,
            timeout=config.arq_timeout_job_s,
            keep_result=config.arq_retencao_resultado_s,
            max_tries=config.arq_max_tentativas,
        )
        for tarefa in TAREFAS
    ]


async def ao_iniciar(ctx: dict[Any, Any]) -> None:
    """Prepara o contexto compartilhado por todos os jobs do processo.

    O `ctx` do ARQ ja chega com `redis`, `job_id` e `job_try`. Aqui entram a
    configuracao resolvida e o instante de subida — o suficiente para o log
    identificar o processo. Sem banco e sem MinIO de proposito (ver o cabecalho
    do modulo).
    """
    config = obter_configuracao()
    configurar_log(config)
    ctx["config"] = config
    ctx["iniciado_em"] = dt.datetime.now(tz=dt.UTC)
    logger.info(
        "worker iniciado",
        extra={
            "ambiente": config.ambiente,
            "versao": config.versao,
            "commit": config.commit,
            "fila": FILA_PADRAO,
            "maxJobs": config.arq_max_jobs,
            "tarefas": list(NOMES_DAS_TAREFAS),
        },
    )


async def ao_encerrar(ctx: dict[Any, Any]) -> None:
    """Encerramento limpo. O ARQ ja espera os jobs em voo antes de chamar aqui."""
    iniciado_em = ctx.get("iniciado_em")
    segundos = (
        (dt.datetime.now(tz=dt.UTC) - iniciado_em).total_seconds()
        if isinstance(iniciado_em, dt.datetime)
        else None
    )
    logger.info("worker encerrado", extra={"segundosNoAr": segundos})


async def ao_iniciar_job(ctx: dict[Any, Any]) -> None:
    """Marca o inicio do job. `job_try` distingue primeira execucao de retentativa.

    O `ctx` do ARQ nao carrega o nome da tarefa neste ponto — so `job_id`,
    `job_try`, `enqueue_time` e `score`. O nome aparece no log da propria tarefa
    e no log do ARQ; aqui o que interessa e o par inicio/fim para medir duracao.
    """
    ctx["job_iniciado_em"] = dt.datetime.now(tz=dt.UTC)
    logger.info(
        "job iniciado",
        extra={
            "jobId": ctx.get("job_id"),
            "tentativa": ctx.get("job_try"),
            "enfileiradoEm": str(ctx.get("enqueue_time") or ""),
        },
    )


async def ao_encerrar_job(ctx: dict[Any, Any]) -> None:
    """Fecha o par do evento anterior com a duracao medida.

    O ARQ ja registra sucesso e falha por conta propria. O que se ganha aqui e a
    duracao no **mesmo formato JSON** do resto da casa, para a F15 conseguir
    montar percentil de duracao por tarefa em Loki sem parser especial.
    """
    iniciado_em = ctx.get("job_iniciado_em")
    duracao_ms = (
        round((dt.datetime.now(tz=dt.UTC) - iniciado_em).total_seconds() * 1000)
        if isinstance(iniciado_em, dt.datetime)
        else None
    )
    logger.info(
        "job encerrado",
        extra={
            "jobId": ctx.get("job_id"),
            "tentativa": ctx.get("job_try"),
            "duracaoMs": duracao_ms,
        },
    )


_config = obter_configuracao()


class WorkerSettings:
    """Configuracao que o comando `arq` le por reflexao.

    O ARQ instancia `arq.worker.Worker` com os atributos desta classe cujo nome
    bate com um parametro do construtor. Atributo com nome fora dessa lista e
    silenciosamente ignorado — por isso nada aqui e "quase" o nome certo.
    """

    #: As oito tarefas do catalogo, com nome de enfileiramento fixado.
    functions: ClassVar[Sequence[Function]] = montar_funcoes(_config)

    #: Fila unica na Fase 0. Ver decisao 2 no cabecalho do modulo.
    queue_name: ClassVar[str] = FILA_PADRAO

    redis_settings: ClassVar[RedisSettings] = montar_redis(_config)

    on_startup: ClassVar[Any] = ao_iniciar
    on_shutdown: ClassVar[Any] = ao_encerrar
    on_job_start: ClassVar[Any] = ao_iniciar_job
    on_job_end: ClassVar[Any] = ao_encerrar_job

    #: Jobs simultaneos no processo. Vem de `ARQ_MAX_JOBS` (compose).
    max_jobs: ClassVar[int] = _config.arq_max_jobs

    #: Prazo de um job. AFD de 12 meses e relatorio de 1.000 colaboradores sao
    #: longos por natureza; o padrao do ARQ (300 s) mataria os dois.
    job_timeout: ClassVar[int] = _config.arq_timeout_job_s

    #: Quanto tempo o resultado sobrevive no Redis depois de concluido. E o que
    #: permite a API responder "seu relatorio ficou pronto" sem tocar no banco.
    keep_result: ClassVar[int] = _config.arq_retencao_resultado_s

    #: Tentativas antes de a falha virar definitiva.
    max_tries: ClassVar[int] = _config.arq_max_tentativas

    #: `True`: excecao nao tratada devolve o job a fila com espera crescente ate
    #: `max_tries`. Tarefa que precise pedir retentativa explicita (terminal
    #: fora do ar, por exemplo) levanta `arq.worker.Retry(defer=...)`.
    retry_jobs: ClassVar[bool] = True

    #: Permite `Job.abort()` a partir da API — usado a partir da F11 para
    #: cancelar relatorio que o usuario desistiu de esperar.
    allow_abort_jobs: ClassVar[bool] = True

    health_check_key: ClassVar[str] = CHAVE_SAUDE_WORKER
    health_check_interval: ClassVar[int] = INTERVALO_SAUDE_S

    #: Sem `timezone` explicito de proposito: o ARQ passa a usar o relogio local
    #: do processo, e o container fixa `TZ=America/Sao_Paulo` (compose) com
    #: tzdata instalado (Dockerfile). Fixar um `datetime.timezone` aqui seria
    #: deslocamento constante e erraria a virada do horario de verao.


__all__ = [
    "CHAVE_SAUDE_WORKER",
    "INTERVALO_SAUDE_S",
    "WorkerSettings",
    "ao_encerrar",
    "ao_encerrar_job",
    "ao_iniciar",
    "ao_iniciar_job",
    "montar_funcoes",
    "montar_redis",
]
