"""Idempotência genérica de escrita (F13/A1, T3).

`PONTO-IDEM-001/002/003` (`packages/contracts/errors.yaml`) definem o
contrato: toda escrita exige `Idempotency-Key`; reusar a chave com corpo
diferente é `409 PONTO-IDEM-002`; duas requisições concorrentes com a mesma
chave, a segunda responde `409 PONTO-IDEM-003`. `app.marcacao.pipeline.
idempotencia` (F5) já prova o padrão, mas está amarrado à tabela `marcacoes`
(FK `marcacao_id`) — não reaproveitável fora daquele domínio (§2.4 do PCF).
Esta é a versão genérica, aplicada só às rotas que A1/A3/A5/A8 constroem
nesta fase (`admin` api-clients/api-keys, `webhooks`, `integracoes`) — nunca
retrofit nas ~130 rotas de F1–F12 (proibição explícita do PCF, §9.12).

**Por que não é um único `Depends()` que resolve tudo sozinho.** Uma
dependência FastAPI roda ANTES do handler: ela não tem como saber a resposta
que o handler vai produzir para gravá-la (replay) nem para devolver 200 sem
executar a lógica de novo. A solução usada aqui é a mesma forma que
`app.marcacao.pipeline.idempotencia` já estabeleceu (funções explícitas,
chamadas pelo próprio handler) mais um passo `Depends()` real
(`exigir_idempotencia()`) para a parte que É pura leitura de cabeçalho/corpo:

    1. `Depends(exigir_idempotencia())` — lê `Idempotency-Key` (`400
       PONTO-IDEM-001` se ausente/vazio) e o corpo cru da requisição, devolve
       `ChaveIdempotencia(valor, corpo_hash)`. Não toca banco.
    2. O handler chama `abrir_operacao(sessao, tenant_id=..., escopo=...,
       chave=...)` **depois** de resolver `tenant_id` (de `Sujeito` ou de
       `ClienteAutenticado`, conforme a rota). Devolve `ResultadoAbertura`:
       se `ja_concluido`, o handler devolve a resposta ARMAZENADA sem
       reexecutar a lógica de negócio; senão, prossegue normalmente.
    3. Ao final, o handler chama `concluir_operacao(sessao, registro_id=...,
       status_http=..., corpo_resposta=...)` para persistir o resultado.

**Trava de concorrência.** `pg_try_advisory_xact_lock` sobre o hash de
`tenant_id + escopo + chave`, mesma técnica de
`app.marcacao.pipeline.idempotencia.travar_idempotency_key` — escopada à
transação corrente (libera sozinha no commit/rollback de `SessaoDb`/
`sessao_com_tenant_resolvido`). Segunda requisição com a mesma chave, ainda
em voo, falha a tentativa (`pg_try_advisory_xact_lock` não bloqueia, devolve
`false` na hora) e responde `PONTO-IDEM-003` sem tocar a tabela.

**Efeito colateral do design: `abrir_operacao`/`concluir_operacao` rodam na
MESMA sessão/transação do handler.** Se a lógica de negócio falhar e a
transação sofrer rollback (`app/db/sessao.py:obter_sessao`), a linha de
`idempotencia_chaves` desta tentativa desaparece junto — uma tentativa que
falhou nunca "envenena" a chave para sempre; só uma tentativa que TERMINOU
(`concluir_operacao` chamado e a transação commitada) fica disponível para
replay. Isso é compatível com `PONTO-IDEM-002`/`003`: o que a chave impede é
reusar o MESMO identificador para uma operação DIFERENTE enquanto a anterior
ainda existir (em voo ou concluída), nunca tentar de novo depois de uma falha.

**TTL de 24h (`PONTO-IDEM-002`: "usada nas ÚLTIMAS 24 HORAS").** Uma linha
expirada (`expira_em <= agora`) é tratada como inexistente: é apagada e a
chave fica livre para uma operação nova, mesmo com corpo diferente.

Tabela `idempotencia_chaves` (migration `0002_idempotencia_chaves`, exclusiva
desta fase — ver nota em `packages/contracts/**` no relatório da fase: a
tabela NÃO foi replicada em `packages/contracts/schema.sql`/`ponto_contracts`
porque esses arquivos ficam congelados fora das três RFCs nomeadas no PCF
§2.1, e nenhuma delas cobre esta tabela; o PCF autoriza migration nova sem
mencionar edição de schema.sql, então o modelo Python desta tabela vive aqui,
como `sqlalchemy.Table` solto — não em `ponto_contracts` — e é acessado só
por Core, nunca por um novo model ORM registrado na `Base` do pacote
congelado).
"""

