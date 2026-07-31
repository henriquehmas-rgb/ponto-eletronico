"""Critério de aceite 11 do PCF: `listarRepPs`/`criarRepP` (ownership de A1
dentro da tag `fiscal`) declaram `Depends(exigir_permissao(...))` com
exatamente o `x-permissao` do contrato. Mesmo padrão de
`apps/api/tests/f10/test_permissoes_rotas.py` e de
`tests/f12/afd/test_permissoes_rotas.py`.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from fastapi.routing import APIRoute

_RAIZ_REPO = Path(__file__).resolve().parents[5]
_OPENAPI = _RAIZ_REPO / "packages" / "contracts" / "openapi.yaml"

_METODOS = ("get", "post", "put", "patch", "delete", "head", "options")

_OPERATION_IDS_A1 = frozenset({"listarRepPs", "criarRepP"})


def _permissao_exigida_por_operation_id() -> dict[str, str | None]:
    documento = yaml.safe_load(_OPENAPI.read_text(encoding="utf-8"))
    mapa: dict[str, str | None] = {}
    for item in documento["paths"].values():
        for metodo, operacao in item.items():
            if metodo not in _METODOS or not isinstance(operacao, dict):
                continue
            op_id = operacao.get("operationId")
            if op_id:
                mapa[op_id] = operacao.get("x-permissao")
    return mapa


def _codigo_de_exigir_permissao(funcao: object) -> str | None:
    if not callable(funcao):
        return None
    if getattr(funcao, "__qualname__", "") != "exigir_permissao.<locals>._verificar":
        return None
    code = funcao.__code__
    closure = funcao.__closure__ or ()
    for nome, cell in zip(code.co_freevars, closure, strict=True):
        if nome == "codigo":
            valor = cell.cell_contents
            assert isinstance(valor, str)
            return valor
    return None


def _permissao_declarada_na_rota(rota: APIRoute) -> str | None:
    pendentes = list(rota.dependant.dependencies)
    while pendentes:
        dependencia = pendentes.pop()
        codigo = _codigo_de_exigir_permissao(dependencia.call)
        if codigo is not None:
            return codigo
        pendentes.extend(dependencia.dependencies)
    return None


def _todas_as_api_routes(app: object) -> list[APIRoute]:
    rotas: list[APIRoute] = []
    for rota in app.routes:  # type: ignore[attr-defined]
        if isinstance(rota, APIRoute):
            rotas.append(rota)
        elif type(rota).__name__ == "_IncludedRouter":
            rotas.extend(r for r in rota.original_router.routes if isinstance(r, APIRoute))
    return rotas


def _rotas_a1_de_rep_p() -> list[APIRoute]:
    import sys

    raiz_api = Path(__file__).resolve().parents[3]
    if str(raiz_api) not in sys.path:
        sys.path.insert(0, str(raiz_api))
    from app.main import app  # import tardio: precisa do sys.path acima

    return [
        rota
        for rota in _todas_as_api_routes(app)
        if "fiscal" in (rota.tags or []) and rota.operation_id in _OPERATION_IDS_A1
    ]


def test_rep_p_declara_a_permissao_exata_do_contrato() -> None:
    permissao_do_contrato = _permissao_exigida_por_operation_id()
    rotas = _rotas_a1_de_rep_p()
    assert rotas, "nenhuma rota de REP-P encontrada -- listarRepPs/criarRepP nao registradas?"

    divergencias: list[str] = []
    for rota in rotas:
        op_id = rota.operation_id
        assert op_id
        esperado = permissao_do_contrato.get(op_id)
        if esperado is None:
            continue
        declarado = _permissao_declarada_na_rota(rota)
        if declarado != esperado:
            divergencias.append(
                f"{op_id} ({rota.path}): contrato exige x-permissao={esperado!r}, "
                f"handler declara Depends(exigir_permissao({declarado!r}))"
            )
    assert not divergencias, "\n".join(divergencias)


def test_rep_p_foi_realmente_auditada() -> None:
    ids_das_rotas_reais = {r.operation_id for r in _rotas_a1_de_rep_p()}
    assert ids_das_rotas_reais >= _OPERATION_IDS_A1
