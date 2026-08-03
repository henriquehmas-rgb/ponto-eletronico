"""Formatacao de baixo nivel compartilhada pelos tres exportadores TOTVS
(RM, Protheus, Datasul -- T17, agente A6). Fica em `totvs_rm/` (dentro do
glob de ownership exclusivo de A6) e e importada por `totvs_protheus` e
`totvs_datasul`; nunca editada por outro agente desta fase.

Deliberadamente PEQUENO: nao e um "motor generico de layout" concorrente ao
de T15/A5 (`app.integracoes.folha.comum`, PCF §5.1 -- "A6 nao duplica o
motor de layout"). E so a mecanica minima que qualquer um dos tres
exportadores precisaria de qualquer forma (arredondamento comercial,
separador decimal brasileiro, escrita de CSV com o modulo `csv` da
stdlib) -- a busca em `apuracoes_dia`/`apuracao_componentes`
(`app.integracoes.folha.comum.dados.coletar_linhas_apuracao`), a resolucao
de rubrica (`app.integracoes.folha.comum.rubricas.resolver_rubrica`) e o
protocolo de entrada/saida (`app.integracoes.folha.comum.protocolo`) sao
todos importados de `comum`, nunca reimplementados aqui.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Sequence
from decimal import ROUND_HALF_UP, Decimal

#: Delimitador ';' -- convencao de mercado brasileira para layout de folha,
#: confirmada pela pesquisa desta revisao e ja adotada por T15/A5 em
#: `app.integracoes.folha.comum.generico_csv.DELIMITADOR`. Repetida aqui
#: (nao importada de `comum`, que nao expoe a constante fora do proprio
#: modulo) para que os tres exportadores TOTVS sigam a mesma convencao de
#: mercado que o resto da fase.
DELIMITADOR_PADRAO = ";"

_MINUTOS_POR_HORA = Decimal(60)
_CASAS_DECIMAIS = 2


def formatar_horas_decimais(minutos: int) -> str:
    """`minutos / 60`, 2 casas decimais, arredondamento comercial
    (`ROUND_HALF_UP` -- o que folha espera, nunca o "banker's rounding" do
    `round()` padrao do Python), separador decimal `,` (convencao BR).
    Aceita `minutos` negativo (debito de banco de horas, por exemplo) --
    o sinal e preservado."""
    quantizador = Decimal(1).scaleb(-_CASAS_DECIMAIS)
    horas = (Decimal(minutos) / _MINUTOS_POR_HORA).quantize(quantizador, rounding=ROUND_HALF_UP)
    return str(horas).replace(".", ",")


def montar_csv(
    cabecalho: Sequence[str],
    linhas: Sequence[Sequence[str]],
    *,
    delimitador: str = DELIMITADOR_PADRAO,
) -> bytes:
    """Monta o arquivo CSV completo (cabecalho + linhas) em bytes UTF-8 com
    BOM (`utf-8-sig`): sem o BOM, planilhas abertas no Windows -- o
    consumidor mais comum de um CSV de RH no Brasil, mesmo motivo ja
    documentado por `app.relatorios.exportadores.csv` (F11) e por
    `app.integracoes.folha.comum.generico_csv` (F13/A5, T15) -- interpretam
    o arquivo como Windows-1252 e corrompem acentuacao. Terminador de linha
    `\\r\\n`, mesma convencao dos leiautes fiscais deste projeto e do
    `generico_csv`."""
    buffer = io.StringIO()
    escritor = csv.writer(buffer, delimiter=delimitador, lineterminator="\r\n")
    escritor.writerow(cabecalho)
    for linha in linhas:
        escritor.writerow(linha)
    return buffer.getvalue().encode("utf-8-sig")


__all__ = ["DELIMITADOR_PADRAO", "formatar_horas_decimais", "montar_csv"]
