"""Paginacao por cursor, copia dedicada da fase de marcacao.

Copia deliberada do padrao de `app.pessoas.paginacao` (F2): mesmo algoritmo de
cursor opaco (campo de ordenacao, direcao, valor da ultima linha e `id` como
desempate), mesmos codigos de erro. Nao importamos o modulo da F2 porque ele e
propriedade daquela fase (ver `docs/fases/F05-ingestao-marcacoes-nsr.md`, T10:
"crie a sua propria copia... nao importe o modulo de outra fase").

O cursor e um token opaco em base64url que carrega o campo de ordenacao, a
direcao e o valor da ultima linha vista da pagina anterior, mais o `id` da
linha como desempate -- nenhum dos campos ordenaveis do contrato (`nsr`,
`datahoraMarcacao`, `emitidoEm`) e garantidamente unico sozinho. Trocar
`ordenar` mantendo um cursor emitido para outra ordenacao e `PONTO-VAL-006`;
campo de ordenacao fora da lista aceita pela operacao e `PONTO-VAL-005`.
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
    """Campo e direcao efetivamente aplicados a uma listagem."""

    campo: str
    direcao: str  # "asc" ou "desc"


def normalizar_limite(limite: int | None) -> int:
    """Aplica o padrao (50) e valida a faixa aceita (1..200) do contrato."""
    if limite is None:
        return LIMITE_PADRAO
    if not (1 <= limite <= LIMITE_MAXIMO):
        raise ErroDeAplicacao(
            CODIGO_CONSULTA_INVALIDA,
            detalhe=f"limite deve estar entre 1 e {LIMITE_MAXIMO}.",
        )
    return limite


def interpretar_ordenar(
    ordenar: str | None, *, campos_aceitos: frozenset[str], padrao: str
) -> Ordenacao:
    """Le o primeiro criterio de `campo:direcao` do parametro `ordenar`.

    So o primeiro criterio de uma lista separada por virgula e aplicado: os
    recursos desta fase nao tem indice composto para ordenacao multipla, e
    fingir suporte a ela produziria uma pagina inconsistente.
    """
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
    """Emite o cursor opaco da proxima pagina."""
    payload = {
        "o": ordenacao.campo,
        "d": ordenacao.direcao,
        "v": _serializar(valor),
        "id": str(id_),
    }
    bruto = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(bruto).decode("ascii").rstrip("=")


def decodificar_cursor(cursor: str, *, ordenacao: Ordenacao) -> tuple[Any, UUID]:
    """Decodifica o cursor e confere que foi emitido para a mesma ordenacao.

    Devolve `(valor_bruto, id_desempate)`; o chamador converte `valor_bruto`
    (sempre `str`, `int`, `float`, `bool` ou `None` -- o que sobrevive ao
    JSON) para o tipo Python da coluna ordenada.
    """
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
    """Um campo aceito em `ordenar`: a coluna mapeada e o conversor que
    traz o valor bruto do cursor (sempre `str`/`int`/`float`/`bool`/`None`,
    o que sobrevive ao JSON) de volta ao tipo Python da coluna."""

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
    """Aplica ordenacao (coluna, `id` como desempate), o filtro do cursor
    (keyset, nao `OFFSET`) e o limite (pedindo uma linha a mais, para saber
    `temMais` sem outra consulta).

    Devolve `(linhas_da_pagina, tem_mais)`.
    """
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
    """Constroi o schema `Paginacao` da resposta.

    Fabrica dedicada por causa do alias de campo: `Paginacao` e gerado do
    contrato com `temMais`/`proximoCursor` como alias Pydantic, e o
    verificador de tipos so reconhece o nome do alias na chamada do
    construtor (mesmo com `populate_by_name=True`, que so afeta a validacao
    em tempo de execucao).
    """
    return PaginacaoResposta(
        proximoCursor=proximo_cursor,
        cursorAnterior=None,
        temMais=tem_mais,
        limite=limite,
        totalEstimado=None,
    )
