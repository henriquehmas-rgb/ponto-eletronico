"""T11 -- a costura entre "evento de dominio publicado" e uma linha durável em
`webhook_entregas`. A tarefa mais delicada da fase (PCF F13 secao 6, T11):
leia esta docstring por completo antes de mudar qualquer coisa aqui.

Requisito nao negociavel (PCF §2.2): a linha em `webhook_entregas` so pode
existir depois que o fato de dominio esta de fato commitado -- nunca antes.

Rota escolhida: (b), nao (a)
-----------------------------
O PCF (T11) apresenta duas rotas aceitaveis:

  (a) threading do `AsyncSession` ate `publicar()`, fazendo o INSERT em
      `webhook_entregas` na MESMA transacao do fato de dominio;
  (b) `publicar()` mantem a assinatura atual (so recebe `envelope`) e, alem
      do `BARRAMENTO_INTERNO.append` inalterado, dispara um mecanismo
      assincrono que so considera o evento "real" depois de um sinal de
      commit confirmado.

Decisao (A3): (b). Motivo, nao so preferencia -- a rota (a) e
estruturalmente incompativel com o ownership desta fase: mudar a assinatura
de `publicar()` exige mudar TODOS os call sites que a chamam (`app.marcacao.
pipeline.eventos_marcacao`, `app.marcacao.comprovantes.eventos_comprovante`,
e os modulos equivalentes de F2/F4/F10/F12), e esses call sites vivem dentro
de `apps/api/app/{marcacao,apuracao,workflow,pessoas,fiscal}/**` FORA do
unico arquivo que o PCF §5.2/§5.4 autoriza A3 a tocar em cada dominio (o
corpo de `publicar()` em `*/eventos.py`, nada mais). Sem poder tocar os call
sites, mudar a assinatura de `publicar()` quebraria o import de nove modulos
que pertencem a outras fases -- exatamente o tipo de dano entre fases que o
ownership exclusivo do projeto existe para prevenir. Rota (b) e a unica que
cabe inteiramente dentro do que este agente pode editar.

O sinal de commit confirmado, precisamente
-------------------------------------------
`apps/api/app/db/sessao.py::obter_sessao` (INTOCAVEL, so leitura) e o UNICO
ponto que chama `sessao.commit()` para toda rota HTTP do sistema -- uma
`AsyncSession` por requisicao, `async with fabrica() as sessao: yield sessao;
await sessao.commit()`. Isso significa que TODA sessao usada por qualquer
handler (inclusive os nove `eventos.py` que este modulo instrumenta,
indiretamente, via `publicar()`) e criada pela MESMA fabrica
(`app.db.sessao.fabrica_de_sessoes()`), que por sua vez usa a classe `Session`
padrao do SQLAlchemy (nunca uma subclasse customizada -- confirmado por
leitura de `app/db/sessao.py`). Isso permite um listener GLOBAL de evento do
SQLAlchemy, registrado uma unica vez por processo, sem precisar que
`publicar()` receba a sessao como parametro:

    sqlalchemy.event.listens_for(Session, "after_commit")

`AsyncSession.commit()` delega para `self.sync_session.commit()` via
`greenlet_spawn` (ponte assincrona oficial do SQLAlchemy) -- o listener
"after_commit" roda de fato, de forma sincrona, dentro dessa ponte, estritamente
DEPOIS que o COMMIT real no Postgres retornou com sucesso. Nunca antes.

Como associar "o envelope publicado por este `publicar()`" a "esta sessao
que acabou de commitar", sem `publicar()` receber a sessao
-----------------------------------------------------------------------------
Um `ContextVar` (mesmo padrao ja em uso por `app.core.contexto`, cuja propria
docstring documenta que "asyncio propaga o contexto para toda Task filha
automaticamente: o valor definido no middleware continua visivel dentro do
handler, do worker de background e do driver do banco" -- e exatamente essa
propriedade que sustenta este desenho): `publicar()` (corpo aditivo em cada
`eventos.py`) chama `registrar_pendente(envelope)`, que empilha o envelope
numa lista guardada no `ContextVar` da Task/request corrente. Como a
requisicao inteira -- handler, `publicar()`, e o `commit()` feito por
`obter_sessao` depois que o handler retorna -- roda dentro da MESMA Task
asyncio (FastAPI nao cria Task nova por dependencia), o `ContextVar` setado
por `publicar()` continua visivel quando o listener `after_commit` executa.

O listener global le a lista pendente da Task corrente, LIMPA o `ContextVar`
imediatamente (evita reprocessar em caso de commit duplo/aninhado) e grava
cada envelope em `webhook_entregas` via uma conexao SQL SEPARADA e
SINCRONA (driver `psycopg`, ja dependencia do projeto para o Alembic --
`apps/api/pyproject.toml`, nao e dependencia nova). Sincrona de proposito:
o callback `after_commit` do SQLAlchemy roda dentro de uma ponte greenlet
sincrona; chamar `asyncio.run()` dali dispararia `RuntimeError: asyncio.run()
cannot be called from a running event loop` (ja estamos dentro do loop da
API). Uma conexao sincrona evita esse problema por completo, ao custo de
alguns milissegundos de latencia adicional na resposta HTTP (aceito e
documentado abaixo).

Janela de risco aceita
-----------------------
Entre o COMMIT do fato de dominio (que already aconteceu, garantido pelo
`after_commit`) e o COMMIT da propria insercao em `webhook_entregas` (a
proxima linha de codigo, na mesma chamada sincrona), existe uma janela de
poucos milissegundos em que um crash do processo (kill -9, OOM, queda de
energia) perderia o evento -- ele nunca seria entregue, porque nunca virou
linha durável. Esta janela e:

* pequena (uma unica instrucao SQL, sem I/O de rede alem do proprio Postgres);
* sincrona com a resposta HTTP (o cliente so recebe 2xx depois que a
  insercao de fan-out terminou ou falhou -- nunca "fire and forget" para os
  nove produtores de `apps/api`, que sao a maioria dos 13 pontos do
  catalogo);
* estritamente menor que a alternativa descartada (rota (a) exigiria tocar
  arquivos fora do ownership desta fase) e MENOR que a janela aceita para os
  tres produtores fora de `apps/api` (worker/device-gw, ver `_apos_commit`
  do lado worker em `worker.despacho_webhooks`), que usam
  `asyncio.create_task` (fire-and-forget) por rodarem em contexto
  verdadeiramente assincrono sem callback sincrono do SQLAlchemy disponivel.

Se uma insercao de fan-out falhar (Postgres indisponivel, por exemplo), o
erro e logado e ENGOLIDO -- nunca propagado para o chamador: um evento que
falha ao entrar na fila de webhook NUNCA deve fazer a escrita de dominio
original (ja commitada) parecer ter falhado para quem chamou a API. Esta e
uma escolha deliberada de disponibilidade: o consumidor de webhook pode
perder um evento nessa janela; o cliente da API nunca ve uma falha espuria.

Eventos internos (`webhook_publico: false`)
---------------------------------------------
`ocorrencia.aberta`, `comprovante.emitido` e `webhook.desabilitado` passam
por aqui tambem (chamam `publicar()` como qualquer outro), mas a consulta de
fan-out (`eventos @> ARRAY[:evento]`) nunca encontra um webhook ativo que os
assine -- `criarWebhook` recusa evento nao-publico com `PONTO-WEBH-003`, entao
nenhuma linha de `webhooks.eventos` pode conter um nome interno. O filtro
`_EVENTOS_INTERNOS` abaixo e so uma otimizacao (evita a consulta SQL de todo),
nao uma regra de seguranca nova.
"""

