"""Interop de cifra: `apps/api/app/terminais/cifra.py` cifra, `gateway.dominio.
cifra` decifra -- os dois precisam concordar em algoritmo, empacotamento
(`iv || ciphertext||tag`) e variavel de ambiente (`PONTO_TERMINAL_CHAVE_MESTRA`),
mesmo sendo copias deliberadas (nao um pacote compartilhado).

O modulo da API e carregado diretamente do arquivo (`importlib`), sem passar
pelo pacote `app` inteiro -- o `device-gw` nao depende de `apps/api` em
producao, e este teste so quer provar que os DOIS ALGORITMOS concordam, nao
acoplar os dois processos.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from types import ModuleType

import pytest

from gateway.dominio import cifra as cifra_gateway

CHAVE_TESTE = "c" * 64


@pytest.fixture(autouse=True)
def _chave_mestra() -> None:
    os.environ["PONTO_TERMINAL_CHAVE_MESTRA"] = CHAVE_TESTE


def _carregar_cifra_api() -> ModuleType:
    caminho = Path(__file__).resolve().parents[4] / "api" / "app" / "terminais" / "cifra.py"
    spec = importlib.util.spec_from_file_location("cifra_api_f6_teste", caminho)
    assert spec is not None and spec.loader is not None
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def test_decifra_o_que_a_api_cifrou() -> None:
    cifra_api = _carregar_cifra_api()
    blob, chave_id = cifra_api.cifrar_senha("senha-do-equipamento")
    assert chave_id == "term-v1"
    assert b"senha-do-equipamento" not in blob

    decifrada = cifra_gateway.decifrar_senha(blob)
    assert decifrada == "senha-do-equipamento"


def test_chave_ausente_leva_a_erro_explicito() -> None:
    del os.environ["PONTO_TERMINAL_CHAVE_MESTRA"]
    with pytest.raises(cifra_gateway.ChaveTerminalAusente):
        cifra_gateway.decifrar_senha(b"\x00" * 28)
