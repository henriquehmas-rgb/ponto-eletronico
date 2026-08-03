"""Rastreamento do processamento assincrono de `exportarFolha` (F13/A5,
T15, aplicando a parte da RFC-017 que cabe a este agente:
`obterExportacaoFolha`).

**Achado de contrato documentado, julgamento proprio deste agente -- nao
escondido, ver relatorio final da fase.** RFC-017 decide `obterExportacaoFolha`
reaproveitando o schema `ProcessamentoAssincrono` ("ja existente, ja
generico o bastante") e e explicita: "Nenhuma mudanca em schema.sql/
models/". Mas nenhuma tabela do dominio de folha guarda uma linha POR
EXECUCAO de exportacao: `integracoes_folha` e a CONFIGURACAO da integracao
(uma linha por integracao, nao por exportacao), e `ultima_exportacao_em` e
um unico timestamp escalar, nao um historico navegavel por id -- diferente
do padrao que a propria RFC manda replicar (`obterExecucaoRelatorio`,
respaldado por `relatorio_execucoes`, uma linha por execucao) e diferente
de `obterImportacao` (RFC-017/A8, respaldado por `importacoes`, que ja tem
todas as colunas). Sem tabela nova autorizada nesta fase (so A1 tem
migration, T3, exclusiva de `idempotencia_chaves`) e sem redecidir a RFC
por conta propria (proibido, PCF secao 2.1/9.2), a alternativa escolhida
foi: **`processamentoId` = job id do `arq`** (`_job_id` customizado,
suportado nativamente pela biblioteca desde sempre) e este modulo LE o
estado do processamento direto do Redis via `arq.jobs.Job`, sem gravar
nada em Postgres.

Infra ja provisionada para isto, sem mudanca nenhuma: `arq` ja guarda o
resultado de todo job no Redis por `keep_result` segundos
(`worker.config.Configuracao.arq_retencao_resultado_s = 86_400`, campo que
ja existia antes desta fase) -- 24h de retencao, mesmo horizonte de
`Idempotency-Key` (`PONTO-IDEM-001`). Depois disso o processamento
"expira" do ponto de vista deste endpoint, tratado como `PONTO-REC-002`
(mesmo codigo/semantica que `obterExecucaoRelatorio` usa para artefato
expirado) -- nao e um bug, e o design.

**Isolamento de tenant.** O Redis nao tem coluna `tenant_id`: um
`processamentoId` sozinho nao prova que pertence ao tenant/integracao da
requisicao. Este modulo NUNCA devolve dado de um job sem antes conferir
que os `kwargs` com que ele foi enfileirado (`tenant_id`/`integracao_id`,
que `servico.solicitar_exportacao` sempre passa) batem com o tenant/
integracao pedidos -- descasamento e tratado como "nao encontrado" (o
mesmo 404 de um id que nunca existiu; nunca vaza que o id pertence a outro
tenant).

Se o orquestrador preferir uma tabela dedicada no estilo `relatorio_
execucoes` no futuro, isso e mudanca aditiva sobre este modulo (troca a
fonte de leitura, mantem a assinatura de `obter_estado`), nunca reescrita
do resto do motor de folha.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from arq.jobs import Job, JobStatus
from redis.asyncio import Redis

from app.core.filas import FILA_PADRAO

#: `ProcessamentoAssincrono.tipo` fixo para este dominio.
TIPO: str = "exportacao_folha"

#: `PONTO-REC-002` -- mesmo codigo usado por `obterExecucaoRelatorio` para
#: artefato/processamento expirado (ver docstring do modulo).
CODIGO_EXPIRADO: str = "PONTO-REC-002"


@dataclass(frozen=True, slots=True)
class EstadoProcessamentoFolha:
    """Espelha os campos de `ProcessamentoAssincrono` (openapi.yaml) que
    este dominio consegue preencher a partir do job do `arq`."""

    id: UUID
    status: str
    progresso: int | None
    total_itens: int | None
    itens_processados: int | None
    resultado_ref: str | None
    iniciado_em: dt.datetime | None
    concluido_em: dt.datetime | None
    erro: str | None
    codigo_erro: str | None


async def obter_estado(
    redis: Redis,
    *,
    processamento_id: UUID,
    tenant_id: UUID,
    integracao_id: UUID,
) -> EstadoProcessamentoFolha | None:
    """Le o estado do processamento no Redis (via `arq.jobs.Job`). Devolve
    `None` quando o job nunca existiu, ja expirou (`keep_result` decorrido)
    OU pertence a outro tenant/integracao (isolamento -- ver docstring do
    modulo). O chamador (router) traduz `None` para `PONTO-REC-001`
    (nao encontrado) por padrao; so quando o chamador ja sabe, por outra
    via, que o id EXISTIU (por exemplo guardou o instante de criacao),
    `None` pode ser reinterpretado como `PONTO-REC-002` (expirado) -- este
    modulo nao tem como distinguir os dois casos sozinho, porque o Redis
    simplesmente nao tem mais nenhum registro do job vencido."""
    job = Job(str(processamento_id), redis, _queue_name=FILA_PADRAO)
    status = await job.status()
    if status == JobStatus.not_found:
        return None

    info = await job.info()
    if info is None:
        return None
    kwargs = info.kwargs or {}
    if str(kwargs.get("tenant_id")) != str(tenant_id) or str(kwargs.get("integracao_id")) != str(
        integracao_id
    ):
        # Isolamento de tenant: nunca confirma nem nega a existencia do job
        # de outro tenant/integracao. Ver docstring do modulo.
        return None

    if status in (JobStatus.deferred, JobStatus.queued):
        return EstadoProcessamentoFolha(
            id=processamento_id,
            status="enfileirado",
            progresso=0,
            total_itens=None,
            itens_processados=None,
            resultado_ref=None,
            iniciado_em=None,
            concluido_em=None,
            erro=None,
            codigo_erro=None,
        )
    if status == JobStatus.in_progress:
        return EstadoProcessamentoFolha(
            id=processamento_id,
            status="processando",
            progresso=None,
            total_itens=None,
            itens_processados=None,
            resultado_ref=None,
            iniciado_em=None,
            concluido_em=None,
            erro=None,
            codigo_erro=None,
        )

    # status == JobStatus.complete
    resultado = await job.result_info()
    if resultado is None:
        # Corrida rara entre `status()` reportar `complete` e o resultado
        # ainda nao ter sido lido nesta mesma leitura -- trata como
        # "processando" em vez de expor uma inconsistencia transiente ao
        # cliente, que vai poll novamente.
        return EstadoProcessamentoFolha(
            id=processamento_id,
            status="processando",
            progresso=None,
            total_itens=None,
            itens_processados=None,
            resultado_ref=None,
            iniciado_em=None,
            concluido_em=None,
            erro=None,
            codigo_erro=None,
        )

    if resultado.success:
        payload: dict[str, Any] = resultado.result or {}
        return EstadoProcessamentoFolha(
            id=processamento_id,
            status="concluido",
            progresso=100,
            total_itens=payload.get("totalLinhas"),
            itens_processados=payload.get("totalLinhas"),
            resultado_ref=payload.get("resultadoRef"),
            iniciado_em=resultado.start_time,
            concluido_em=resultado.finish_time,
            erro=None,
            codigo_erro=None,
        )

    erro_bruto = resultado.result
    return EstadoProcessamentoFolha(
        id=processamento_id,
        status="falhou",
        progresso=None,
        total_itens=None,
        itens_processados=None,
        resultado_ref=None,
        iniciado_em=resultado.start_time,
        concluido_em=resultado.finish_time,
        erro=str(erro_bruto) if erro_bruto is not None else "Falha nao especificada.",
        codigo_erro=getattr(erro_bruto, "codigo", None),
    )