from __future__ import annotations

import datetime as _dt
import hashlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Annotated, Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from fastapi import Header, Request
from sqlalchemy.dialects import postgresql as sa_pg
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.erros import ErroDeAplicacao

__all__ = [
    "TTL_IDEMPOTENCIA",
    "ChaveIdempotencia",
    "ResultadoAbertura",
    "abrir_operacao",
    "concluir_operacao",
    "exigir_idempotencia",
]

#: Validade de uma chave (`PONTO-IDEM-002`: "nas últimas 24 horas").
TTL_IDEMPOTENCIA = _dt.timedelta(hours=24)

#: Espera sugerida (`Retry-After`) para uma requisição concorrente reapresentar
#: a mesma chave — não é o tempo real da operação em voo (desconhecido daqui),
#: só um valor pequeno e honesto o bastante para não incentivar polling apertado.
_RETRY_AFTER_CONCORRENTE_S = 2

metadata_idempotencia = sa.MetaData()

#: Espelho da tabela `idempotencia_chaves` (ver docstring do módulo: migration
#: própria desta fase, não replicada em `packages/contracts/schema.sql`).
#: Acesso só por SQLAlchemy Core — nunca um segundo model ORM fora do pacote
#: `ponto_contracts` congelado.
tabela_idempotencia = sa.Table(
    "idempotencia_chaves",
    metadata_idempotencia,
    sa.Column("id", sa_pg.UUID(as_uuid=True), primary_key=True),
    sa.Column("tenant_id", sa_pg.UUID(as_uuid=True), nullable=False),
    sa.Column("escopo", sa.Text(), nullable=False),
    sa.Column("chave", sa.Text(), nullable=False),
    sa.Column("corpo_hash", sa.Text(), nullable=False),
    sa.Column("status", sa.Text(), nullable=False),
    sa.Column("resposta_status", sa.Integer(), nullable=True),
    sa.Column("resposta_corpo", sa_pg.JSONB(), nullable=True),
    sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
    sa.Column("expira_em", sa.DateTime(timezone=True), nullable=False),
)

STATUS_EM_ANDAMENTO = "em_andamento"
STATUS_CONCLUIDO = "concluido"


@dataclass(frozen=True, slots=True)
class ChaveIdempotencia:
    """Estado extraído do cabeçalho/corpo da requisição, antes de o handler
    conhecer `tenant_id`/`escopo` (que dependem de qual autenticação a rota
    usa — humana via `Sujeito` ou de cliente via `ClienteAutenticado`)."""

    valor: str
    corpo_hash: str


@dataclass(frozen=True, slots=True)
class ResultadoAbertura:
    """Devolvido por `abrir_operacao`.

    `ja_concluido=True` → a MESMA operação já terminou antes: o handler deve
    devolver `resposta_status`/`resposta_corpo` sem reexecutar nada.
    `ja_concluido=False` → operação nova (ou uma tentativa anterior que nunca
    chegou a `concluir_operacao`, sob a mesma trava exclusiva): o handler
    prossegue e chama `concluir_operacao(registro_id=...)` ao final.
    """

    registro_id: UUID
    ja_concluido: bool
    resposta_status: int | None
    resposta_corpo: Any | None


def exigir_idempotencia() -> Callable[..., Awaitable[ChaveIdempotencia]]:
    """Fábrica de dependência FastAPI: `Depends(exigir_idempotencia())`.

    Declarada como fábrica (em vez de uma dependência solta) para ficar no
    mesmo formato de `exigir_escopo`/`exigir_limite_taxa` deste pacote — não
    recebe argumento hoje, mas mantém a rota livre para evoluir sem trocar a
    forma de uso em todo lugar que já a chama.

    Nota deliberada: o parâmetro `idempotency_key` é declarado `str | None`
    (nunca `str` obrigatório) porque um `Header(...)` obrigatório faria o
    FastAPI recusar a requisição por `RequestValidationError` ANTES desta
    função rodar — o que produziria `PONTO-VAL-011` (cabeçalho ausente
    genérico), não o código correto do catálogo para este caso específico,
    `PONTO-IDEM-001`.
    """

    async def _dependencia(
        request: Request,
        idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    ) -> ChaveIdempotencia:
        chave = (idempotency_key or "").strip()
        if not chave:
            raise ErroDeAplicacao("PONTO-IDEM-001")
        corpo_bruto = await request.body()
        corpo_hash = hashlib.sha256(corpo_bruto).hexdigest()
        return ChaveIdempotencia(valor=chave, corpo_hash=corpo_hash)

    return _dependencia


