"""Alocacao transacional de NSR, CRC-16 e hash encadeado (ADR-003).

CONTRATO ENTRE MODULOS desta fase: `app.marcacao.dominio.registro` (T3) e
`app.marcacao.dominio.verificacao_nsr` (T4) importam daqui e **precisam
concordar** sobre a formula de canonicalizacao -- ela e fixada e documentada
neste modulo porque os dois lados (quem grava e quem verifica) tem que usar
exatamente a mesma. Mudar `_SEPARADOR`, a lista de campos ou a normalizacao de
qualquer um deles invalidaria toda cadeia de hash ja gravada; se algum dia for
preciso mudar, e RFC, nunca ajuste silencioso.

**NSR nao usa `SEQUENCE` do PostgreSQL.** `SEQUENCE`/`SERIAL`/`GENERATED AS
IDENTITY` nao sao transacionais -- nao voltam atras em `ROLLBACK` -- e uma
transacao abortada deixaria lacuna permanente, que a Portaria MTP 671/2021
proibe. Em vez disso, `alocar_nsr` faz um `UPDATE ... RETURNING` na linha de
`nsr_sequencias` do REP-P, **na mesma transacao** que grava a marcacao: o
bloqueio de linha que o `UPDATE` toma serializa apenas os concorrentes daquele
REP-P (nunca entre REP-Ps distintos), e commit publica os dois, rollback
desfaz os dois -- lacuna vira impossivel por construcao (ADR-003).
"""

from __future__ import annotations

import datetime as dt
import hashlib
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.erros import ErroDeAplicacao

#: Separador ASCII "Unit Separator" (0x1F): nunca aparece em CPF, canal, tipo
#: de registro nem em ISO 8601, o que evita qualquer ambiguidade de
#: concatenacao (diferente de um separador visivel como "|", que em teoria
#: poderia colidir com um campo textual futuro).
_SEPARADOR = "\x1f"


@dataclass(frozen=True, slots=True)
class NsrAlocado:
    """Resultado de `alocar_nsr`: o NSR concedido e o elo anterior da cadeia."""

    nsr: int
    hash_anterior: str | None


async def alocar_nsr(sessao: AsyncSession, *, tenant_id: UUID, rep_p_id: UUID) -> NsrAlocado:
    """Aloca o proximo NSR do REP-P dentro da transacao corrente (ADR-003).

    `UPDATE nsr_sequencias SET proximo_nsr = proximo_nsr + 1, ... RETURNING
    proximo_nsr - 1 AS nsr, ultimo_hash AS hash_anterior`: o `RETURNING`
    calcula sobre a linha JA atualizada pelo proprio `UPDATE` -- por isso
    subtraimos 1 para recuperar o valor alocado -- e `ultimo_hash` ainda nao
    foi tocado por este comando (so `fechar_nsr` o atualiza, depois que o
    hash do registro corrente for calculado), portanto e o elo anterior
    correto da cadeia.

    Nao ha linha em `nsr_sequencias` para o REP-P (nunca deveria acontecer:
    o cadastro do REP-P, feito pela F12, e quem a cria) ou falha de banco:
    `PONTO-MARC-008`, retentavel com a MESMA `Idempotency-Key`.
    """
    resultado = await sessao.execute(
        text(
            "UPDATE nsr_sequencias "
            "SET proximo_nsr = proximo_nsr + 1, "
            "    ultimo_nsr_emitido = proximo_nsr, "
            "    ultima_emissao_em = now() "
            "WHERE tenant_id = :tenant_id AND rep_p_id = :rep_p_id "
            "RETURNING proximo_nsr - 1 AS nsr, ultimo_hash AS hash_anterior"
        ),
        {"tenant_id": str(tenant_id), "rep_p_id": str(rep_p_id)},
    )
    linha = resultado.first()
    if linha is None:
        raise ErroDeAplicacao(
            "PONTO-MARC-008",
            contexto_log={"tenant_id": str(tenant_id), "rep_p_id": str(rep_p_id)},
        )
    return NsrAlocado(nsr=linha.nsr, hash_anterior=linha.hash_anterior)