from __future__ import annotations

import contextvars
import logging
from typing import Any

import sqlalchemy as sa
from sqlalchemy import event
from sqlalchemy.orm import Session

logger = logging.getLogger("integracoes.webhooks.fan_out")

__all__ = [
    "EVENTOS_INTERNOS",
    "SQL_INSERIR_ENTREGAS_PENDENTES",
    "instalar_listener",
    "payload_json",
    "registrar_pendente",
]

#: Nomes dos tres eventos internos do catalogo (`events.yaml`,
#: `webhook_publico: false`). Duplicado aqui de proposito, mesmo padrao ja
#: documentado por `worker/filas.py`/`app/core/filas.py` (constante pequena e
#: estavel, custo de import cruzado maior que o risco de desalinhamento):
#: nenhum evento novo pode ser adicionado a `events.yaml` sem RFC, entao esta
#: lista so muda junto de uma mudanca de contrato explicita.
EVENTOS_INTERNOS = frozenset({"ocorrencia.aberta", "comprovante.emitido", "webhook.desabilitado"})
_EVENTOS_INTERNOS = EVENTOS_INTERNOS  # alias interno, mantido pelos usos abaixo

#: Pilha de envelopes pendentes de fan-out da Task/requisicao corrente.
#: Default `None` (nao `[]`) para distinguir "nenhum publicar() chamado ainda"
#: de "lista vazia" sem alocar por Task a toa.
_PENDENTES: contextvars.ContextVar[list[dict[str, Any]] | None] = contextvars.ContextVar(
    "ponto_webhooks_fan_out_pendentes", default=None
)

