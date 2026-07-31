"""Exportador PDF, tabular generico (F11, T5/A3).

**Nao e o mesmo modulo nem o mesmo layout do espelho de ponto oficial**
(`app.workflow.fechamento.pdf::gerar_pdf_espelho`, ownership de A4, T12) --
aqui e um relatorio tabular generico, reaproveitado pelos 23 relatorios
restantes do catalogo que declaram `pdf` em `formatos` (PCF §6/T5: "nao e o
mesmo modulo nem o mesmo layout do espelho, e um relatorio tabular
generico").

Biblioteca: `reportlab` (ja dependencia da API desde a F10, nenhuma nova).
Usa `reportlab.pdfgen.canvas.Canvas` diretamente (nao `platypus.Table`, que
exige a matriz de dados inteira em memoria para calcular larguras de coluna
antes de desenhar) -- cada linha e desenhada e descartada conforme chega do
iteravel `linhas`, trocando de pagina quando a proxima linha nao cabe mais
(mesmo espirito de streaming do PCF §2.3 item 2, agora tambem em PDF, nao so
em XLSX).

**Extensao aditiva ao contrato do §4:** a assinatura fixada pelo PCF e
`exportar(linhas, colunas, *, destino) -> None`; este modulo aceita, alem
disso, `titulo`/`subtitulo` opcionais (cabecalho com nome do relatorio e
periodo/filtros aplicados, exigido pelo "pronto quando" de T5) -- mantendo
compatibilidade total com quem chama so com os tres parametros do contrato
base (`titulo`/`subtitulo` tem padrao e nunca sao obrigatorios).
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable, Mapping, Sequence
from typing import Any, BinaryIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.pdfgen.canvas import Canvas

from app.relatorios.exportadores import ColunaExportacao, cabecalhos, valor_formatado

_MARGEM = 1.6 * cm
_ALTURA_LINHA = 0.5 * cm
_FONTE_CABECALHO = "Helvetica-Bold"
_FONTE_LINHA = "Courier"
_TAMANHO_FONTE = 7.5
_COR_CABECALHO_FUNDO = colors.HexColor("#4C5FCA")
_COR_CABECALHO_TEXTO = colors.white
_COR_ZEBRA = colors.HexColor("#EFF2F6")
_COR_TEXTO = colors.HexColor("#262B31")


def _largura_colunas(quantidade: int, largura_util: float) -> float:
    """Largura igual para cada coluna -- relatorio generico, sem
    conhecimento do conteudo de cada coluna para pesar larguras diferentes
    (o layout de designer do espelho oficial e privilegio de A4/T12, nao
    deste exportador generico)."""
    return largura_util / max(quantidade, 1)


def exportar(
    linhas: Iterable[Mapping[str, Any]],
    colunas: Sequence[ColunaExportacao],
    *,
    destino: BinaryIO,
    converter_decimal: bool = False,
    casas_decimais: int = 2,
    titulo: str = "Relatorio",
    subtitulo: str | None = None,
) -> None:
    """Escreve `linhas` como uma tabela PDF paginada em `destino`, uma linha
    por vez -- nunca materializa a matriz de dados inteira em memoria (PCF
    §2.3 item 2). `destino` permanece aberto ao final."""
    largura_pagina, altura_pagina = A4
    largura_util = largura_pagina - 2 * _MARGEM
    largura_coluna = _largura_colunas(len(colunas), largura_util)
    gerado_em = dt.datetime.now(tz=dt.UTC).strftime("%d/%m/%Y %H:%M UTC")

    canvas_ = Canvas(destino, pagesize=A4)
    pagina = 1

    def _cabecalho_pagina() -> float:
        """Desenha titulo/subtitulo (so na primeira pagina) e o cabecalho da
        tabela em toda pagina. Devolve o `y` onde a primeira linha de dado
        comeca."""
        y = altura_pagina - _MARGEM
        if pagina == 1:
            canvas_.setFont(_FONTE_CABECALHO, 13)
            canvas_.setFillColor(_COR_TEXTO)
            canvas_.drawString(_MARGEM, y, titulo)
            y -= 0.55 * cm
            if subtitulo:
                canvas_.setFont("Helvetica", 9)
                canvas_.drawString(_MARGEM, y, subtitulo)
                y -= 0.55 * cm
            y -= 0.15 * cm
        canvas_.setFillColor(_COR_CABECALHO_FUNDO)
        canvas_.rect(_MARGEM, y - _ALTURA_LINHA, largura_util, _ALTURA_LINHA, fill=1, stroke=0)
        canvas_.setFillColor(_COR_CABECALHO_TEXTO)
        canvas_.setFont(_FONTE_CABECALHO, _TAMANHO_FONTE)
        for indice_coluna, rotulo in enumerate(cabecalhos(colunas)):
            canvas_.drawString(
                _MARGEM + indice_coluna * largura_coluna + 0.1 * cm,
                y - _ALTURA_LINHA + 0.14 * cm,
                rotulo[:40],
            )
        return float(y - _ALTURA_LINHA)

    def _rodape() -> None:
        canvas_.setFont("Helvetica", 7)
        canvas_.setFillColor(colors.HexColor("#838D9A"))
        canvas_.drawString(_MARGEM, _MARGEM - 0.4 * cm, f"Gerado em {gerado_em}")
        canvas_.drawRightString(largura_pagina - _MARGEM, _MARGEM - 0.4 * cm, f"Pagina {pagina}")

    y = _cabecalho_pagina()
    for indice_linha, linha in enumerate(linhas):
        if y - _ALTURA_LINHA < _MARGEM + 0.6 * cm:
            _rodape()
            canvas_.showPage()
            pagina += 1
            y = _cabecalho_pagina()

        if indice_linha % 2 == 1:
            canvas_.setFillColor(_COR_ZEBRA)
            canvas_.rect(_MARGEM, y - _ALTURA_LINHA, largura_util, _ALTURA_LINHA, fill=1, stroke=0)

        canvas_.setFillColor(_COR_TEXTO)
        canvas_.setFont(_FONTE_LINHA, _TAMANHO_FONTE)
        for indice_coluna, coluna in enumerate(colunas):
            valor = valor_formatado(
                linha,
                coluna,
                converter_decimal=converter_decimal,
                casas_decimais=casas_decimais,
            )
            canvas_.drawString(
                _MARGEM + indice_coluna * largura_coluna + 0.1 * cm,
                y - _ALTURA_LINHA + 0.14 * cm,
                str("" if valor is None else valor)[:40],
            )
        y -= _ALTURA_LINHA

    _rodape()
    canvas_.save()


__all__ = ["exportar"]
