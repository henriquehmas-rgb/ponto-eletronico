"""Utilitarios compartilhados pelos modulos de `app.lgpd` (F14/A3).

Paginacao por cursor e traducao de `IntegrityError`, self-contained pelo
mesmo motivo que `app/biometria/comum.py` documenta: nao acoplar a modulos
de outro agente da mesma fase. Copia deliberada do mesmo padrao (nao
compartilhada via `app/comum/`, que e territorio de A2 nesta fase).
"""

from __future__ import annotations

import base64
import binascii
import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import Select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.core.erros import ErroDeAplicacao

__all__ = [
    "CampoOrdenacao",
    "Ordenacao",
    "codificar_cursor",
    "executar_pagina",
    "interpretar_ordenar",
    "normalizar_limite",
    "traduzir_integridade",
]

LIMITE_PADRAO = 50
LIMITE_MAXIMO = 200

#: Nome de constraint -> codigo do catalogo. So as constraints que as
#: tabelas desta fase (consentimentos, solicitacoes_titular) podem violar.
_CODIGOS_POR_CONSTRAINT: dict[str, str] = {
    "uq_consentimentos_vigente": "PONTO-CONF-001",
    "uq_solicitacoes_titular_protocolo": "PONTO-CONF-001",
}


def traduzir_integridade(exc: IntegrityError, *, padrao: str = "PONTO-CONF-001") -> ErroDeAplicacao:
    """Converte `IntegrityError` no `ErroDeAplicacao` do codigo correspondente."""
    origem = exc.orig or exc
    nome = getattr(origem, "constraint_name", None)
    if not nome:
        texto = str(origem)
        nome = next((c for c in _CODIGOS_POR_CONSTRAINT if c in texto), None)
    codigo = _CODIGOS_POR_CONSTRAINT.get(nome or "", padrao)
    return ErroDeAplicacao(codigo, contexto_log={"constraint": nome})


def normalizar_limite(limite: int | None) -> int:
    if limite is None:
        return LIMITE_PADRAO
    if not (1 <= limite <= LIMITE_MAXIMO):
        raise ErroDeAplicacao(
            "PONTO-VAL-005", detalhe=f"limite deve estar entre 1 e {LIMITE_MAXIMO}."
        )
    return limite


@dataclass(frozen=True, slots=True)
class Ordenacao:
    campo: str
    direcao: str


def interpretar_ordenar(
    ordenar: str | None, *, campos_aceitos: frozenset[str], padrao: str
) -> Ordenacao:
    if not ordenar:
        return Ordenacao(campo=padrao, direcao="desc")
    primeiro = ordenar.split(",")[0].strip()
    campo, _, direcao_bruta = primeiro.partition(":")
    direcao = (direcao_bruta or "asc").strip().lower()
    if direcao not in ("asc", "desc"):
        raise ErroDeAplicacao(
            "PONTO-VAL-005", detalhe=f"Direcao de ordenacao invalida: {direcao_bruta!r}."
        )
    if campo not in campos_aceitos:
        raise ErroDeAplicacao("PONTO-VAL-005", detalhe=f"Campo de ordenacao invalido: {campo!r}.")
    return Ordenacao(campo=campo, direcao=direcao)


def _serializar(valor: Any) -> Any:
    if isinstance(valor, datetime | date):
        return valor.isoformat()
    if isinstance(valor, UUID):
        return str(valor)
    return valor


def codificar_cursor(ordenacao: Ordenacao, valor: Any, id_: Any) -> str:
    payload = {
        "o": ordenacao.campo,
        "d": ordenacao.direcao,
        "v": _serializar(valor),
        "id": str(id_),
    }
    bruto = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(bruto).decode("ascii").rstrip("=")


def _decodificar_cursor(cursor: str, *, ordenacao: Ordenacao) -> tuple[Any, UUID]:
    try:
        preenchido = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(preenchido.encode("ascii")))
    except (binascii.Error, ValueError, UnicodeDecodeError) as exc:
        raise ErroDeAplicacao("PONTO-VAL-006", detalhe="Cursor ilegivel.") from exc
    if (
        not isinstance(payload, dict)
        or payload.get("o") != ordenacao.campo
        or payload.get("d") != ordenacao.direcao
    ):
        raise ErroDeAplicacao(
            "PONTO-VAL-006",
            detalhe="O cursor foi emitido para outro campo ou outra direcao de ordenacao.",
        )
    try:
        id_ = UUID(str(payload["id"]))
    except (KeyError, ValueError) as exc:
        raise ErroDeAplicacao(
            "PONTO-VAL-006", detalhe="Cursor sem identificador de desempate."
        ) from exc
    return payload.get("v"), id_


@dataclass(frozen=True, slots=True)
class CampoOrdenacao:
    coluna: InstrumentedAttribute[Any]
    conversor: Callable[[Any], Any]


async def executar_pagina(
    sessao: AsyncSession,
    consulta: Select[Any],
    *,
    ordenacao: Ordenacao,
    campo: CampoOrdenacao,
    coluna_id: InstrumentedAttribute[Any],
    cursor: str | None,
    limite: int,
) -> tuple[Sequence[Any], bool]:
    """Paginacao por keyset (coluna ordenada + `id` como desempate)."""
    desc = ordenacao.direcao == "desc"
    consulta = consulta.order_by(
        campo.coluna.desc() if desc else campo.coluna.asc(),
        coluna_id.desc() if desc else coluna_id.asc(),
    )
    if cursor:
        valor_bruto, id_cursor = _decodificar_cursor(cursor, ordenacao=ordenacao)
        valor = campo.conversor(valor_bruto) if valor_bruto is not None else None
        tupla_pagina = sa.tuple_(campo.coluna, coluna_id)
        tupla_cursor = sa.tuple_(sa.literal(valor), sa.literal(id_cursor))
        condicao = tupla_pagina < tupla_cursor if desc else tupla_pagina > tupla_cursor
        consulta = consulta.where(condicao)
    consulta = consulta.limit(limite + 1)
    resultado = await sessao.execute(consulta)
    linhas = list(resultado.scalars().all())
    tem_mais = len(linhas) > limite
    return linhas[:limite], tem_mais
