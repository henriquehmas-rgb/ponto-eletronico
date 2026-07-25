"""Confere o inventario de rotas da aplicacao contra o contrato congelado.

Por que existe: os routers sao gerados a partir do `openapi.yaml`, mas nada
impede alguem de apagar um modulo, esquecer de registra-lo em
`app/routers/__init__.py` ou renomear um `operationId`. Este script transforma
esse tipo de deriva silenciosa em falha ruidosa.

Compara nos DOIS sentidos:

* operacao do contrato que a aplicacao nao expoe  -> FALTANDO
* operacao da aplicacao fora do contrato          -> EXCEDENTE

`/health`, `/ready`, `/docs`, `/redoc` e `/openapi.json` sao operacionais e
ficam fora do contrato de proposito -- entram na lista de isentos.

Uso (a partir de `apps/api/`)::

    python tools/conferir_rotas.py

Saida 0 quando o inventario bate; 1 quando ha divergencia.
"""

from __future__ import annotations

import pathlib
import sys

import yaml

RAIZ_API = pathlib.Path(__file__).resolve().parents[1]
CONTRATO = RAIZ_API.parents[1] / "packages" / "contracts" / "openapi.yaml"

METODOS = ("get", "post", "put", "patch", "delete", "head", "options")

#: Caminhos operacionais que nao pertencem ao contrato da API v1.
ISENTOS = frozenset(
    {"/health", "/ready", "/live", "/docs", "/docs/oauth2-redirect", "/redoc", "/openapi.json"}
)


def inventario(esquema: dict[str, object]) -> set[tuple[str, str]]:
    caminhos = esquema.get("paths") or {}
    assert isinstance(caminhos, dict)
    return {
        (metodo.upper(), caminho)
        for caminho, item in caminhos.items()
        if caminho not in ISENTOS
        for metodo in item
        if metodo in METODOS
    }


def operation_ids(esquema: dict[str, object]) -> dict[tuple[str, str], str]:
    caminhos = esquema.get("paths") or {}
    assert isinstance(caminhos, dict)
    return {
        (metodo.upper(), caminho): item[metodo].get("operationId", "")
        for caminho, item in caminhos.items()
        if caminho not in ISENTOS
        for metodo in item
        if metodo in METODOS
    }


def main() -> int:
    sys.path.insert(0, str(RAIZ_API))
    from app.main import app  # import tardio: depende do sys.path ajustado acima

    da_aplicacao = app.openapi()
    do_contrato = yaml.safe_load(CONTRATO.read_text(encoding="utf-8"))

    inv_app = inventario(da_aplicacao)
    inv_contrato = inventario(do_contrato)

    faltando = sorted(inv_contrato - inv_app)
    excedente = sorted(inv_app - inv_contrato)

    ids_app = operation_ids(da_aplicacao)
    ids_contrato = operation_ids(do_contrato)
    ids_divergentes = sorted(
        (chave, ids_contrato[chave], ids_app[chave])
        for chave in inv_app & inv_contrato
        if ids_contrato[chave] != ids_app[chave]
    )

    print(f"contrato : {len(inv_contrato)} operacoes em {len(do_contrato['paths'])} caminhos")
    print(f"aplicacao: {len(inv_app)} operacoes em {len(da_aplicacao['paths'])} caminhos")

    for metodo, caminho in faltando:
        print(f"FALTANDO  {metodo:6} {caminho}", file=sys.stderr)
    for metodo, caminho in excedente:
        print(f"EXCEDENTE {metodo:6} {caminho}", file=sys.stderr)
    for (metodo, caminho), esperado, obtido in ids_divergentes:
        print(
            f"OPERATIONID {metodo:6} {caminho}: contrato={esperado} aplicacao={obtido}",
            file=sys.stderr,
        )

    if faltando or excedente or ids_divergentes:
        print("\nInventario DIVERGENTE do contrato.", file=sys.stderr)
        return 1

    print("Inventario identico ao contrato (metodo, caminho e operationId).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
