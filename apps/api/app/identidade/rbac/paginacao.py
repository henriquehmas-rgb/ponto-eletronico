"""Paginacao por cursor opaco, compartilhada pelos `listar*` desta fase.

O cursor codifica `(criado_em, id)` da ultima linha da pagina anterior, em
base64 de um JSON compacto. Nao ha suporte a ordenacao alternativa
(`ordenar=`) nesta fase -- a ordem e sempre `criado_em, id` ascendente, que e
o suficiente para o `listarUsuarios`/`listarPerfis`/`listarPermissoes`/
`listarApiClients`/`listarAuditoria` desta fase. Uma fase futura que precise
de outro criterio de ordenacao estende este helper.
"""

from __future__ import annotations

import base64
import datetime as _dt
import json
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

LIMITE_PADRAO = 20
LIMITE_MAXIMO = 100


def _codificar(criado_em: _dt.datetime, id_: UUID) -> str:
    bruto = json.dumps([criado_em.isoformat(), str(id_)]).encode("utf-8")
    return base64.urlsafe_b64encode(bruto).decode("ascii")


def _decodificar(cursor: str) -> tuple[_dt.datetime, UUID]:
    bruto = base64.urlsafe_b64decode(cursor.encode("ascii"))
    criado_em_iso, id_str = json.loads(bruto)
    return _dt.datetime.fromisoformat(criado_em_iso), UUID(id_str)


def normalizar_limite(limite: int | None) -> int:
    if limite is None or limite <= 0:
        return LIMITE_PADRAO
    return min(limite, LIMITE_MAXIMO)


async def paginar(
    sessao: AsyncSession,
    consulta_base: sa.Select[Any],
    *,
    coluna_criado_em: Any,
    coluna_id: Any,
    cursor: str | None,
    limite: int | None,
) -> tuple[list[Any], dict[str, Any]]:
    """Aplica cursor + limite a `consulta_base` e devolve `(linhas, paginacao)`.

    `paginacao` ja sai no formato de `contrato.Paginacao` (chaves em
    `snake_case`, que o pydantic aceita via `populate_by_name`).
    """
    limite_efetivo = normalizar_limite(limite)
    consulta = consulta_base.order_by(coluna_criado_em.asc(), coluna_id.asc())

    if cursor:
        criado_em_cursor, id_cursor = _decodificar(cursor)
        consulta = consulta.where(
            sa.tuple_(coluna_criado_em, coluna_id) > (criado_em_cursor, id_cursor)
        )

    linhas = list((await sessao.scalars(consulta.limit(limite_efetivo + 1))).all())
    tem_mais = len(linhas) > limite_efetivo
    linhas = linhas[:limite_efetivo]

    proximo_cursor = None
    if tem_mais and linhas:
        ultima = linhas[-1]
        proximo_cursor = _codificar(ultima.criado_em, ultima.id)

    paginacao = {
        "proximo_cursor": proximo_cursor,
        "cursor_anterior": None,
        "tem_mais": tem_mais,
        "limite": limite_efetivo,
    }
    return linhas, paginacao
