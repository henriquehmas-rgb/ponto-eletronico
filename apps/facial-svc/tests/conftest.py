"""Ambiente dos testes do facial-svc.

Este arquivo existe por uma razao de ordem de importacao: `facial/main.py` monta
a aplicacao **no import** (`app = criar_aplicacao()`) e `obter_configuracao` e
`lru_cache`. Ajustar `os.environ` dentro de um modulo de teste chegaria tarde —
o `conftest.py` e importado pelo pytest antes de qualquer modulo de teste, e e o
unico ponto em que ainda da para influenciar a configuracao do processo.

Duas variaveis sao definidas aqui, e nenhuma delas vale em producao:

``AMBIENTE=ci``
    Mantem `/docs` ligado e, principalmente, impede que o validador de
    `Configuracao` recuse `FACIAL_BAIXAR_MODELO` (ele so e recusado em
    `hml`/`prd`).
``FACIAL_BAIXAR_MODELO=1``
    Deixa o InsightFace baixar `buffalo_l` na primeira execucao da suite, caso o
    diretorio de modelos esteja vazio. Sao ~326 MB, uma vez por maquina. Em
    producao isso e proibido por configuracao: la os pesos chegam pelo volume
    `facial-models`, junto com o deploy.

`FACIAL_MODEL_DIR` so e definido se o ambiente ainda nao o trouxer, para que o
CI e a VPS possam apontar para um cache ja populado sem editar teste.
"""

from __future__ import annotations

import os
import pathlib

os.environ.setdefault("AMBIENTE", "ci")
os.environ.setdefault("LOG_FORMATO", "texto")
os.environ.setdefault("FACIAL_BAIXAR_MODELO", "1")
os.environ.setdefault(
    "FACIAL_MODEL_DIR",
    str(pathlib.Path.home() / ".insightface" / "models"),
)
