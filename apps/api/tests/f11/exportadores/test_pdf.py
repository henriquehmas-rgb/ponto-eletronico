"""`app.relatorios.exportadores.pdf` (F11, T5/A3)."""

from __future__ import annotations

import io
from collections.abc import Iterator
from typing import Any

from pypdf import PdfReader

from app.relatorios.exportadores import ColunaExportacao
from app.relatorios.exportadores import pdf as exportador_pdf

_COLUNAS = [
    ColunaExportacao(chave="nome", rotulo="Nome"),
    ColunaExportacao(chave="minutos", rotulo="Horas", duracao=True),
]


def _linhas() -> list[dict[str, Any]]:
    return [
        {"nome": "Jose Silva", "minutos": 150},
        {"nome": "Ana Souza", "minutos": 90},
    ]


def _texto_do_pdf(bruto: bytes) -> str:
    leitor = PdfReader(io.BytesIO(bruto))
    return "\n".join(pagina.extract_text() or "" for pagina in leitor.pages)


def test_gera_pdf_com_titulo_cabecalho_e_linhas() -> None:
    destino = io.BytesIO()
    exportador_pdf.exportar(
        _linhas(), _COLUNAS, destino=destino, titulo="Relatorio de teste", subtitulo="Julho/2026"
    )
    texto = _texto_do_pdf(destino.getvalue())
    assert "Relatorio de teste" in texto
    assert "Julho/2026" in texto
    assert "Nome" in texto and "Horas" in texto
    assert "Jose Silva" in texto
    assert "Gerado em" in texto


def test_converte_apenas_coluna_marcada_como_duracao() -> None:
    destino = io.BytesIO()
    exportador_pdf.exportar(_linhas(), _COLUNAS, destino=destino, converter_decimal=True)
    texto = _texto_do_pdf(destino.getvalue())
    assert "2.5" in texto
    assert "1.5" in texto


def _gerador_muitas_linhas(quantidade: int) -> Iterator[dict[str, Any]]:
    for indice in range(quantidade):
        yield {"nome": f"Colaborador {indice}", "minutos": indice}


def test_pagina_quando_excede_uma_pagina() -> None:
    destino = io.BytesIO()
    exportador_pdf.exportar(_gerador_muitas_linhas(200), _COLUNAS, destino=destino)
    leitor = PdfReader(io.BytesIO(destino.getvalue()))
    assert len(leitor.pages) > 1


def test_destino_permanece_aberto_apos_exportar() -> None:
    destino = io.BytesIO()
    exportador_pdf.exportar(_linhas(), _COLUNAS, destino=destino)
    assert not destino.closed
