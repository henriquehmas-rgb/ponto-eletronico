"""Ponte para o semeador de desenvolvimento.

`make seed` e `.\\tasks.ps1 seed` chamam `python -m app.scripts.seed`. O
semeador de verdade vive em `migrations/seed_dev.py`, que e ownership do agente
de migrations e ja resolve URL do banco, idempotencia e origem da senha do
administrador. Duplicar aquela logica aqui criaria duas fontes da verdade para o
mesmo dado -- este modulo apenas encaminha os argumentos.

Uso::

    python -m app.scripts.seed --help
    PONTO_SEED_ADMIN_SENHA=... python -m app.scripts.seed
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys
from collections.abc import Sequence
from typing import Any

CAMINHO_SEED = pathlib.Path(__file__).resolve().parents[2] / "migrations" / "seed_dev.py"


def main(argv: Sequence[str] | None = None) -> int:
    if not CAMINHO_SEED.exists():
        print(f"semeador ausente: {CAMINHO_SEED}", file=sys.stderr)
        return 1

    especificacao = importlib.util.spec_from_file_location("ponto_seed_dev", CAMINHO_SEED)
    if especificacao is None or especificacao.loader is None:  # pragma: no cover
        print(f"nao foi possivel carregar {CAMINHO_SEED}", file=sys.stderr)
        return 1

    modulo = importlib.util.module_from_spec(especificacao)
    especificacao.loader.exec_module(modulo)
    executar: Any = modulo.main
    return int(executar(argv))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
