"""`app.relatorios.exportadores.csv` (F11, T5/A3)."""

from __future__ import annotations

import csv as csv_stdlib
import io
from collections.abc import Iterator
from typing import Any

from app.relatorios.exportadores import ColunaExportacao
from app.relatorios.exportadores import csv as exportador_csv

_COLUNAS = [
    ColunaExportacao(chave="nome", rotulo="Nome"),
    ColunaExportacao(chave="minutos", rotulo="Horas", duracao=True),
]


def _linhas() -> list[dict[str, Any]]:
    return [
        {"nome": "José", "minutos": 150},
        {"nome": "Ana", "minutos": 90},
    ]


def test_escreve_cabecalho_e_linhas() -> None:
    destino = io.BytesIO()
    exportador_csv.exportar(_linhas(), _COLUNAS, destino=destino)

    texto = destino.getvalue().decode("utf-8-sig")
    leitor = list(csv_stdlib.reader(io.StringIO(texto)))
    assert leitor[0] == ["Nome", "Horas"]
    assert leitor[1] == ["José", "150"]
    assert leitor[2] == ["Ana", "90"]


def test_converte_apenas_coluna_marcada_como_duracao() -> None:
    destino = io.BytesIO()
    exportador_csv.exportar(_linhas(), _COLUNAS, destino=destino, converter_decimal=True)

    texto = destino.getvalue().decode("utf-8-sig")
    linhas = list(csv_stdlib.reader(io.StringIO(texto)))
    assert linhas[1] == ["José", "2.5"]
    assert linhas[2] == ["Ana", "1.5"]


def test_bom_utf8_para_abrir_correto_no_excel() -> None:
    destino = io.BytesIO()
    exportador_csv.exportar(_linhas(), _COLUNAS, destino=destino)
    assert destino.getvalue().startswith(b"\xef\xbb\xbf")


def test_nunca_materializa_linhas_em_lista() -> None:
    """`linhas` pode ser um gerador puro (sem `__len__`/`__getitem__`) --
    prova que o exportador nunca chama `list(linhas)` nem indexa."""

    class _SemMaterializar:
        def __iter__(self) -> Iterator[dict[str, Any]]:
            yield from _linhas()

        def __len__(self) -> int:  # pragma: no cover - nunca deve ser chamado
            raise AssertionError("exportador nao deve materializar as linhas")

    destino = io.BytesIO()
    exportador_csv.exportar(_SemMaterializar(), _COLUNAS, destino=destino)
    texto = destino.getvalue().decode("utf-8-sig")
    assert "José" in texto and "Ana" in texto


def test_destino_permanece_aberto_apos_exportar() -> None:
    destino = io.BytesIO()
    exportador_csv.exportar(_linhas(), _COLUNAS, destino=destino)
    assert not destino.closed
