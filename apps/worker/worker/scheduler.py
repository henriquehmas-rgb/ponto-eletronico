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
from zoneinfo import ZoneInfo

from arq.connections import RedisSettings
from arq.cron import CronJob, cron

from worker.banco_horas_vencimento import (
    abrir_ocorrencia_banco_vencendo,
    dias_ate_o_vencimento,
    listar_contas_abertas_cross_tenant,
    obter_politica_vencimento,
    publicar_banco_horas_vencendo,
)
from worker.config import Configuracao, obter_configuracao
from worker.filas import CODIGO_NAO_IMPLEMENTADO, FILA_MANUTENCAO, FILA_PADRAO
from worker.log import configurar_log, obter_logger

# `montar_redis` vem de `worker.main` para que os dois processos leiam a mesma
# `REDIS_URL` do mesmo jeito. O import traz junto o `WorkerSettings`, que e
# construido no import de `main` — sao apenas objetos em memoria, sem I/O e sem
# nada registrado: o scheduler continua sem conhecer as oito tarefas pesadas.
from worker.main import montar_redis
from worker.notificacoes_verificacao import verificar_notificacoes_pendentes_cross_tenant
from worker.relatorios_agendamentos_verificacao import (
    verificar_agendamentos_relatorio_cross_tenant,
)
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
#: `verificar_notificacoes_pendentes` (F10/A3) e' uma excecao deliberada ao
#: padrao restrito das duas rotinas acima: ela nao publica um evento de
#: `events.yaml` (nenhum evento do catalogo corresponde 1:1 a esta rotina --
#: PCF F10 §2.10), so grava `notificacoes` e aciona o escalonamento de A1
#: indiretamente (via lembrete de prazo vencido). `evento` fica vazio de
#: proposito -- `_resultado_rotina` ja trata ausencia com `meta.get("evento",
#: "")`, sem quebrar o andaime original.
ROTINAS: Final[dict[str, dict[str, str]]] = {
    "verificar_banco_horas_vencendo": {"fase": "F4", "evento": "banco_horas.vencendo"},
    "verificar_terminal_offline": {"fase": "F6", "evento": "terminal.offline"},
    "verificar_notificacoes_pendentes": {"fase": "F10", "evento": ""},
    "verificar_agendamentos_relatorio": {"fase": "F11", "evento": ""},
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
    """Projeta o vencimento das contas de banco de horas abertas (F4/T7/A2).

    Enumera contas `aberta` de TODOS os tenants via
    `fn_bh_contas_para_verificacao_vencimento()` (RFC-013, SECURITY
    DEFINER -- ver docstring de `worker/banco_horas_vencimento.py`), sem
    segunda credencial de banco. Para cada conta, compara a antecedencia em
    dias ate `periodo_fim` com `bh_politicas.dias_pre_aviso` (padrao
    ``{30,15,7}``, lida sob `app.tenant_id` publicado): quando a
    antecedencia bate EXATAMENTE um dos valores configurados, publica
    `banco_horas.vencendo` (uma vez por antecedencia e por conta -- o
    disparo e idempotente por construcao, ver docstring do modulo de
    suporte, nao precisa de marca de "ja avisado") e abre
    `ocorrencias.codigo='banco_vencendo'` (PCF secao 2: "banco_teto/
    banco_vencendo nascem nesta fase, A2").

    `minutosAVencer` e o saldo credor atual da conta (nunca negativo -- um
    saldo devedor nao "vence", so o credor): a projecao desta rotina e por
    CONTA (`periodo_fim`), nao por lancamento individual (essa granularidade
    fina, "quanto vence em 30/15/7 dias", ja existe em
    `obterSaldoBancoHoras`/`app.apuracao.banco_horas.consulta`).

    Roda de madrugada, depois da virada do dia e antes do expediente: o aviso
    precisa chegar ao gestor no comeco do dia util, e a projecao le muita linha.
    """
    config = obter_configuracao()
    # `hoje` precisa ser a data civil de `config.tz` (America/Sao_Paulo por
    # padrao, o mesmo fuso que o container fixa via TZ e que o restante do
    # sistema usa como referencia civil -- ADR-004), nunca UTC: como esta
    # rotina compara `periodo_fim - N dias == hoje` por igualdade exata
    # (nao por intervalo), usar UTC desalinha a comparacao em ate um dia
    # inteiro durante a janela em que UTC ja virou o dia mas o Brasil
    # (UTC-3) ainda nao -- bug real encontrado na reverificacao da F4
    # (achado: `assert 0 == 1` em `test_scheduler_publica_vencendo_
    # exatamente_nas_antecedencias_configuradas`, rodando as 21h de
    # Brasilia/01h UTC).
    hoje = dt.datetime.now(tz=ZoneInfo(config.tz)).date()
    contas = await listar_contas_abertas_cross_tenant(config)
    contas_verificadas = 0
    avisos_publicados = 0

    for conta in contas:
        contas_verificadas += 1
        restantes = dias_ate_o_vencimento(conta.periodo_fim, hoje)
        if restantes < 0:
            continue

        politica = await obter_politica_vencimento(config, conta.tenant_id, conta.bh_politica_id)
        if politica is None or restantes not in politica.dias_pre_aviso:
            continue

        minutos_a_vencer = max(conta.saldo_atual_minutos, 0)
        publicar_banco_horas_vencendo(
            tenant_id=conta.tenant_id,
            conta_id=conta.id,
            colaborador_id=conta.colaborador_id,
            vinculo_id=conta.vinculo_id,
            conta_codigo=conta.codigo,
            minutos_a_vencer=minutos_a_vencer,
            saldo_atual_minutos=conta.saldo_atual_minutos,
            vence_em=conta.periodo_fim,
            dias_restantes=restantes,
            acao_vencimento=politica.acao_vencimento,
        )
        await abrir_ocorrencia_banco_vencendo(
            config,
            tenant_id=conta.tenant_id,
            colaborador_id=conta.colaborador_id,
            vinculo_id=conta.vinculo_id,
            data=hoje,
            descricao=(
                f"Conta de banco de horas '{conta.codigo}' vence em "
                f"{conta.periodo_fim.isoformat()} ({restantes} dias), saldo atual de "
                f"{conta.saldo_atual_minutos} minutos."
            ),
            detalhes={
                "contaId": str(conta.id),
                "periodoFim": conta.periodo_fim.isoformat(),
                "diasRestantes": restantes,
                "saldoAtualMinutos": conta.saldo_atual_minutos,
            },
        )
        avisos_publicados += 1

    logger.info(
        "rotina verificar_banco_horas_vencendo concluida",
        extra={
            "jobId": ctx.get("job_id"),
            "evento": "banco_horas.vencendo",
            "contasVerificadas": contas_verificadas,
            "avisosPublicados": avisos_publicados,
        },
    )
    return {
        "implementado": True,
        "rotina": "verificar_banco_horas_vencendo",
        "contasVerificadas": contas_verificadas,
        "avisosPublicados": avisos_publicados,
        "executadoEm": dt.datetime.now(tz=dt.UTC).isoformat(),
    }


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

    A enumeracao cross-tenant usa `fn_terminais_para_verificacao_saude()`
    (RFC-013, SECURITY DEFINER) pela role comum `ponto_app`, sem segunda
    credencial de banco, porque este e um cron global, sem `tenant_id` de
    entrada — ver docstring de `worker/terminais_saude.py`.

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


async def verificar_notificacoes_pendentes(ctx: dict[Any, Any]) -> dict[str, Any]:
    """Varredura cross-tenant de sinais que nascem em domínios já
    concluídos e precisam virar notificação (F10/T11/A3).

    Dois achados por execução, os únicos citados pelo PCF §2.10:

    * ocorrências recentes com código em `{jornada_excedida, sem_marcacao,
      banco_vencendo}` (`ocorrencias`, gravadas por F4 durante a apuração)
      sem uma `Notificacao` correspondente ainda;
    * solicitações cuja etapa corrente está `pendente` com `prazo_em`
      vencido (`solicitacoes`/`aprovacoes`, gravadas por A1 desta mesma
      fase) sem o lembrete `solicitacao.pendente_prazo` ainda.

    A enumeração cross-tenant usa `fn_tenants_ativos()` (RFC-014, SECURITY
    DEFINER) pela role comum `ponto_app`, sem segunda credencial de banco --
    ver docstring de `worker/notificacoes_verificacao.py`. Cada achado
    materializa uma linha de `Notificacao` via `app.notificacao.motor.
    processar_evento` (reaproveitado, nunca duplicado).

    Ao final, enfileira `processar_fila_notificacoes` uma vez por tenant
    ATIVO (não só os que tiveram achado nesta execução: notificações
    nascidas em processo, pela chamada direta de A1/A2/A4 a `app.
    notificacao.motor.processar_evento` durante uma requisição HTTP, também
    esperam por este envio periódico -- ver docstring de
    `worker/tarefas/notificacoes.py`). `_queue_name=FILA_PADRAO` é
    EXPLÍCITO de propósito: `ctx["redis"]` aqui é o pool do SCHEDULER
    (`default_queue_name=FILA_MANUTENCAO`, a fila do próprio scheduler, ver
    `SchedulerSettings.queue_name`); sem o override, o job cairia numa fila
    que o `worker` (`queue_name=FILA_PADRAO`) nunca consome -- o mesmo "job
    órfão" que o achado real de `app/core/filas.py` (F9b/A3) já documentou
    para o lado da API, agora evitado aqui deliberadamente.

    Roda a cada 10 minutos (PCF §2.10): frequência alta o bastante para o
    lembrete de prazo vencido chegar no mesmo turno de trabalho, sem
    aproximar-se do custo de varrer `ocorrencias`/`solicitacoes` de todo
    tenant a cada poucos segundos.
    """
    resultado = await verificar_notificacoes_pendentes_cross_tenant()

    enfileiradas = 0
    redis = ctx.get("redis")
    if redis is not None:
        for tenant_id in resultado.tenant_ids:
            await redis.enqueue_job(
                "processar_fila_notificacoes",
                tenant_id=str(tenant_id),
                _queue_name=FILA_PADRAO,
            )
            enfileiradas += 1

    logger.info(
        "rotina verificar_notificacoes_pendentes concluida",
        extra={
            "jobId": ctx.get("job_id"),
            "tenantsVerificados": resultado.tenants_verificados,
            "ocorrenciasNotificadas": resultado.ocorrencias_notificadas,
            "pendenciasNotificadas": resultado.pendencias_notificadas,
            "drenagensEnfileiradas": enfileiradas,
        },
    )
    return {
        "implementado": True,
        "rotina": "verificar_notificacoes_pendentes",
        "tenantsVerificados": resultado.tenants_verificados,
        "ocorrenciasNotificadas": resultado.ocorrencias_notificadas,
        "pendenciasNotificadas": resultado.pendencias_notificadas,
        "drenagensEnfileiradas": enfileiradas,
        "executadoEm": dt.datetime.now(tz=dt.UTC).isoformat(),
    }


async def verificar_agendamentos_relatorio(ctx: dict[Any, Any]) -> dict[str, Any]:
    """Dispara relatórios agendados cuja `proxima_execucao_em` já venceu
    (F11, T11/A3).

    Para cada tenant `ativo` (`fn_tenants_ativos()`, RFC-014, mesmo padrão
    de `verificar_notificacoes_pendentes`), busca `relatorio_agendamentos`
    com `ativo=true AND proxima_execucao_em <= now()`
    (`worker.relatorios_agendamentos_verificacao`), cria a
    `RelatorioExecucao(status='enfileirado', agendamento_id=...)`
    correspondente e recalcula `proxima_execucao_em` via `croniter`
    (`app.relatorios.agendamentos.calcular_proxima_execucao`) -- tudo na
    mesma transação, o que torna a varredura idempotente por construção
    (ver docstring do módulo de suporte): uma linha disparada sai da janela
    `<= now()` antes da rotina seguinte rodar, então nunca duplica.

    Enfileira `executar_relatorio` no worker com `_queue_name=FILA_PADRAO`
    **explícito**: `ctx["redis"]` aqui é o pool do SCHEDULER
    (`default_queue_name=FILA_MANUTENCAO`), então sem o override o job
    cairia numa fila que o `worker` (`queue_name=FILA_PADRAO`) nunca
    consome -- o mesmo "job órfão" que `app/core/filas.py` (F9b/A3) e
    `verificar_notificacoes_pendentes` (acima) já documentam.

    Roda a cada 10 minutos, mesmo intervalo de `verificar_notificacoes_
    pendentes` (PCF §2.10 de F10): frequência alta o bastante para um
    agendamento diário/mensal disparar dentro da mesma janela de horário
    configurada, sem se aproximar do custo de varrer `relatorio_
    agendamentos` de todo tenant a cada poucos segundos.
    """
    redis = ctx.get("redis")

    async def _enfileirar(
        *,
        tenant_id: str,
        execucao_id: str,
        codigo: str,
        parametros: dict[str, Any],
        formato: str,
        solicitante_id: str | None,
    ) -> None:
        if redis is None:  # pragma: no cover - so em teste sem ctx["redis"]
            return
        await redis.enqueue_job(
            "executar_relatorio",
            tenant_id=tenant_id,
            execucao_id=execucao_id,
            codigo=codigo,
            parametros=parametros,
            formato=formato,
            solicitante_id=solicitante_id,
            _queue_name=FILA_PADRAO,
        )

    resultado = await verificar_agendamentos_relatorio_cross_tenant(enfileirar=_enfileirar)

    logger.info(
        "rotina verificar_agendamentos_relatorio concluida",
        extra={
            "jobId": ctx.get("job_id"),
            "tenantsVerificados": resultado.tenants_verificados,
            "agendamentosDisparados": resultado.agendamentos_disparados,
        },
    )
    return {
        "implementado": True,
        "rotina": "verificar_agendamentos_relatorio",
        "tenantsVerificados": resultado.tenants_verificados,
        "agendamentosDisparados": resultado.agendamentos_disparados,
        "executadoEm": dt.datetime.now(tz=dt.UTC).isoformat(),
    }


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
        # A cada 10 minutos (PCF F10 §2.10).
        cron(
            verificar_notificacoes_pendentes,
            name="verificar_notificacoes_pendentes",
            minute={0, 10, 20, 30, 40, 50},
            second=0,
            timeout=300,
            max_tries=1,
        ),
        # A cada 10 minutos (mesmo intervalo de verificar_notificacoes_
        # pendentes, PCF F11 §6/T11).
        cron(
            verificar_agendamentos_relatorio,
            name="verificar_agendamentos_relatorio",
            minute={0, 10, 20, 30, 40, 50},
            second=0,
            timeout=300,
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
    "verificar_agendamentos_relatorio",
    "verificar_banco_horas_vencendo",
    "verificar_notificacoes_pendentes",
    "verificar_terminal_offline",
]
