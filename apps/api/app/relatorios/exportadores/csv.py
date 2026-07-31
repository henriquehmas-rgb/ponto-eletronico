"""Exportador CSV, streaming linha a linha (F11, T5/A3).

Usa o modulo `csv` da stdlib (nunca uma dependencia nova, PCF §2.5). Grava em
UTF-8 com BOM (`utf-8-sig`): sem o BOM, o Excel no Windows -- o consumidor
mais comum de um CSV de RH no Brasil -- interpreta o arquivo como
Windows-1252 e corrompe qualquer acento (colaborador "José" vira "JosÃ©").
Delimitador `,` (RFC 4180 padrao); nao ha exigencia de `;` fixada em nenhum
documento desta fase.

Nomeado `csv.py` dentro do pacote: `import csv` aqui de dentro resolve para o
modulo da stdlib (import absoluto, Python 3 nao faz import relativo
implicito), nao para si mesmo -- mesmo raciocinio documentado em
`decimal.py` para o mesmo padrao de nome.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable, Mapping, Sequence
from typing import Any, BinaryIO

from app.relatorios.exportadores import ColunaExportacao, cabecalhos, valor_formatado


def exportar(
    linhas: Iterable[Mapping[str, Any]],
    colunas: Sequence[ColunaExportacao],
    *,
    destino: BinaryIO,
    converter_decimal: bool = False,
    casas_decimais: int = 2,
) -> None:
    """Escreve `linhas` como CSV em `destino`, uma linha por vez -- nunca
    materializa o conjunto inteiro em memoria (PCF §2.3 item 2). `destino`
    permanece aberto ao final: fechar e responsabilidade de quem chamou."""
    # `TextIOWrapper` em cima do `BinaryIO` para o `csv.writer` (que exige um
    # arquivo em modo texto). `write_through=True` evita buffer proprio do
    # wrapper que atrasaria o streaming linha a linha; `detach()` ao final
    # devolve `destino` intacto (sem fechar o stream binario subjacente, que
    # e de quem chamou).
    texto = io.TextIOWrapper(destino, encoding="utf-8-sig", newline="", write_through=True)
    try:
        escritor = csv.writer(texto)
        escritor.writerow(cabecalhos(colunas))
        for linha in linhas:
            escritor.writerow(
                [
                    valor_formatado(
                        linha,
                        coluna,
                        converter_decimal=converter_decimal,
                        casas_decimais=casas_decimais,
                    )
                    for coluna in colunas
                ]
            )
    finally:
        texto.flush()
        texto.detach()


__all__ = ["exportar"]