#: SQL canonico do fan-out (INSERT...SELECT: uma linha de `webhook_entregas`
#: por webhook ATIVO que assina `:evento`, no tenant `:tenant_id`). Publico
#: (nao `_`-prefixado) porque `apps/worker/worker/despacho_webhooks.py`
#: reaproveita este MESMO texto para os tres produtores fora de `apps/api`
#: (worker/device-gw) que tambem alimentam `webhook_entregas` -- `apps/worker`
#: pode importar `app.*` como biblioteca (ADR-009), entao reaproveitar aqui
#: evita duas copias do mesmo SQL divergindo com o tempo.
SQL_INSERIR_ENTREGAS_PENDENTES = sa.text(
    """
    INSERT INTO webhook_entregas
        (tenant_id, webhook_id, evento, evento_id, payload, tentativa, status, proxima_tentativa_em)
    SELECT w.tenant_id, w.id, :evento, :evento_id, CAST(:payload AS jsonb), 1, 'pendente', now()
    FROM webhooks w
    WHERE w.tenant_id = :tenant_id
      AND w.status = 'ativo'
      AND w.eventos @> ARRAY[:evento]::text[]
      AND w.excluido_em IS NULL
    """
)

_engine_sync: Any = None
_listener_instalado = False


def registrar_pendente(envelope: dict[str, Any]) -> None:
    """Chamada ADITIVA dentro do corpo de `publicar()` de cada `eventos.py`
    (apps/api) -- empilha o envelope no `ContextVar` da requisicao corrente,
    para o listener `after_commit` processar depois que o commit real
    acontecer. Nunca levanta excecao: uma falha aqui nao pode impedir
    `BARRAMENTO_INTERNO.append`, que os testes de F2/F4/F5/F10/F12 dependem
    continuar funcionando exatamente como antes."""
    try:
        pendentes = _PENDENTES.get()
        if pendentes is None:
            pendentes = []
            _PENDENTES.set(pendentes)
        pendentes.append(envelope)
    except Exception:  # pragma: no cover - defensivo, nunca deve ocorrer
        logger.exception("falha ao empilhar envelope pendente de fan-out")


def _dsn_sincrona(database_url: str) -> str:
    """`postgresql+asyncpg://...` -> `postgresql+psycopg://...` (mesma
    conversao de `apps/api/migrations/env.py`, duplicada aqui de proposito
    -- ver docstring do modulo sobre por que a insercao de fan-out precisa
    ser sincrona)."""
    for prefixo in ("postgresql+asyncpg://", "postgres+asyncpg://", "postgresql+psycopg_async://"):
        if database_url.startswith(prefixo):
            return "postgresql+psycopg://" + database_url[len(prefixo) :]
    if database_url.startswith("postgresql://"):
        return "postgresql+psycopg://" + database_url[len("postgresql://") :]
    return database_url