async def fechar_nsr(
    sessao: AsyncSession, *, tenant_id: UUID, rep_p_id: UUID, hash_registro: str
) -> None:
    """Fecha a cadeia: grava `hash_registro` como `ultimo_hash` de
    `nsr_sequencias`, o elo que a PROXIMA alocacao do mesmo REP-P vai ler como
    `hash_anterior`. Chamado por `registro.persistir_marcacao` apos o `INSERT`
    em `marcacoes`, ainda na mesma transacao."""
    await sessao.execute(
        text(
            "UPDATE nsr_sequencias SET ultimo_hash = :hash_registro "
            "WHERE tenant_id = :tenant_id AND rep_p_id = :rep_p_id"
        ),
        {
            "tenant_id": str(tenant_id),
            "rep_p_id": str(rep_p_id),
            "hash_registro": hash_registro,
        },
    )


def crc16(dados: bytes) -> int:
    """CRC-16/ARC: polinomio reverso `0x A001` (equivalente ao polinomio
    normal `0x8005`), registrador inicial `0x0000`, reflexao de entrada e
    saida (a variante mais comum de "CRC-16" em leiautes fiscais brasileiros).

    Documentado aqui, nao certificado: a conformidade byte a byte com o
    validador oficial do leiaute do AFD e conferida pela F12 (`docs/fases`,
    F05, secao 2). A exigencia desta fase e "calculado e congelado de forma
    estavel" -- a mesma entrada sempre produz a mesma saida, para sempre.
    """
    crc = 0x0000
    for byte in dados:
        crc ^= byte
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc & 0xFFFF


def canonicalizar_registro(
    *,
    tenant_id: UUID,
    rep_p_id: UUID,
    nsr: int,
    cpf: str,
    tipo_registro: str,
    canal: str,
    datahora_marcacao: dt.datetime,
) -> str:
    """Monta a string canonica que entra em `calcular_hash`.

    FORMULA FIXA (mudar qualquer item abaixo exige RFC, porque quebraria a
    verificacao de toda cadeia ja gravada):

    1. Campos, NESTA ordem: ``tenant_id``, ``rep_p_id``, ``nsr``, ``cpf``,
       ``tipo_registro``, ``canal``, ``datahora_marcacao``.
    2. Cada campo e normalizado antes de entrar: ``tenant_id``/``rep_p_id``
       como `str(UUID)` (minusculo, com hifens); ``nsr`` como `str(int)`
       decimal; ``cpf``/``tipo_registro``/``canal`` exatamente como
       armazenados (ja normalizados pelo dominio: 11 digitos, sem pontuacao,
       para o CPF); ``datahora_marcacao`` convertido para UTC e serializado em
       ISO 8601 com microssegundos e sufixo ``Z`` (nunca ``+00:00``, para o
       verificador nao depender da forma como o driver serializa o offset).
    3. Os campos sao concatenados com o separador `_SEPARADOR` (0x1F) entre
       cada par.

    O verificador (`app.marcacao.dominio.verificacao_nsr`) reconstroi esta
    mesma string a partir dos valores persistidos (join com `marcacoes`) e
    recalcula `calcular_hash` para provar que o conteudo nao mudou.
    """
    instante_utc = datahora_marcacao.astimezone(dt.UTC)
    instante_iso = instante_utc.isoformat(timespec="microseconds").replace("+00:00", "Z")
    campos = (
        str(tenant_id),
        str(rep_p_id),
        str(nsr),
        cpf,
        tipo_registro,
        canal,
        instante_iso,
    )
    return _SEPARADOR.join(campos)


def calcular_hash(dados_canonicos: str, hash_anterior: str | None) -> str:
    """SHA-256 hexadecimal (minusculo, 64 caracteres, formato `dom_sha256`) de
    ``(hash_anterior ou "") + _SEPARADOR + dados_canonicos``.

    Encadear o hash anterior ANTES dos dados canonicos (em vez de depois) e
    deliberado: torna a cadeia sensivel a qualquer alteracao retroativa --
    trocar um hash no meio da cadeia muda a entrada de todo elo seguinte, o
    que e exatamente a propriedade que torna a remocao ou adulteracao
    silenciosa de um registro detectavel (glossario, "Hash chain").
    """
    base = f"{hash_anterior or ''}{_SEPARADOR}{dados_canonicos}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()
