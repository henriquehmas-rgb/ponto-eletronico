"""Idempotencia de quatro chaves do registro de ponto (F5, T5).

`marcacao_idempotencia` (`packages/contracts/schema.sql`, secao 8) impoe a
unicidade GLOBAL (entre particoes/meses) de `(tenant_id, escopo, chave)` para
quatro escopos independentes e simultaneos:

* ``external_id``       -- canal ``api``: `externalId` do integrador, junto
  com o canal (`chave_external_id`).
* ``dispositivo_log``   -- catch-up de terminal: o par `dispositivoId` +
  `logExternoId` (`chave_dispositivo_log`).
* ``idempotency_key``   -- toda escrita: o cabecalho `Idempotency-Key`
  (`chave_idempotency_key`, identidade).
* ``offline_hmac``      -- item da fila offline (T7): o HMAC do item, junto
  com o dispositivo (`chave_offline_hmac`).

**Por que nao ha uma tabela de "reserva" para detectar requisicao concorrente
em voo (`PONTO-IDEM-003`).** `marcacao_idempotencia.marcacao_id` e `NOT NULL`
e tem FK para `marcacoes`: nao da para inserir a linha de idempotencia antes
de a marcacao existir, entao nao ha como "reservar" a chave no inicio da
transacao e completar depois. Em vez disso, `travar_idempotency_key` usa
`pg_try_advisory_xact_lock`: um lock consultivo, escopado a transacao (libera
sozinho no commit ou no rollback, mesmo se a funcao levantar excecao), tomado
sobre o hash de `tenant_id + escopo + chave`. Duas requisicoes com a MESMA
`Idempotency-Key` chegando ao mesmo tempo: a primeira obtem o lock e segue; a
segunda falha a tentativa (`pg_try_advisory_xact_lock` nao bloqueia, devolve
`false` na hora) e responde `PONTO-IDEM-003` sem tocar o banco.

**Por que a comparacao de "mesmo corpo" (`PONTO-IDEM-002` vs replay
verdadeiro) nao usa um hash do JSON bruto da requisicao.** Nenhuma tabela
desta fase guarda o corpo cru (nem deveria: aumentaria a superficie de dado
sensivel sem necessidade). Em vez disso, comparamos os campos que REALMENTE
definem a identidade do registro e que sobrevivem em `marcacoes` depois da
resolucao (colaborador ja resolvido por id/cpf/matricula, empresa, unidade,
canal, dispositivo, terminal, sentido informado, cpf, externalId,
logExternoId) -- ver `calcular_hash_identidade`. Campos que so existem no
corpo bruto e nunca persistem em `marcacoes` (matricula textual, latitude,
liveness, attestation) propositalmente NAO entram na comparacao: eles nao
mudam qual FATO esta sendo registrado, so como ele foi capturado.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from ponto_contracts import Marcacao, MarcacaoIdempotencia
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.erros import ErroDeAplicacao

ESCOPO_EXTERNAL_ID = "external_id"
ESCOPO_DISPOSITIVO_LOG = "dispositivo_log"
ESCOPO_IDEMPOTENCY_KEY = "idempotency_key"
ESCOPO_OFFLINE_HMAC = "offline_hmac"

#: Nome da constraint unica de `marcacao_idempotencia` -- usado para traduzir
#: `IntegrityError` de insercao concorrente na chave de dominio (o caminho
#: normal ja checa antes de inserir; isto so cobre a janela de corrida entre
#: o SELECT e o INSERT desta mesma transacao).
_CONSTRAINT_IDEMPOTENCIA = "uq_marcacao_idempotencia"


def chave_external_id(canal: str, external_id: str) -> str:
    """Chave do escopo ``external_id``: o par (canal, externalId) do
    integrador. O canal entra na chave porque `externalId` so e unico dentro
    do canal ``api`` -- o mesmo texto em outro canal e outra operacao."""
    return f"{canal}:{external_id}"


def chave_dispositivo_log(dispositivo_id: UUID, log_externo_id: int) -> str:
    """Chave do escopo ``dispositivo_log``: o catch-up de terminal (F6)."""
    return f"{dispositivo_id}:{log_externo_id}"


def chave_idempotency_key(idempotency_key: str) -> str:
    """Chave do escopo ``idempotency_key``: o cabeçalho, identidade -- o
    escopo ja isola o namespace, nao precisa prefixo."""
    return idempotency_key


def chave_offline_hmac(dispositivo_id: UUID, hmac: str) -> str:
    """Chave do escopo ``offline_hmac``: o HMAC do item da fila offline (T7),
    junto com o dispositivo (o HMAC ja e derivado da chave do aparelho, mas
    prefixar pelo dispositivo evita depender so disso para unicidade)."""
    return f"{dispositivo_id}:{hmac}"


def calcular_hash_identidade(
    *,
    colaborador_id: UUID | None,
    empresa_id: UUID | None,
    unidade_id: UUID | None,
    canal: str | None,
    dispositivo_id: UUID | None,
    terminal_id: UUID | None,
    sentido_informado: str | None,
    cpf: str,
    external_id: str | None,
    log_externo_id: int | None,
) -> str:
    """SHA-256 hex dos campos que definem o FATO sendo registrado, ja
    resolvidos (colaborador por id, nunca por cpf/matricula bruto). Usado
    para decidir se um reenvio pela mesma `Idempotency-Key` repete a MESMA
    operacao (`PONTO-IDEM-002` se nao) -- ver docstring do modulo."""
    campos: dict[str, Any] = {
        "colaboradorId": str(colaborador_id) if colaborador_id else None,
        "empresaId": str(empresa_id) if empresa_id else None,
        "unidadeId": str(unidade_id) if unidade_id else None,
        "canal": canal,
        "dispositivoId": str(dispositivo_id) if dispositivo_id else None,
        "terminalId": str(terminal_id) if terminal_id else None,
        "sentidoInformado": sentido_informado,
        "cpf": cpf,
        "externalId": external_id,
        "logExternoId": log_externo_id,
    }
    canonico = json.dumps(campos, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonico.encode("utf-8")).hexdigest()


def hash_identidade_da_marcacao(marcacao: Marcacao) -> str:
    """Mesma formula de `calcular_hash_identidade`, a partir de uma linha ja
    persistida de `marcacoes` -- usada para comparar contra o pedido novo."""
    return calcular_hash_identidade(
        colaborador_id=marcacao.colaborador_id,
        empresa_id=marcacao.empresa_id,
        unidade_id=marcacao.unidade_id,
        canal=marcacao.canal,
        dispositivo_id=marcacao.dispositivo_id,
        terminal_id=marcacao.terminal_id,
        sentido_informado=marcacao.sentido_informado,
        cpf=marcacao.cpf,
        external_id=marcacao.external_id,
        log_externo_id=marcacao.log_externo_id,
    )


async def travar_idempotency_key(
    sessao: AsyncSession, *, tenant_id: UUID, idempotency_key: str
) -> bool:
    """Tenta um lock consultivo escopado a transacao sobre
    `tenant_id + escopo + Idempotency-Key`. `True` quando obteve o lock (nenhuma
    outra transacao concorrente segura o mesmo par agora); `False` quando outra
    requisicao com a MESMA chave esta em voo neste instante -- o chamador deve
    responder `PONTO-IDEM-003` sem tocar o banco. Libera sozinho no commit ou
    no rollback da transacao corrente (`obter_sessao` sempre faz um dos dois),
    nunca precisa de unlock explicito."""
    chave_txt = f"{tenant_id}:{ESCOPO_IDEMPOTENCY_KEY}:{idempotency_key}"
    resultado = await sessao.execute(
        sa.text("SELECT pg_try_advisory_xact_lock(hashtextextended(:chave, 0))"),
        {"chave": chave_txt},
    )
    return bool(resultado.scalar_one())


async def buscar_marcacao_por_chave(
    sessao: AsyncSession, *, tenant_id: UUID, escopo: str, chave: str
) -> Marcacao | None:
    """Devolve a `Marcacao` ja registrada para `(escopo, chave)`, ou `None`."""
    consulta = (
        sa.select(Marcacao)
        .join(
            MarcacaoIdempotencia,
            sa.and_(
                MarcacaoIdempotencia.marcacao_id == Marcacao.id,
                MarcacaoIdempotencia.datahora_marcacao == Marcacao.datahora_marcacao,
            ),
        )
        .where(
            MarcacaoIdempotencia.tenant_id == tenant_id,
            MarcacaoIdempotencia.escopo == escopo,
            MarcacaoIdempotencia.chave == chave,
        )
    )
    resultado = await sessao.execute(consulta)
    return resultado.scalar_one_or_none()


async def registrar_chave(
    sessao: AsyncSession,
    *,
    tenant_id: UUID,
    escopo: str,
    chave: str,
    marcacao_id: UUID,
    datahora_marcacao: Any,
    usuario_id: UUID | None = None,
    codigo_conflito: str = "PONTO-MARC-003",
) -> None:
    """Insere a linha de idempotencia na MESMA transacao da marcacao.

    Uma violacao de `uq_marcacao_idempotencia` aqui so pode acontecer por uma
    corrida dentro desta mesma transacao (o chamador ja checou a chave antes
    de persistir); ainda assim traduzimos para o codigo do catalogo em vez de
    deixar vazar `IntegrityError` como 500. `codigo_conflito` e
    `PONTO-MARC-003` (colisao de chave de dominio) por padrao; o chamador pode
    trocar quando a chave for `idempotency_key` (nesse caso o lock consultivo
    ja deveria ter prevenido a corrida -- ver `travar_idempotency_key`)."""
    sessao.add(
        MarcacaoIdempotencia(
            tenant_id=tenant_id,
            escopo=escopo,
            chave=chave,
            marcacao_id=marcacao_id,
            datahora_marcacao=datahora_marcacao,
            criado_por=usuario_id,
        )
    )
    try:
        await sessao.flush()
    except IntegrityError as exc:
        nome = getattr(exc.orig, "constraint_name", None) or str(exc.orig or exc)
        if _CONSTRAINT_IDEMPOTENCIA not in str(nome):
            raise
        raise ErroDeAplicacao(
            codigo_conflito, contexto_log={"escopo": escopo, "constraint": str(nome)}
        ) from exc
