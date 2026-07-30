"""Fixtures locais do subpacote `tests/f10/fechamento/**` (ownership de A2).

Só acrescenta o que a fixture COMPARTILHADA da fase (`tests/f10/conftest.py`,
ownership de A1) não cobre -- aqui, a URL do Redis de teste, necessária para
`criarFechamento`/`gerarEspelhos` enfileirarem de verdade (mesmo padrão de
`tests/f4/tratamento/conftest.py::redis_teste_url`, cópia local, nunca
importada de outra fase)."""

from __future__ import annotations

import os

import pytest

_URL_REDIS_PADRAO_LOCAL = "redis://localhost:6379/0"


@pytest.fixture(scope="session")
def redis_teste_url_f10() -> str:
    """`PONTO_TEST_REDIS_URL`, com o mesmo default local de
    `tests/f4/tratamento/conftest.py` -- nunca aponta para ambiente real."""
    return os.environ.get("PONTO_TEST_REDIS_URL", _URL_REDIS_PADRAO_LOCAL)
