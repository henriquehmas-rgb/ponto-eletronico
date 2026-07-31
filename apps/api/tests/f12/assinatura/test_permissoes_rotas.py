"""Critério de aceite 11 do PCF F12 (`docs/fases/F12-conformidade-rep-p.md`,
§7): "toda rota declara `Depends(exigir_permissao(...))` com exatamente o
`x-permissao` do contrato" -- escopo deste arquivo é só as 6 operações da
tag `fiscal` que A3 implementa (`listarAfd`, `obterAfd`, `baixarAfd`,
`listarAej`, `obterAej`, `assinarArquivoFiscal`; as 4 restantes --
`gerarAfd`, `gerarAej`, `listarRepPs`, `criarRepP` -- são de A1/A2).

Mesmo padrão de `tests/f10/test_permissoes_rotas.py` (não existe um
equivalente genérico que cubra toda rota do projeto -- ver a nota daquele
arquivo: o único teste parecido, `tests/f1/rbac/test_catalogo_permissoes.py`,
confere só que o código existe na tabela `permissoes`, não que o HANDLER
real declara o código exato).

Estático -- não toca banco, só introspecção do app FastAPI real e do
`openapi.yaml` congelado.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from fastapi.routing import APIRoute

_RAIZ_REPO = Path(__file__).resolve().parents[5]
_OPENAPI = _RAIZ_REPO / "packages" / "contracts" / "openapi.yaml"

_METODOS = ("get", "post", "put", "patch", "delete", "head", "options")

#: Operações da tag `fiscal` cujo ownership é de A3 (PCF F12 §4, tabela
#: "Produz" -- "A3 implementa listagem/obtenção/download").
_OPERACOES_A3 = frozenset(
    {"listarAfd", "obterAfd", "baixarAfd", "listarAej", "obterAej", "assinarArquivoFiscal"}
)


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
    """Extrai o `codigo` capturado pelo closure de `exigir_permissao(codigo)`
    -- mesma técnica de `tests/f10/test_permissoes_rotas.py`."""
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
    """Achata `app.routes` em `APIRoute`s reais -- FastAPI >=0.137 envolve
    cada router incluído num `_IncludedRouter` (ver nota idêntica em
    `tests/f10/test_permissoes_rotas.py`)."""
    rotas: list[APIRoute] = []
    for rota in app.routes:  # type: ignore[attr-defined]
        if isinstance(rota, APIRoute):
            rotas.append(rota)
        elif type(rota).__name__ == "_IncludedRouter":
            rotas.extend(r for r in rota.original_router.routes if isinstance(r, APIRoute))
    return rotas


def _rotas_fiscal_de_a3() -> list[APIRoute]:
    import sys

    raiz_api = Path(__file__).resolve().parents[3]
    if str(raiz_api) not in sys.path:
        sys.path.insert(0, str(raiz_api))
    from app.main import app  # import tardio: precisa do sys.path acima

    return [rota for rota in _todas_as_api_routes(app) if rota.operation_id in _OPERACOES_A3]


def test_toda_rota_fiscal_de_a3_declara_a_permissao_exata_do_contrato() -> None:
    permissao_do_contrato = _permissao_exigida_por_operation_id()
    rotas = _rotas_fiscal_de_a3()
    assert len(rotas) == len(_OPERACOES_A3), (
        f"esperado {len(_OPERACOES_A3)} rotas de A3, encontrado {len(rotas)} -- "
        "os routers nao foram registrados, ou uma operacao de A3 nao existe ainda?"
    )

    divergencias: list[str] = []
    for rota in rotas:
        op_id = rota.operation_id
        esperado = permissao_do_contrato.get(op_id)
        assert esperado is not None, f"{op_id} sem x-permissao no contrato"
        declarado = _permissao_declarada_na_rota(rota)
        if declarado != esperado:
            divergencias.append(
                f"{op_id} ({rota.path}): contrato exige x-permissao={esperado!r}, "
                f"handler declara Depends(exigir_permissao({declarado!r}))"
            )

    mensagem = "divergencias entre contrato e Depends(exigir_permissao(...)):\n" + "\n".join(
        divergencias
    )
    assert not divergencias, mensagem
