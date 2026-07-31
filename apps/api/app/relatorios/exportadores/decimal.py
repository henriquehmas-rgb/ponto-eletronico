"""Conversao de duracao (minutos inteiros) para horas decimais -- so na
apresentacao/exportacao (F11, T5/A3, PCF §2.5).

`converterDecimal=true` na query de `executarRelatorio` (`openapi.yaml`,
`executarRelatorio`, linha ~14262) e a descricao do proprio parametro ja fixa
a regra: "Internamente tudo e minuto inteiro". Isto e regra de RENDERIZACAO,
nunca de dominio: nenhum dataset (A2/A3/A4) devolve duracao em unidade
diferente de minuto inteiro; esta funcao e chamada exclusivamente pelos
exportadores (`app.relatorios.exportadores.{csv,xlsx,pdf}`, via
`valor_formatado` em `__init__.py`) sobre as colunas marcadas
`ColunaExportacao(duracao=True)` no catalogo -- nunca gravada em lugar
nenhum, nunca aplicada dentro de um dataset.

**Casas decimais: 2** (`CASAS_DECIMAIS_PADRAO`). Escolha documentada: 2 casas
cobrem o minuto exato sem sobra de precisao (1 minuto = 0.0166... horas;
arredondar para 2 casas ja perde o minuto individual, que e o comportamento
esperado de uma coluna "decimal" pensada para leitura humana/folha, nao para
recalculo -- quem precisa do minuto exato le a coluna em minutos, nao a
decimal).
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

CASAS_DECIMAIS_PADRAO = 2

_MINUTOS_POR_HORA = Decimal(60)


def minutos_para_horas_decimais(
    minutos: int, *, casas_decimais: int = CASAS_DECIMAIS_PADRAO
) -> float:
    """`minutos / 60`, arredondado para `casas_decimais` (padrao 2,
    `ROUND_HALF_UP` -- arredondamento comercial, o que RH/folha espera, nunca
    o "banker's rounding" que `round()` do Python usa por padrao).

    `minutos` pode ser negativo (saldo devedor de banco de horas, por
    exemplo) -- o sinal e preservado.
    """
    quantizador = Decimal(1).scaleb(-casas_decimais)
    horas = (Decimal(minutos) / _MINUTOS_POR_HORA).quantize(quantizador, rounding=ROUND_HALF_UP)
    return float(horas)


__all__ = ["CASAS_DECIMAIS_PADRAO", "minutos_para_horas_decimais"]
