"""De-para de rubricas: traduz `apuracao_componentes.codigo` (nosso codigo
interno, por exemplo `he_50`, `adicional_noturno`) para o codigo que o
sistema de folha do parceiro espera, usando `integracoes_folha.
mapeamento_rubricas` (JSONB, schema `IntegracaoFolha.mapeamentoRubricas`).

Modulo deliberadamente minusculo: a traducao e uma unica busca em
dicionario, mas fica em modulo proprio porque TODO exportador (generico ou
de parceiro) precisa da mesma regra -- "sem mapeamento, sai com o codigo
interno" (comportamento do `generico_csv`) e uma decisao de exportador, nao
deste modulo, que so resolve e devolve `None` quando nao ha entrada.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def resolver_rubrica(
    codigo_componente: str, mapeamento_rubricas: Mapping[str, Any] | None
) -> str | None:
    """Devolve a rubrica do parceiro para `codigo_componente`, ou `None`
    quando `mapeamento_rubricas` e vazio/ausente ou nao tem entrada para
    este codigo."""
    if not mapeamento_rubricas:
        return None
    valor = mapeamento_rubricas.get(codigo_componente)
    if valor is None:
        return None
    return str(valor)
