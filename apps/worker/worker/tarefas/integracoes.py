"""Entrega de webhooks e sincronizacao de terminais.

**`enviar_webhook`** (F13/A3, T12): entrega uma tentativa do evento ao
endpoint do cliente, assinado HMAC-SHA256 (`X-Ponto-Signature`, formato
`t=<epoch>,v1=<hex>` de `events.yaml`). Sucesso = 2xx -> `status='sucesso'`,
zera `webhooks.falhas_consecutivas`. Falha: agenda a proxima tentativa com
recuo exponencial (`_BACKOFF_SEGUNDOS`) ate `webhooks.max_tentativas`;
esgotado, `status='dlq'`, incrementa `falhas_consecutivas` e, acima de
`_LIMITE_FALHAS_CONSECUTIVAS_DESABILITA`, desabilita o webhook e publica
`webhook.desabilitado` (`app.integracoes.webhooks.eventos`, primeiro
produtor real deste evento). Quem enfileira cada tentativa: o commit de
T11 (fan-out, `app.integracoes.webhooks.fan_out`) grava a linha `pendente`
em `webhook_entregas`; a rotina de cron `worker.scheduler.
despachar_webhooks_pendentes` (T11/T12, a cada minuto) varre e enfileira
esta tarefa -- ver `worker.despacho_webhooks` para o desenho completo.

`sincronizar_terminal`: F6/A2, implementada nesta tarefa (T7 do PCF).

**`sincronizar_terminal`** empurra cadastro (hoje: usuarios; ver `_ESCOPO`
abaixo para os demais) para um coletor Control iD. Vive na mesma fila de
integracoes porque as duas tarefas sao curtas e falam com rede de terceiro --
e ficam longe da fila de apuracao, que e longa e nao pode ser atrasada por um
endpoint remoto lento.

**Esta tarefa NAO fala com o terminal diretamente.** Ela monta os comandos no
vocabulario do fabricante (`gateway.provisionamento.comandos`, T7/T8 do PCF)
e entrega ao `device-gw` via `POST /interno/terminais/{numeroSerie}/comandos`
(`gateway/rotas/push.py::enfileirar_comando`, A1/T4), que enfileira para o
proximo ciclo de Push -- o worker nunca abre sessao `login.fcgi` nem fala
`*.fcgi` por conta propria (isso e o `cliente_controlid.py` de dentro do
`device-gw`, usado por A1 no catch-up). `202`/`409 PONTO-TERM-004` (terminal
mudo, comando enfileirado do mesmo jeito) contam como entrega bem-sucedida
desta tarefa; qualquer outra resposta conta como falha, registrada no
resultado sem abortar o restante do lote.

**`importar_arquivo_generico`** (F13/A8, T19): dispatcher de importação
genérica -- `POST /v1/importacoes` (RFC-017, `app.integracoes.importadores.
servico`) enfileira esta tarefa para todo `tipo` que não tem pipeline
próprio (`colaboradores` continua indo direto para `importar_colaboradores`,
F2, sem passar por aqui -- ver aquele módulo). Hoje só `tipo='afd_terceiro'`
tem processamento real (`app.integracoes.importadores.afd_terceiro.servico`,
instalado no venv do worker como biblioteca, ADR-009 -- mesmo padrão que
`worker/tarefas/relatorios.py` já usa para `app.comum.armazenamento`); os
demais seis tipos do enum (`estrutura`/`escalas`/`feriados`/`marcacoes`/
`banco_horas`/`biometria`) marcam a importação como `falhou` com mensagem
clara de "tipo ainda não suportado", nunca travando a fila nem fingindo
sucesso -- fora do escopo de T19 (ver docstring de `app.integracoes.
importadores.servico`).

**`exportar_folha`** (F13/A5, T15): corpo real de `POST /v1/integracoes/
folha/{integracaoId}/exportar` (`app.integracoes.folha.comum.servico.
solicitar_exportacao` enfileira esta tarefa com `_job_id` igual ao
`processamentoId` devolvido ao cliente -- ver `app.integracoes.folha.
comum.processamento` para o porquê). Import tardio de `app.integracoes.
folha.comum.execucao.executar_exportacao_folha` (mesmo padrão de `app.
fiscal.afd.gerador.gerar_afd_arquivo` chamado por `worker/tarefas/
fiscal.py::gerar_afd` -- `apps/worker` instala `apps/api` como biblioteca
na imagem `runtime`, ADR-009): consulta a apuração fechada, gera o arquivo
do parceiro configurado e grava no armazenamento de objetos. O resultado
do job (`{"totalLinhas": int, "resultadoRef": str}`) é o que `arq` guarda
no Redis e que `obterExportacaoFolha` lê de volta.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import json
import time
import zlib
from typing import Any
from uuid import UUID, uuid4

import httpx
import sqlalchemy as sa
from ponto_contracts import Colaborador, Importacao, Tenant, Terminal, Webhook, WebhookEntrega
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from worker.config import obter_configuracao
from worker.log import obter_logger
from worker.tarefas.importacoes import construir_envelope_evento, publicar_evento

logger = obter_logger("tarefas.integracoes")

__all__ = [
    "ErroEntregaComando",
    "enviar_webhook",
    "exportar_folha",
    "importar_arquivo_generico",
    "reiniciar_engine_para_testes",
    "sincronizar_terminal",
    "user_id_do_terminal",
]

# =============================================================================
# `user_id_do_terminal` -- COPIA deliberada de
# `apps/device-gw/gateway/provisionamento/comandos.py::user_id_do_terminal`.
# O worker nao pode importar `gateway` em producao (imagens Docker
# separadas -- mesma razao de `worker/tarefas/importacoes.py` duplicar os
# validadores de CPF/PIS da API, ver docstring daquele modulo); mesmo
# algoritmo, mesma fonte. Se o algoritmo mudar, muda nos dois lugares --
# registrado em `docs/backlog.md`.
# =============================================================================


def user_id_do_terminal(matricula: str) -> int:
    """`users.id` deterministico para esta matricula, estavel entre
    sincronizacoes (o mesmo colaborador sempre cai no mesmo `id`)."""
    return zlib.crc32(matricula.encode("utf-8")) + 1


def _montar_comando_criar_usuario(*, user_id: int, matricula: str, nome: str) -> dict[str, Any]:
    return {
        "verb": "POST",
        "endpoint": "create_objects.fcgi",
        "contentType": "application/json",
        "queryString": "",
        "body": {
            "object": "users",
            "values": [{"id": user_id, "registration": matricula, "name": nome}],
        },
    }


# =============================================================================
# Sessao de banco (lazy, self-contained -- mesmo padrao de
# `worker/tarefas/importacoes.py`, duplicado de proposito: os dois modulos
# tem ciclo de vida de engine independente, e a razao de fundo e a mesma —
# `apps/worker` nao importa `apps/api/app/db/sessao.py`, pacotes/imagens
# Docker separadas.)
# =============================================================================

_engine: AsyncEngine | None = None
_fabrica: async_sessionmaker[AsyncSession] | None = None


def _fabrica_de_sessoes() -> async_sessionmaker[AsyncSession]:
    global _engine, _fabrica
    if _fabrica is None:
        config = obter_configuracao()
        _engine = create_async_engine(config.database_url, pool_pre_ping=True)
        _fabrica = async_sessionmaker(_engine, expire_on_commit=False, autoflush=False)
    return _fabrica


async def reiniciar_engine_para_testes() -> None:
    """SOMENTE para teste: descarta a engine cacheada para que a proxima
    chamada crie uma nova, presa ao event loop corrente (mesma razao de
    `worker/tarefas/importacoes.py::reiniciar_engine_para_testes`)."""
    global _engine, _fabrica
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _fabrica = None


async def _aplicar_tenant(sessao: AsyncSession, tenant_id: str) -> None:
    """`SET LOCAL app.tenant_id` -- ADR-001 consequencia (a): o worker nao
    tem requisicao HTTP e precisa publicar o tenant explicitamente em cada
    job."""
    await sessao.execute(
        text("SELECT set_config('app.tenant_id', :tenant, true)"), {"tenant": tenant_id}
    )


def _agora() -> dt.datetime:
    return dt.datetime.now(tz=dt.UTC)


# =============================================================================
# Entrega ao device-gw
# =============================================================================


class ErroEntregaComando(RuntimeError):
    """Falha ao entregar um comando ao `device-gw` (rede, HTTP >= 500 ou
    formato de resposta inesperado). **Nao** cobre `409 PONTO-TERM-004`
    ("terminal mudo, comando enfileirado do mesmo jeito"): isso e sucesso do
    ponto de vista desta tarefa -- o comando entra na fila e sai no proximo
    contato do equipamento, exatamente como o modo Push preve."""


async def _entregar_comando(
    cliente_http: httpx.AsyncClient,
    *,
    base_url: str,
    numero_serie: str,
    comando: dict[str, Any],
) -> None:
    url = f"{base_url}/interno/terminais/{numero_serie}/comandos"
    try:
        resposta = await cliente_http.post(url, json=comando)
    except httpx.HTTPError as exc:
        raise ErroEntregaComando(f"device-gw inacessivel para {numero_serie}: {exc}") from exc
    if resposta.status_code in (202, 409):
        return
    raise ErroEntregaComando(
        f"device-gw respondeu {resposta.status_code} ao entregar comando para {numero_serie}."
    )


# =============================================================================
# Escopo da sincronizacao
# =============================================================================

#: `completo` cobre as cinco categorias; os demais valores restringem a uma
#: so. Mapeamento identico ao que `apps/api/app/terminais/servico.py`
#: (A1, T3) produz a partir de `SincronizacaoTerminalRequisicao` -- ver
#: `_escopo_de` la.
_CATEGORIAS_POR_ESCOPO: dict[str, frozenset[str]] = {
    "completo": frozenset({"usuarios", "templates", "grupos", "regras", "horarios"}),
    "usuarios": frozenset({"usuarios"}),
    "templates": frozenset({"templates"}),
    "grupos": frozenset({"grupos"}),
    "regras": frozenset({"regras"}),
    "horarios": frozenset({"horarios"}),
}

#: Categorias sem fonte de dado alcancavel nesta fase (ver docstring de cada
#: bloco em `sincronizar_terminal`) -- registradas no resultado como
#: "nao implementado", nunca silenciosamente ignoradas.
_MOTIVO_TEMPLATES = (
    "Sem fonte de foto crua disponivel nesta fase: colaboradores.foto_ref aponta para um "
    "armazenamento de objetos que nenhuma fase ainda integrou de verdade (mesma lacuna "
    "documentada em worker/tarefas/importacoes.py para conteudo_ref; ver docs/backlog.md)."
)
_MOTIVO_GRUPOS_REGRAS_HORARIOS = (
    "Grupos/regras de acesso/faixas de horario dependem do modelo de jornada e escala "
    "(tags jornadas/escalas), que sao da F3 e estao fora do escopo desta fase (PCF F6 secao 4, "
    "'Nao toca'). Registrado em docs/backlog.md para a fase que fechar esse mapeamento."
)


#: Recuo exponencial com jitter (`packages/contracts/events.yaml`, secao
#: `entrega.backoff`): "10s, 30s, 2min, 10min, 30min, 2h, 6h, 12h" -- 8
#: valores, o mesmo tamanho de `entrega.max_tentativas_padrao`. Indexado por
#: `tentativa - 1` (a tentativa que ACABOU de falhar): tentativa 1 falhou ->
#: espera 10s antes da tentativa 2; tentativa 7 falhou -> espera 6h antes da
#: tentativa 8. Para um webhook configurado com `max_tentativas` MAIOR que 8
#: (a coluna aceita qualquer inteiro positivo, o contrato nao limita o teto),
#: as tentativas alem da oitava reusam o ultimo valor (12h) -- decisao de A3,
#: documentada aqui por nao haver um nono valor no catalogo.
_BACKOFF_SEGUNDOS: tuple[int, ...] = (10, 30, 120, 600, 1800, 7200, 21600, 43200)

#: Falhas consecutivas (entregas que esgotaram `max_tentativas` e foram para
#: `dlq`, sem nenhuma entrega bem-sucedida entre elas) acima deste limite
#: desabilitam o webhook automaticamente (`status='desabilitado_por_falha'`,
#: `events.yaml`: "Falhas consecutivas acima do limite do webhook...").
#: **Achado de contrato, documentado no relatorio da fase**: nem
#: `packages/contracts/schema.sql` nem `openapi.yaml` modelam esse limite
#: como coluna/campo configuravel por webhook (so `max_tentativas`, que e
#: por ENTREGA, existe) -- este e um valor de aplicacao, fixo, escolhido por
#: A3 na ausencia de um campo de contrato para isso. Não decidido como RFC
#: (não é lacuna de superfície de contrato, é um parâmetro interno de
#: comportamento) -- se o produto quiser tornar isto configuravel por
#: tenant/webhook no futuro, é trabalho de RFC sobre `schema.sql`.
_LIMITE_FALHAS_CONSECUTIVAS_DESABILITA = 10


def _resposta_truncada(resposta: httpx.Response) -> str:
    try:
        texto = resposta.text
    except Exception:  # pragma: no cover - corpo nao decodificavel como texto
        return f"<corpo binario, {len(resposta.content)} bytes>"
    return texto[:2000]


async def enviar_webhook(
    ctx: dict[str, Any],
    *,
    tenant_id: str,
    entrega_id: str,
    webhook_id: str,
    evento: str,
    tentativa: int = 1,
    cliente_http: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Entrega uma vez o evento ao endpoint do cliente, assinado com HMAC.

    Args:
        ctx: contexto do ARQ.
        tenant_id: tenant dono do dado.
        entrega_id: registro em `webhook_entregas`, que acumula o historico.
        webhook_id: assinatura do cliente (endpoint, segredo e eventos).
        evento: nome do evento no catalogo, por exemplo `marcacao.criada`.
        tentativa: numero da tentativa, base do recuo exponencial.
        cliente_http: **somente para teste** -- injeta um `httpx.AsyncClient`
            (por exemplo com `transport=httpx.MockTransport(...)`), mesmo
            padrao de `sincronizar_terminal` acima. Em producao, `None` cria
            um cliente novo por chamada, com o timeout do proprio webhook.
    """
    logger.info(
        "enviar_webhook recebida",
        extra={
            "jobId": ctx.get("job_id"),
            "tenantId": tenant_id,
            "entregaId": entrega_id,
            "webhookId": webhook_id,
            "evento": evento,
            "tentativa": tentativa,
        },
    )
    tenant_uuid = UUID(tenant_id)
    entrega_uuid = UUID(entrega_id)
    webhook_uuid = UUID(webhook_id)
    fabrica = _fabrica_de_sessoes()

    async with fabrica() as sessao:
        await _aplicar_tenant(sessao, tenant_id)

        webhook = (
            await sessao.execute(
                sa.select(Webhook).where(
                    Webhook.id == webhook_uuid,
                    Webhook.tenant_id == tenant_uuid,
                    Webhook.excluido_em.is_(None),
                )
            )
        ).scalar_one_or_none()
        entrega = (
            await sessao.execute(
                sa.select(WebhookEntrega).where(
                    WebhookEntrega.id == entrega_uuid, WebhookEntrega.tenant_id == tenant_uuid
                )
            )
        ).scalar_one_or_none()

        if webhook is None or entrega is None:
            logger.warning(
                "enviar_webhook: webhook ou entrega nao encontrados",
                extra={"webhookId": webhook_id, "entregaId": entrega_id},
            )
            return {
                "implementado": True,
                "encontrado": False,
                "webhookId": webhook_id,
                "entregaId": entrega_id,
            }
        if entrega.status == "cancelada":
            # `excluirWebhook` cancela entregas pendentes (T10) -- job que
            # ja estava na fila quando isso aconteceu nao deve reenviar.
            return {"implementado": True, "enviado": False, "motivo": "entrega cancelada"}

        # Import tardio: `app.integracoes.webhooks.cifra`/`eventos` sao de A3
        # dentro de `apps/api`, instalado como biblioteca no worker (ADR-009,
        # mesmo padrao de `app.fiscal.afd.gerador` em `worker/tarefas/
        # fiscal.py::gerar_afd`). `# type: ignore[import-not-found]`: mypy
        # nao resolve `app.integracoes` como pacote regular porque o
        # diretorio nao tem `__init__.py` proprio ainda (namespace package
        # PEP 420 -- "unico criador" e A1, PCF F13 secao 5.2); em runtime
        # Python resolve normalmente (ja provado pelos testes desta fase).
        from app.integracoes.webhooks.cifra import (  # type: ignore[import-not-found]
            decifrar_segredo,
        )

        segredo = decifrar_segredo(webhook.segredo_hmac_cifrado)

        # Corpo assinado e enviado: a serializacao CANONICA do payload ja
        # gravado em `webhook_entregas.payload` (jsonb) -- nao existe um
        # "corpo bruto original" a preservar aqui (diferente de um RECEPTOR
        # de webhook verificando uma requisicao de terceiro): este processo
        # e o EMISSOR, entao a serializacao que assinamos e a mesma que
        # enviamos, byte a byte, o que e o requisito real de
        # `events.yaml` ("assine o corpo BRUTO, antes de qualquer parse").
        corpo_bruto = json.dumps(entrega.payload, ensure_ascii=False, separators=(",", ":")).encode(
            "utf-8"
        )
        epoch = int(time.time())
        base_assinada = f"{epoch}.".encode("ascii") + corpo_bruto
        assinatura_hex = hmac.new(
            segredo.encode("utf-8"), base_assinada, hashlib.sha256
        ).hexdigest()
        cabecalho_assinatura = f"t={epoch},v1={assinatura_hex}"

        tenant_slug = (
            await sessao.execute(sa.select(Tenant.slug).where(Tenant.id == tenant_uuid))
        ).scalar_one_or_none() or ""

        cabecalhos: dict[str, str] = {
            "Content-Type": "application/json",
            "X-Ponto-Signature": cabecalho_assinatura,
            "X-Ponto-Event": evento,
            "X-Ponto-Event-Id": str(entrega.evento_id),
            "X-Ponto-Delivery-Id": str(uuid4()),
            "X-Ponto-Tenant": tenant_slug,
        }
        if webhook.cabecalhos_extras:
            for chave, valor in webhook.cabecalhos_extras.items():
                cabecalhos[str(chave)] = str(valor)

        entrega.status = "enviando"
        entrega.assinatura = cabecalho_assinatura
        await sessao.commit()
        # `SET LOCAL app.tenant_id` vale so para a transacao que o commit
        # acima encerrou -- a proxima instrucao nesta MESMA sessao comeca
        # uma transacao nova, sem RLS liberado, entao reaplica antes de
        # continuar escrevendo em `webhook`/`entrega` (achado real desta
        # fase: sem isto, o UPDATE final falha silenciosamente por RLS --
        # nao um erro de permissao claro, e sim `StaleDataError`/"0 rows
        # matched", porque a policy filtra a linha antes do UPDATE achar
        # ela).
        await _aplicar_tenant(sessao, tenant_id)

        http_status: int | None = None
        resposta_trecho: str | None = None
        erro_texto: str | None = None
        inicio = time.monotonic()
        fechar_cliente = cliente_http is None
        http = cliente_http or httpx.AsyncClient(timeout=webhook.timeout_segundos)
        try:
            try:
                resposta = await http.post(webhook.url, content=corpo_bruto, headers=cabecalhos)
                http_status = resposta.status_code
                resposta_trecho = _resposta_truncada(resposta)
                sucesso = 200 <= resposta.status_code < 300
            except httpx.HTTPError as exc:
                erro_texto = f"{type(exc).__name__}: {exc}"
                sucesso = False
        finally:
            if fechar_cliente:
                await http.aclose()
        duracao_ms = int((time.monotonic() - inicio) * 1000)

        entrega.duracao_ms = duracao_ms
        entrega.http_status = http_status
        entrega.resposta = resposta_trecho
        entrega.erro = erro_texto
        entrega.enviado_em = _agora()

        resultado: dict[str, Any] = {
            "implementado": True,
            "enviado": True,
            "sucesso": sucesso,
            "httpStatus": http_status,
            "tentativa": tentativa,
        }

        if sucesso:
            entrega.status = "sucesso"
            webhook.ultima_entrega_em = entrega.enviado_em
            webhook.falhas_consecutivas = 0
        else:
            resultado["erro"] = erro_texto
            proxima_tentativa = tentativa + 1
            if proxima_tentativa <= webhook.max_tentativas:
                indice_backoff = min(tentativa - 1, len(_BACKOFF_SEGUNDOS) - 1)
                atraso_s = _BACKOFF_SEGUNDOS[max(indice_backoff, 0)]
                entrega.status = "falha"
                entrega.tentativa = proxima_tentativa
                entrega.proxima_tentativa_em = _agora() + dt.timedelta(seconds=atraso_s)
                resultado["proximaTentativaEm"] = entrega.proxima_tentativa_em.isoformat()
            else:
                # Tentativas esgotadas (`entrega.tentativa` continua na
                # ultima usada -- `proxima_tentativa_em` fica `None`: nada
                # mais varre esta linha ate um reenvio manual, T13).
                entrega.status = "dlq"
                entrega.proxima_tentativa_em = None
                webhook.falhas_consecutivas += 1
                resultado["dlq"] = True

                if (
                    webhook.falhas_consecutivas > _LIMITE_FALHAS_CONSECUTIVAS_DESABILITA
                    and webhook.status == "ativo"
                ):
                    webhook.status = "desabilitado_por_falha"
                    total_dlq = (
                        await sessao.execute(
                            sa.select(sa.func.count())
                            .select_from(WebhookEntrega)
                            .where(
                                WebhookEntrega.tenant_id == tenant_uuid,
                                WebhookEntrega.webhook_id == webhook_uuid,
                                WebhookEntrega.status == "dlq",
                            )
                        )
                    ).scalar_one()
                    # Import tardio, mesmo motivo do `decifrar_segredo` acima.
                    from app.integracoes.webhooks.eventos import (  # type: ignore[import-not-found]
                        publicar_webhook_desabilitado,
                    )

                    publicar_webhook_desabilitado(
                        tenant_id=tenant_uuid,
                        webhook_id=webhook_uuid,
                        nome=webhook.nome,
                        falhas_consecutivas=webhook.falhas_consecutivas,
                        ultimo_erro=erro_texto,
                        entregas_na_dlq=int(total_dlq) + 1,
                    )
                    resultado["desabilitadoPorFalha"] = True

        await sessao.commit()

    logger.info(
        "enviar_webhook concluida",
        extra={
            "jobId": ctx.get("job_id"),
            "entregaId": entrega_id,
            "webhookId": webhook_id,
            "sucesso": resultado.get("sucesso"),
            "status": entrega.status,
        },
    )
    return resultado


