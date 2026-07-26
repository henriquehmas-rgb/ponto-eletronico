"""Importacao dos models ORM de `packages/contracts`, com o mesmo fallback
usado em `apps/api/migrations/env.py`, `apps/api/migrations/seed_dev.py` e
`app.identidade.rbac._contrato`: em ambiente normal o pacote `ponto-contracts`
esta instalado (editable), e o fallback por `sys.path` cobre o checkout cru
sem instalacao previa.

Nome deliberadamente distinto de `app.schemas.contrato` (os schemas Pydantic
do contrato publico): aqui `contrato` e o modulo de models SQLAlchemy.
"""

from __future__ import annotations

import pathlib
import sys

try:  # pragma: no cover - caminho feliz
    import ponto_contracts as contrato
except ModuleNotFoundError:  # pragma: no cover - fallback de checkout cru
    _RAIZ = pathlib.Path(__file__).resolve().parents[5]
    sys.path.insert(0, str(_RAIZ / "packages" / "contracts"))
    import models as contrato  # type: ignore[import-not-found,no-redef]

__all__ = ["contrato"]
