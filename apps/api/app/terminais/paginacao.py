"""Paginacao por cursor, self-contained para o dominio `terminais` (mesmo
padrao de `app/pessoas/paginacao.py`, `app/organizacao/paginacao.py` -- cada
dominio guarda a propria copia para nao acoplar a modulo de outro agente/fase,
ver `app/biometria/comum.py`)."""

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
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.core.erros import ErroDeAplicacao
from app.schemas.contrato import Paginacao as PaginacaoResposta

CODIGO_CURSOR_INCOMPATIVEL = "PONTO-VAL-006"
CODIGO_CONSULTA_INVALIDA = "PONTO-VAL-005"

LIMITE_PADRAO = 50
LIMITE_MAXIMO = 200


@dataclass(frozen=True, slots=True)
class Ordenacao:
    campo: str
    direcao: str


def normalizar_limite(limite: int | None) -> int:
    if limite is None:
        return LIMITE_PADRAO
    if not (1 <= limite <= LIMITE_MAXIMO):
        raise ErroDeAplicacao(
            CODIGO_CONSULTA_INVALIDA, detalhe=f"limite deve estar entre 1 e {LIMITE_MAXIMO}."
        )
    return limite


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
            CODIGO_CONSULTA_INVALIDA, detalhe=f"Direcao de ordenacao invalida: {direcao_bruta!r}."
        )
    if campo not in campos_aceitos:
        raise ErroDeAplicacao(
            CODIGO_CONSULTA_INVALIDA, detalhe=f"Campo de ordenacao invalido: {campo!r}."
        )
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


def decodificar_cursor(cursor: str, *, ordenacao: Ordenacao) -> tuple[Any, UUID]:
    try:
        preenchido = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(preenchido.encode("ascii")))
    except (binascii.Error, ValueError, UnicodeDecodeError) as exc:
        raise ErroDeAplicacao(CODIGO_CURSOR_INCOMPATIVEL, detalhe="Cursor ilegivel.") from exc
    if (
        not isinstance(payload, dict)
        or payload.get("o") != ordenacao.campo
        or payload.get("d") != ordenacao.direcao
    ):
        raise ErroDeAplicacao(
            CODIGO_CURSOR_INCOMPATIVEL,
            detalhe="O cursor foi emitido para outro campo ou outra direcao de ordenacao.",
        )
    try:
        id_ = UUID(str(payload["id"]))
    except (KeyError, ValueError) as exc:
        raise ErroDeAplicacao(
            CODIGO_CURSOR_INCOMPATIVEL, detalhe="Cursor sem identificador de desempate."
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
    desc = ordenacao.direcao == "desc"
    consulta = consulta.order_by(
        campo.coluna.desc() if desc else campo.coluna.asc(),
        coluna_id.desc() if desc else coluna_id.asc(),
    )
    if cursor:
        valor_bruto, id_cursor = decodificar_cursor(cursor, ordenacao=ordenacao)
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


def montar_paginacao(
    *, proximo_cursor: str | None, tem_mais: bool, limite: int
) -> PaginacaoResposta:
    return PaginacaoResposta(
        proximoCursor=proximo_cursor,
        cursorAnterior=None,
        temMais=tem_mais,
        limite=limite,
        totalEstimado=None,
    )