async def _travar(sessao: AsyncSession, *, tenant_id: UUID, escopo: str, chave: str) -> bool:
    texto_chave = f"{tenant_id}:{escopo}:{chave}"
    resultado = await sessao.execute(
        sa.text("SELECT pg_try_advisory_xact_lock(hashtextextended(:c, 0))"),
        {"c": texto_chave},
    )
    return bool(resultado.scalar_one())


async def abrir_operacao(
    sessao: AsyncSession,
    *,
    tenant_id: UUID,
    escopo: str,
    chave: ChaveIdempotencia,
    agora: _dt.datetime | None = None,
) -> ResultadoAbertura:
    """Reserva/verifica a chave para `(tenant_id, escopo, chave.valor)`.

    Levanta `PONTO-IDEM-003` (requisição concorrente com a mesma chave, em
    voo agora) ou `PONTO-IDEM-002` (mesma chave, corpo diferente, dentro do
    TTL de 24h).
    """
    agora = agora or _dt.datetime.now(_dt.UTC)

    obteve_trava = await _travar(sessao, tenant_id=tenant_id, escopo=escopo, chave=chave.valor)
    if not obteve_trava:
        raise ErroDeAplicacao(
            "PONTO-IDEM-003",
            tentar_novamente_em=_RETRY_AFTER_CONCORRENTE_S,
            cabecalhos={"Retry-After": str(_RETRY_AFTER_CONCORRENTE_S)},
            contexto_log={"escopo": escopo},
        )

    linha = (
        (
            await sessao.execute(
                sa.select(tabela_idempotencia).where(
                    tabela_idempotencia.c.tenant_id == tenant_id,
                    tabela_idempotencia.c.escopo == escopo,
                    tabela_idempotencia.c.chave == chave.valor,
                )
            )
        )
        .mappings()
        .one_or_none()
    )

    if linha is not None and linha["expira_em"] <= agora:
        await sessao.execute(
            sa.delete(tabela_idempotencia).where(tabela_idempotencia.c.id == linha["id"])
        )
        linha = None

    if linha is not None:
        if linha["corpo_hash"] != chave.corpo_hash:
            raise ErroDeAplicacao("PONTO-IDEM-002", contexto_log={"escopo": escopo})
        if linha["status"] == STATUS_CONCLUIDO:
            return ResultadoAbertura(
                registro_id=linha["id"],
                ja_concluido=True,
                resposta_status=linha["resposta_status"],
                resposta_corpo=linha["resposta_corpo"],
            )
        # `em_andamento` sobrevivendo apesar da trava exclusiva obtida acima só
        # acontece se uma tentativa anterior chegou a inserir a linha e depois
        # nunca chamou `concluir_operacao` NA MESMA transação que a inseriu
        # (não deveria: `SessaoDb`/`sessao_com_tenant_resolvido` sempre fazem
        # commit ou rollback) -- reaproveita a linha em vez de around, e deixa
        # o handler tentar de novo.
        return ResultadoAbertura(
            registro_id=linha["id"], ja_concluido=False, resposta_status=None, resposta_corpo=None
        )

    novo_id = uuid4()
    await sessao.execute(
        sa.insert(tabela_idempotencia).values(
            id=novo_id,
            tenant_id=tenant_id,
            escopo=escopo,
            chave=chave.valor,
            corpo_hash=chave.corpo_hash,
            status=STATUS_EM_ANDAMENTO,
            criado_em=agora,
            expira_em=agora + TTL_IDEMPOTENCIA,
        )
    )
    return ResultadoAbertura(
        registro_id=novo_id, ja_concluido=False, resposta_status=None, resposta_corpo=None
    )


async def concluir_operacao(
    sessao: AsyncSession,
    *,
    registro_id: UUID,
    status_http: int,
    corpo_resposta: Any,
) -> None:
    """Persiste o resultado da operação para replay futuro. Chamado pelo
    handler ao final, sempre dentro da mesma transação de `abrir_operacao`."""
    await sessao.execute(
        sa.update(tabela_idempotencia)
        .where(tabela_idempotencia.c.id == registro_id)
        .values(status=STATUS_CONCLUIDO, resposta_status=status_http, resposta_corpo=corpo_resposta)
    )