def _obter_engine_sync() -> Any:
    global _engine_sync
    if _engine_sync is None:
        from app.core.config import obter_configuracao

        config = obter_configuracao()
        _engine_sync = sa.create_engine(
            _dsn_sincrona(config.database_url),
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=5,
        )
    return _engine_sync


def reiniciar_engine_sync_para_testes() -> None:
    """SOMENTE para teste: descarta a engine sincrona cacheada."""
    global _engine_sync
    if _engine_sync is not None:
        _engine_sync.dispose()
    _engine_sync = None


def _inserir_entregas_sync(pendentes: list[dict[str, Any]]) -> None:
    engine = _obter_engine_sync()
    with engine.begin() as conexao:
        for envelope in pendentes:
            tipo = envelope.get("tipo")
            if not tipo or tipo in _EVENTOS_INTERNOS:
                continue
            tenant_id = envelope.get("tenantId")
            evento_id = envelope.get("id")
            if not tenant_id or not evento_id:
                logger.warning(
                    "envelope pendente de fan-out sem tenantId/id, descartado",
                    extra={"tipo": tipo},
                )
                continue
            conexao.execute(
                sa.text("SELECT set_config('app.tenant_id', :tenant, true)"),
                {"tenant": str(tenant_id)},
            )
            conexao.execute(
                SQL_INSERIR_ENTREGAS_PENDENTES,
                {
                    "evento": tipo,
                    "evento_id": str(evento_id),
                    "payload": payload_json(envelope),
                    "tenant_id": str(tenant_id),
                },
            )


def payload_json(envelope: dict[str, Any]) -> str:
    """Serializa o envelope para o parametro `:payload` do INSERT
    (`CAST(:payload AS jsonb)`). Publico -- reaproveitado por
    `apps/worker/worker/despacho_webhooks.py` (ver docstring de
    `SQL_INSERIR_ENTREGAS_PENDENTES`)."""
    import json

    return json.dumps(envelope, ensure_ascii=False, default=str)


def _apos_commit(sessao: Session) -> None:
    """Listener global `after_commit` -- roda para TODO commit de TODA
    `Session`/`AsyncSession` do processo (`sessao` aqui e a `Session`
    sincrona interna que `AsyncSession` embrulha). So faz trabalho quando o
    `ContextVar` desta Task tem envelopes pendentes."""
    pendentes = _PENDENTES.get()
    if not pendentes:
        return
    # Limpa ANTES de processar: um envelope so pode ser inserido uma vez,
    # mesmo que este listener seja re-entrado (nao deveria, mas defensivo).
    _PENDENTES.set(None)
    try:
        _inserir_entregas_sync(pendentes)
    except Exception:
        # NUNCA propaga: a escrita de dominio ja commitou com sucesso do
        # ponto de vista do chamador da API. Uma falha aqui vira log/alerta
        # de operacao, nunca um 500 espurio numa escrita que ja deu certo.
        logger.exception(
            "falha ao gravar fan-out de webhook_entregas apos commit",
            extra={"eventos": [e.get("tipo") for e in pendentes]},
        )


def instalar_listener() -> None:
    """Registra o listener `after_commit` uma unica vez por processo.
    Idempotente (`event.contains` evita registro duplicado se chamada mais
    de uma vez -- por exemplo, por mais de um modulo que importa este
    arquivo). Chamado eagerly no import de `app.routers.webhooks` (garante
    que o listener existe antes da primeira requisicao) e, defensivamente,
    de dentro de `registrar_pendente` via import do proprio modulo (o
    registro do listener acontece no import deste arquivo, nao em
    `registrar_pendente`)."""
    global _listener_instalado
    if _listener_instalado:
        return
    if not event.contains(Session, "after_commit", _apos_commit):
        event.listen(Session, "after_commit", _apos_commit)
    _listener_instalado = True


# Registrado no import do modulo (nao so quando `instalar_listener()` e
# chamada explicitamente) para que o listener exista assim que QUALQUER
# `eventos.py` importar `registrar_pendente` pela primeira vez -- inclusive
# se isso acontecer antes de `app.routers.webhooks` ser importado pela
# aplicacao (ordem de import de router nao e garantida).
instalar_listener()
