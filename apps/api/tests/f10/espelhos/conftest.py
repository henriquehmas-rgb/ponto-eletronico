"""Fixtures locais do subpacote `tests/f10/espelhos/**` (ownership de A2).

Ver `tests/f10/fechamento/conftest.py` -- mesma fixture, cópia local
(subpacote irmão, não visível por herança de `conftest.py` do pytest)."""

from __future__ import annotations

import os

import pytest

_URL_REDIS_PADRAO_LOCAL = "redis://localhost:6379/0"


@pytest.fixture(scope="session")
def redis_teste_url_f10() -> str:
    return os.environ.get("PONTO_TEST_REDIS_URL", _URL_REDIS_PADRAO_LOCAL)
