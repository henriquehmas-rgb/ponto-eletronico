"""Modelos Pydantic v2 da API.

`app.schemas.contrato` e GERADO a partir de `components.schemas` do
`packages/contracts/openapi.yaml` -- 245 modelos, com atributo Python em
`snake_case` e `alias` JSON em `camelCase`. Nao edite o arquivo a mao: regere
com `python tools/gerar_do_contrato.py`. Se um modelo esta errado, o defeito
esta no contrato, e o conserto passa por RFC.

Uso nos routers::

    from app.schemas import contrato

    async def listar_colaboradores(...) -> contrato.ListaColaborador: ...
"""

from __future__ import annotations

from app.schemas import contrato

__all__ = ["contrato"]
