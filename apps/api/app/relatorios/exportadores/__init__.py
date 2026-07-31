"""Exportadores genericos de relatorio: CSV, XLSX, PDF e a conversao decimal
de apresentacao (F11, T5/A3).

Os tres formatos (`csv.py`, `xlsx.py`, `pdf.py`) expoem a MESMA assinatura,
fixada por `docs/fases/F11-relatorios-espelho-exportacoes.md` §4::

    exportar(linhas: Iterable[Mapping[str, Any]], colunas: Sequence[ColunaExportacao],
             *, destino: BinaryIO, converter_decimal: bool = False,
             casas_decimais: int = 2) -> None

`linhas` e um iteravel (nunca materializado numa lista pelo exportador --
quem chama pode passar um cursor de servidor ou um gerador) e `destino` e um
`BinaryIO` aberto para escrita (arquivo real em disco ou `io.BytesIO()`): os
tres exportadores escrevem em streaming, nunca constroem a saida inteira em
memoria antes de gravar (PCF §2.3 item 2 -- "nunca materializam... em memoria
Python de uma vez"). Fechar `destino` e responsabilidade de quem chamou, nao
do exportador.

`ColunaExportacao` e o contrato entre o motor (A1) / os datasets (A2/A3/A4) e
o exportador: qual chave ler de cada linha, qual rotulo usar no cabecalho, e
se a coluna e uma "duracao" (minutos) elegivel para a conversao decimal do
`converterDecimal=true` da query de `executarRelatorio` (PCF §2.5). A
conversao acontece EXCLUSIVAMENTE aqui, na apresentacao/exportacao -- nenhum
dataset devolve duracao em unidade diferente de minuto inteiro (`decimal.py`
documenta a formula).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ColunaExportacao:
    """Uma coluna a exportar: a chave lida de cada linha (`dict`/`Mapping`
    devolvido pelo dataset), o rotulo impresso no cabecalho e se a coluna
    carrega uma duracao em minutos (elegivel para `converterDecimal`)."""

    chave: str
    rotulo: str
    duracao: bool = False


def valor_formatado(
    linha: Mapping[str, Any],
    coluna: ColunaExportacao,
    *,
    converter_decimal: bool = False,
    casas_decimais: int = 2,
) -> Any:
    """Le `coluna.chave` de `linha` e aplica a conversao decimal quando
    pedida e a coluna for de duracao. Compartilhada pelos tres exportadores
    para a regra nunca divergir entre formatos."""
    bruto = linha.get(coluna.chave)
    if converter_decimal and coluna.duracao and bruto is not None:
        from app.relatorios.exportadores.decimal import minutos_para_horas_decimais

        return minutos_para_horas_decimais(bruto, casas_decimais=casas_decimais)
    return bruto


def cabecalhos(colunas: Sequence[ColunaExportacao]) -> list[str]:
    """Lista de rotulos, na ordem das colunas -- usada pelos tres exportadores
    para a primeira linha/cabecalho."""
    return [coluna.rotulo for coluna in colunas]


__all__ = ["ColunaExportacao", "cabecalhos", "valor_formatado"]