async def sincronizar_terminal(
    ctx: dict[str, Any],
    *,
    tenant_id: str,
    terminal_id: str,
    escopo: str = "completo",
    solicitante_id: str | None = None,
    cliente_http: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Sincroniza cadastro e biometria com um coletor Control iD.

    Args:
        ctx: contexto do ARQ.
        tenant_id: tenant dono do dado.
        terminal_id: terminal de destino.
        escopo: `completo` ou o subconjunto a propagar (`usuarios`,
            `templates`, `grupos`, `regras`, `horarios`).
        solicitante_id: quem pediu, para a trilha de auditoria.
        cliente_http: **somente para teste** -- injeta um `httpx.AsyncClient`
            (por exemplo, com `transport=httpx.MockTransport(...)`) para nao
            depender de um `device-gw` real escutando porta nenhuma. Em
            producao, `None` cria um cliente novo, descartado ao final.
    """
    logger.info(
        "sincronizar_terminal recebida",
        extra={
            "jobId": ctx.get("job_id"),
            "tenantId": tenant_id,
            "terminalId": terminal_id,
            "escopo": escopo,
        },
    )
    tenant_uuid = UUID(tenant_id)
    terminal_uuid = UUID(terminal_id)
    config = obter_configuracao()
    fabrica = _fabrica_de_sessoes()

    async with fabrica() as sessao:
        await _aplicar_tenant(sessao, tenant_id)
        terminal = (
            await sessao.execute(
                sa.select(Terminal).where(
                    Terminal.id == terminal_uuid,
                    Terminal.tenant_id == tenant_uuid,
                    Terminal.excluido_em.is_(None),
                )
            )
        ).scalar_one_or_none()
        if terminal is None:
            logger.warning(
                "terminal nao encontrado para sincronizacao",
                extra={"terminalId": terminal_id, "tenantId": tenant_id},
            )
            return {
                "implementado": True,
                "encontrado": False,
                "terminalId": terminal_id,
                "escopo": escopo,
            }

        categorias = _CATEGORIAS_POR_ESCOPO.get(escopo)
        if categorias is None:
            logger.warning("escopo de sincronizacao desconhecido", extra={"escopo": escopo})
            return {
                "implementado": True,
                "encontrado": True,
                "terminalId": terminal_id,
                "escopo": escopo,
                "erro": f"escopo desconhecido: {escopo!r}",
            }

        resultado_usuarios: dict[str, Any] | None = None
        if "usuarios" in categorias:
            linhas = (
                await sessao.execute(
                    sa.select(Colaborador.matricula, Colaborador.nome_completo).where(
                        Colaborador.tenant_id == tenant_uuid,
                        Colaborador.empresa_id == terminal.empresa_id,
                        Colaborador.excluido_em.is_(None),
                        Colaborador.status == "ativo",
                    )
                )
            ).all()

            fechar_cliente = cliente_http is None
            http = cliente_http or httpx.AsyncClient(timeout=config.device_gw_timeout_s)
            enviados = 0
            falhas = 0
            try:
                for matricula, nome in linhas:
                    comando = _montar_comando_criar_usuario(
                        user_id=user_id_do_terminal(matricula), matricula=matricula, nome=nome
                    )
                    try:
                        await _entregar_comando(
                            http,
                            base_url=config.device_gw_base_url,
                            numero_serie=terminal.numero_serie,
                            comando=comando,
                        )
                        enviados += 1
                    except ErroEntregaComando as exc:
                        falhas += 1
                        logger.warning(
                            "falha ao entregar comando de usuario ao device-gw",
                            extra={
                                "terminalId": terminal_id,
                                "matricula": matricula,
                                "erro": str(exc),
                            },
                        )
            finally:
                if fechar_cliente:
                    await http.aclose()
            resultado_usuarios = {"total": len(linhas), "enviados": enviados, "falhas": falhas}

        def _nao_implementado(categoria: str, motivo: str) -> dict[str, Any] | None:
            if categoria not in categorias:
                return None
            return {"enviados": 0, "motivo": motivo}

        resultado_templates = _nao_implementado("templates", _MOTIVO_TEMPLATES)
        resultado_grupos = _nao_implementado("grupos", _MOTIVO_GRUPOS_REGRAS_HORARIOS)
        resultado_regras = _nao_implementado("regras", _MOTIVO_GRUPOS_REGRAS_HORARIOS)
        resultado_horarios = _nao_implementado("horarios", _MOTIVO_GRUPOS_REGRAS_HORARIOS)

        terminal.ultima_sincronizacao_em = _agora()
        await sessao.commit()

    logger.info(
        "sincronizar_terminal concluida",
        extra={
            "terminalId": terminal_id,
            "escopo": escopo,
            "usuarios": resultado_usuarios,
        },
    )
    return {
        "implementado": True,
        "encontrado": True,
        "terminalId": terminal_id,
        "escopo": escopo,
        "usuarios": resultado_usuarios,
        "templates": resultado_templates,
        "grupos": resultado_grupos,
        "regras": resultado_regras,
        "horarios": resultado_horarios,
        "solicitanteId": solicitante_id,
    }


# =============================================================================
# `exportar_folha` -- F13/A5, T15. Ver docstring do modulo.
# =============================================================================


async def exportar_folha(
    ctx: dict[str, Any],
    *,
    tenant_id: str,
    integracao_id: str,
    empresa_id: str,
    parceiro: str,
    competencia_folha: str,
    periodo_id: str | None = None,
    unidade_id: str | None = None,
    somente_fechados: bool = True,
) -> dict[str, Any]:
    """Gera o arquivo de exportacao de folha do parceiro configurado e
    grava no armazenamento de objetos.

    Args:
        ctx: contexto do ARQ. `_job_id` (fixado pelo enfileirador em
            `app.integracoes.folha.comum.servico.solicitar_exportacao`) e
            o `processamentoId` que o cliente recebeu em `exportarFolha` e
            usa para consultar `obterExportacaoFolha` depois.
        tenant_id: tenant dono da integracao.
        integracao_id: linha de `integracoes_folha` configurada.
        empresa_id: empresa cuja apuracao sera exportada.
        parceiro: valor do enum `IntegracaoFolha.parceiro` -- resolve o
            exportador registrado em `app.integracoes.folha.comum.registro`.
        competencia_folha: `AAAA-MM`, usada quando `periodo_id` esta ausente
            (ou so para nomear o arquivo, quando `periodo_id` esta presente).
        periodo_id: periodo interno a exportar, quando informado no pedido.
        unidade_id: restringe a exportacao a uma unidade.
        somente_fechados: exporta so dias com `apuracoes_dia.status =
            'fechado'` (recomendado -- default `True`).

    Devolve `{"totalLinhas": int, "resultadoRef": str}` -- `resultadoRef` e
    a CHAVE do objeto no armazenamento (nunca a URL: a URL assinada e
    resolvida sob demanda por `obterExportacaoFolha`, mesmo padrao de
    `app.comum.armazenamento`).
    """
    logger.info(
        "exportar_folha recebida",
        extra={
            "jobId": ctx.get("job_id"),
            "tenantId": tenant_id,
            "integracaoId": integracao_id,
            "parceiro": parceiro,
            "competenciaFolha": competencia_folha,
        },
    )

    # Import tardio: `apps/worker` so instala `apps/api` como biblioteca na
    # imagem `runtime` (ADR-009) -- mesmo padrao/mesma nota de mypy que
    # `worker/tarefas/fiscal.py::gerar_afd` ja documenta.
    from app.integracoes.folha.comum.execucao import (  # type: ignore[import-not-found]
        executar_exportacao_folha,
    )

    fabrica = _fabrica_de_sessoes()
    async with fabrica() as sessao:
        await _aplicar_tenant(sessao, tenant_id)
        resultado: dict[str, Any] = await executar_exportacao_folha(
            sessao,
            tenant_id=UUID(tenant_id),
            integracao_id=UUID(integracao_id),
            processamento_id=UUID(str(ctx.get("job_id"))),
            empresa_id=UUID(empresa_id),
            parceiro=parceiro,
            periodo_id=UUID(periodo_id) if periodo_id else None,
            competencia_folha=competencia_folha,
            unidade_id=UUID(unidade_id) if unidade_id else None,
            somente_fechados=somente_fechados,
        )

    logger.info(
        "exportar_folha concluida",
        extra={"integracaoId": integracao_id, "totalLinhas": resultado.get("totalLinhas")},
    )
    return resultado


# =============================================================================
# `importar_arquivo_generico` (F13/A8, T19) -- ver docstring do topo do
# modulo. Mesmo padrao estrutural de `worker/tarefas/importacoes.py::
# importar_colaboradores` (F2): duas transacoes (marca `processando`, depois
# processa e finaliza), publica `importacao.concluida` reaproveitando o MESMO
# envelope daquele modulo (`construir_envelope_evento`/`publicar_evento`,
# import de modulo irmao dentro do proprio pacote `worker` -- nao atravessa a
# fronteira `apps/api`/`apps/worker`, entao nao e o mesmo tipo de import
# tardio usado abaixo para `app.integracoes.*`).
# =============================================================================

_STATUS_FINAIS_IMPORTACAO = frozenset({"concluido", "concluido_com_erros", "falhou", "cancelado"})

#: `importacoes.status` -> `importacao.concluida.dados.status` (events.yaml
#: usa `concluidoComErros`, nao `concluido_com_erros`) -- copia pequena e
#: deliberada da mesma tabela que `worker/tarefas/importacoes.py` ja usa
#: (privada la, nao reexportada; duplicar 3 linhas e mais seguro que acoplar
#: a um simbolo `_` de outro modulo/agente).
_STATUS_PARA_EVENTO_IMPORTACAO: dict[str, str] = {
    "concluido": "concluido",
    "concluido_com_erros": "concluidoComErros",
    "falhou": "falhou",
}

#: Tipos aceitos pelo endpoint generico `POST /v1/importacoes` que JA tem
#: pipeline de processamento nesta tarefa. Os demais (estrutura/escalas/
#: feriados/marcacoes/banco_horas/biometria) nao tem implementacao nenhuma
#: ainda em nenhuma fase -- fora do escopo de T19 (importador de AFD de
#: terceiro), ver docstring de `app.integracoes.importadores.servico`.
_TIPOS_SUPORTADOS_GENERICO = frozenset({"afd_terceiro"})


def _envelope_conclusao_importacao(
    *, tenant_id: str, importacao: Importacao, resultado_erros: list[dict[str, Any]] | None
) -> dict[str, Any]:
    status_evento = _STATUS_PARA_EVENTO_IMPORTACAO.get(importacao.status, importacao.status)
    return construir_envelope_evento(
        tipo="importacao.concluida",
        versao=1,
        tenant_id=tenant_id,
        empresa_id=str(importacao.empresa_id) if importacao.empresa_id else None,
        dados={
            "importacaoId": str(importacao.id),
            "tipo": importacao.tipo,
            "status": status_evento,
            "totalLinhas": importacao.total_linhas,
            "linhasSucesso": importacao.linhas_sucesso,
            "linhasErro": importacao.linhas_erro,
            "relatorioDisponivel": bool(resultado_erros),
        },
    )


async def importar_arquivo_generico(
    ctx: dict[str, Any],
    *,
    tenant_id: str,
    importacao_id: str,
) -> dict[str, Any]:
    """Processa uma linha de `importacoes` enfileirada por `POST /v1/
    importacoes` (RFC-017) para qualquer `tipo` sem pipeline dedicado
    próprio. Hoje só `afd_terceiro` tem processamento real -- ver docstring
    do topo do módulo.
    """
    logger.info(
        "importar_arquivo_generico recebida",
        extra={"jobId": ctx.get("job_id"), "tenantId": tenant_id, "importacaoId": importacao_id},
    )
    tenant_uuid = UUID(tenant_id)
    importacao_uuid = UUID(importacao_id)
    fabrica = _fabrica_de_sessoes()

    async with fabrica() as sessao:
        await _aplicar_tenant(sessao, tenant_id)
        importacao = await sessao.get(Importacao, importacao_uuid)
        if importacao is None:
            logger.warning(
                "importacao nao encontrada",
                extra={"importacaoId": importacao_id, "tenantId": tenant_id},
            )
            return {"implementado": True, "encontrada": False, "importacaoId": importacao_id}
        if importacao.status in _STATUS_FINAIS_IMPORTACAO:
            # Idempotencia entre execucoes: job reenfileirado ou reentrega do
            # ARQ (at-least-once) nao reprocessa uma importacao ja concluida
            # -- mesmo raciocinio de `importar_colaboradores` (F2).
            logger.info(
                "importacao ja processada, ignorando reexecucao",
                extra={"importacaoId": importacao_id, "status": importacao.status},
            )
            return {
                "implementado": True,
                "jaProcessada": True,
                "importacaoId": importacao_id,
                "status": importacao.status,
            }
        importacao.status = "processando"
        importacao.iniciado_em = _agora()
        await sessao.commit()

    async with fabrica() as sessao:
        await _aplicar_tenant(sessao, tenant_id)
        importacao = await sessao.get(Importacao, importacao_uuid)
        if importacao is None:  # pragma: no cover - checado acima na mesma transacao logica
            return {"implementado": True, "encontrada": False, "importacaoId": importacao_id}

        if importacao.tipo not in _TIPOS_SUPORTADOS_GENERICO:
            importacao.status = "falhou"
            importacao.concluido_em = _agora()
            importacao.erros = {
                "linhas": [],
                "arquivo": [
                    {
                        "campo": "tipo",
                        "codigo": "PONTO-INT-005",
                        "mensagem": (
                            f"Tipo de importacao '{importacao.tipo}' ainda nao suportado pelo "
                            "importador generico (so afd_terceiro tem pipeline real nesta fase)."
                        ),
                    }
                ],
            }
            await sessao.commit()
            envelope = _envelope_conclusao_importacao(
                tenant_id=tenant_id, importacao=importacao, resultado_erros=None
            )
            publicar_evento(envelope)
            return {"implementado": True, "importacaoId": importacao_id, "status": "falhou"}

        # Import tardio: `apps/worker` so instala `apps/api` como biblioteca
        # na imagem `runtime` (ADR-009) -- mesmo padrao/mesma nota de mypy
        # que `worker/tarefas/fiscal.py::gerar_afd` e `worker/tarefas/
        # relatorios.py::executar_relatorio` ja documentam para
        # `app.comum.armazenamento`.
        from app.comum.armazenamento import obter_objeto  # type: ignore[import-not-found]
        from app.core.erros import ErroDeAplicacao  # type: ignore[import-not-found]
        from app.integracoes.importadores.afd_terceiro.servico import (  # type: ignore[import-not-found]
            ArquivoAfdInvalido,
            processar_arquivo,
        )

        empresa_id_bruto = str(importacao.empresa_id) if importacao.empresa_id else None
        parametros_importacao = importacao.parametros or {}
        rep_p_id_bruto = parametros_importacao.get("repPId")

        if empresa_id_bruto is None or not rep_p_id_bruto:
            # Nao deveria acontecer: `app.integracoes.importadores.servico.
            # criar_importacao` resolve e grava `parametros.repPId` na
            # criacao (sincrono), antes de enfileirar. Defesa em
            # profundidade, nao o caminho feliz.
            importacao.status = "falhou"
            importacao.concluido_em = _agora()
            importacao.erros = {
                "linhas": [],
                "arquivo": [
                    {
                        "campo": "parametros",
                        "codigo": "PONTO-IMP-001",
                        "mensagem": "empresaId ou parametros.repPId ausente na importacao.",
                    }
                ],
            }
            await sessao.commit()
            envelope = _envelope_conclusao_importacao(
                tenant_id=tenant_id, importacao=importacao, resultado_erros=None
            )
            publicar_evento(envelope)
            return {"implementado": True, "importacaoId": importacao_id, "status": "falhou"}

        try:
            conteudo = await obter_objeto(importacao.conteudo_ref or "")
        except ErroDeAplicacao:
            # Falha de INFRAESTRUTURA (armazenamento de objetos fora do ar,
            # `PONTO-INT-003`) -- deliberadamente NAO capturada como falha
            # PERMANENTE da importacao: propaga, o ARQ reentrega o job
            # (retentativa automatica), e a linha fica `processando` ate
            # resolver. Diferente de `ArquivoAfdInvalido` abaixo, que e
            # problema do CONTEUDO do arquivo (retentar nao adianta).
            logger.exception(
                "importar_arquivo_generico: falha ao ler o armazenamento de objetos",
                extra={"importacaoId": importacao_id},
            )
            raise

        try:
            resultado = await processar_arquivo(
                sessao,
                tenant_id=tenant_uuid,
                empresa_id=UUID(empresa_id_bruto),
                rep_p_id=UUID(str(rep_p_id_bruto)),
                importacao=importacao,
                conteudo=conteudo,
            )
        except ArquivoAfdInvalido as exc:
            importacao.status = "falhou"
            importacao.concluido_em = _agora()
            importacao.erros = {
                "linhas": [],
                "arquivo": [{"campo": "arquivo", "codigo": exc.codigo, "mensagem": str(exc)}],
            }
            await sessao.commit()
            envelope = _envelope_conclusao_importacao(
                tenant_id=tenant_id, importacao=importacao, resultado_erros=None
            )
            publicar_evento(envelope)
            return {"implementado": True, "importacaoId": importacao_id, "status": "falhou"}

        importacao.total_linhas = resultado.total_linhas_tipo7
        importacao.linhas_processadas = resultado.total_linhas_tipo7
        importacao.linhas_sucesso = resultado.linhas_sucesso
        importacao.linhas_erro = resultado.linhas_erro
        importacao.erros = {"linhas": resultado.erros} if resultado.erros else None
        importacao.status = "concluido" if not resultado.erros else "concluido_com_erros"
        importacao.concluido_em = _agora()
        await sessao.commit()

        envelope = _envelope_conclusao_importacao(
            tenant_id=tenant_id, importacao=importacao, resultado_erros=resultado.erros
        )

    publicar_evento(envelope)
    logger.info(
        "importar_arquivo_generico concluida",
        extra={
            "importacaoId": importacao_id,
            "status": importacao.status,
            "linhasSucesso": importacao.linhas_sucesso,
            "linhasErro": importacao.linhas_erro,
        },
    )
    return {
        "implementado": True,
        "importacaoId": importacao_id,
        "status": importacao.status,
        "totalLinhas": importacao.total_linhas,
        "linhasSucesso": importacao.linhas_sucesso,
        "linhasErro": importacao.linhas_erro,
    }
