"""Critério de aceite 11 do PCF (`docs/fases/F12-conformidade-rep-p.md`,
§7): "toda rota declara Depends(exigir_permissao(...)) com exatamente o
x-permissao do contrato" -- escopado às operações de OWNERSHIP de A1
(`gerarAfd`; `listarRepPs`/`criarRepP` estão em
`tests/f12/rep_p/test_permissoes_rotas.py`). As demais operações da tag
`fiscal` (`listarAfd`, `obterAfd`, `baixarAfd`, `gerarAej`, `listarAej`,
`obterAej`, `assinarArquivoFiscal`) são de A2/A3 e não são varridas aqui --
cada agente prova a permissão do que implementa.

Mesmo padrão de `apps/api/tests/f10/test_permissoes_rotas.py`: estático, só
introspecção do app FastAPI real e do `openapi.yaml` congelado, sem tocar
banco.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from fastapi.routing import APIRoute

_RAIZ_REPO = Path(__file__).resolve().parents[5]
_OPENAPI = _RAIZ_REPO / "packages" / "contracts" / "openapi.yaml"

_METODOS = ("get", "post", "put", "patch", "delete", "head", "options")

#: Operações de ownership de A1 dentro da tag `fiscal` (PCF §5).
_OPERATION_IDS_A1 = frozenset({"gerarAfd"})


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


def _rotas_a1_de_fiscal() -> list[APIRoute]:
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


def test_gerar_afd_declara_a_permissao_exata_do_contrato() -> None:
    permissao_do_contrato = _permissao_exigida_por_operation_id()
    rotas = _rotas_a1_de_fiscal()
    assert rotas, "nenhuma rota de A1 na tag fiscal encontrada -- gerarAfd nao registrada?"

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


def test_gerar_afd_foi_realmente_auditada() -> None:
    """Prova negativa: `gerarAfd` não ficou fora da varredura acima por
    `operationId` não bater com nenhuma rota real (o que indicaria rota não
    registrada -- já coberto por `conferir_rotas.py`, reforçado aqui)."""
    ids_das_rotas_reais = {r.operation_id for r in _rotas_a1_de_fiscal()}
    assert ids_das_rotas_reais >= _OPERATION_IDS_A1
