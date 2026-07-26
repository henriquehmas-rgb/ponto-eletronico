"""Paginacao por cursor dos endpoints de listagem desta fase.

Implementacao por deslocamento (*offset*), no cursor -- nao por *keyset* -- de
proposito: e a forma mais simples de aplicar de modo uniforme aos sete
recursos de listagem da fase (empresas, unidades, redes permitidas,
departamentos, centros de custo, cargos, equipes), ao custo teorico de pular
ou repetir um item se houver escrita concorrente entre duas paginas -- risco
aceitavel neste tipo de cadastro, de baixa taxa de escrita, e fora do escopo
de desempenho desta fase.

O cursor e opaco (base64 de um JSON) e carrega a ordenacao pedida: pedir a
proxima pagina com um `ordenar` diferente do que o cursor carrega e recusado
com `PONTO-VAL-006` (cursor incompativel com a ordenacao), exatamente como o
contrato descreve em `Paginacao`.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import TypeVar

from app.core.erros import ErroDeAplicacao

_T = TypeVar("_T")

LIMITE_PADRAO = 20
LIMITE_MAXIMO = 100


@dataclass(frozen=True, slots=True)
class PedidoDePagina:
    ordenar: str
    limite: int
    deslocamento: int


def _normalizar_limite(limite: int | None) -> int:
    if limite is None:
        return LIMITE_PADRAO
    if limite < 1:
        raise ErroDeAplicacao("PONTO-VAL-005", detalhe="limite deve ser maior que zero.")
    return min(limite, LIMITE_MAXIMO)


def resolver_pedido(
    *,
    cursor: str | None,
    limite: int | None,
    ordenar: str | None,
    ordenacao_padrao: str,
) -> PedidoDePagina:
    """Decodifica `cursor` (quando presente) e resolve o pedido de pagina.

    `ordenacao_padrao` e o valor usado quando o cliente nao informa
    `ordenar`, no formato `campo:direcao` (ex.: `criado_em:desc`).
    """
    ordenar_pedido = ordenar or ordenacao_padrao
    limite_resolvido = _normalizar_limite(limite)
    if cursor is None:
        return PedidoDePagina(ordenar=ordenar_pedido, limite=limite_resolvido, deslocamento=0)

    try:
        preenchido = cursor + "=" * (-len(cursor) % 4)
        dados = json.loads(base64.urlsafe_b64decode(preenchido.encode("ascii")))
        ordenar_cursor = str(dados["o"])
        deslocamento = int(dados["d"])
    except Exception as exc:
        raise ErroDeAplicacao("PONTO-VAL-006", detalhe="Cursor ilegivel.") from exc

    if ordenar_cursor != ordenar_pedido:
        raise ErroDeAplicacao(
            "PONTO-VAL-006",
            detalhe="Cursor incompativel com a ordenacao pedida: volte a primeira pagina.",
        )
    if deslocamento < 0:
        raise ErroDeAplicacao("PONTO-VAL-006", detalhe="Cursor ilegivel.")
    return PedidoDePagina(
        ordenar=ordenar_pedido, limite=limite_resolvido, deslocamento=deslocamento
    )


def campo_e_direcao(ordenar: str) -> tuple[str, str]:
    """Separa `campo:direcao`. Direcao ausente vira `asc`."""
    campo, _, direcao = ordenar.partition(":")
    direcao = (direcao or "asc").lower()
    if direcao not in ("asc", "desc"):
        raise ErroDeAplicacao(
            "PONTO-VAL-005", detalhe=f"Direcao de ordenacao invalida: {direcao!r}"
        )
    return campo, direcao


def codificar_cursor(*, ordenar: str, deslocamento: int) -> str:
    bruto = json.dumps({"o": ordenar, "d": deslocamento})
    return base64.urlsafe_b64encode(bruto.encode("ascii")).decode("ascii").rstrip("=")


def montar_paginacao(*, pedido: PedidoDePagina, quantidade_lida: int) -> dict[str, object]:
    """Monta o dicionario do schema `Paginacao` a partir do que foi lido.

    `quantidade_lida` e o numero de linhas devolvidas pela consulta, que pede
    sempre `limite + 1` para descobrir `temMais` sem um `SELECT COUNT(*)`
    separado.
    """
    tem_mais = quantidade_lida > pedido.limite
    paginacao: dict[str, object] = {
        "temMais": tem_mais,
        "limite": pedido.limite,
    }
    if tem_mais:
        paginacao["proximoCursor"] = codificar_cursor(
            ordenar=pedido.ordenar, deslocamento=pedido.deslocamento + pedido.limite
        )
    if pedido.deslocamento > 0:
        paginacao["cursorAnterior"] = codificar_cursor(
            ordenar=pedido.ordenar,
            deslocamento=max(pedido.deslocamento - pedido.limite, 0),
        )
    return paginacao


def paginar(*, pedido: PedidoDePagina, linhas: list[_T]) -> tuple[list[_T], dict[str, object]]:
    """Corta `linhas` (que chegam com `limite + 1` itens, ver `crud_base.listar`)
    de volta ao tamanho de pagina pedido e monta o dicionario de `Paginacao` --
    par usado por todo router desta fase para montar o schema `ListaX`."""
    return linhas[: pedido.limite], montar_paginacao(pedido=pedido, quantidade_lida=len(linhas))
