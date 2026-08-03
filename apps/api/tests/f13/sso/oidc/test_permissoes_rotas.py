"""Critério de aceite 10 do PCF F13: "toda rota nova declara x-permissao/
x-escopo idênticos ao contrato". Escopado às quatro operações de OWNERSHIP de
A9 na tag `sso` (`iniciarSso`/`callbackSso`, sem x-permissao por desenho --
RFC-018/ADR-013 decisao 4 -- e `obterConfiguracaoSso`/`atualizarConfiguracaoSso`,
`x-permissao: admin.configurar`). `concluirLoginSaml` (`POST /v1/sso/saml/acs`)
é de A10 e não é varrida aqui.

Mesmo padrão estático de `apps/api/tests/f12/afd/test_permissoes_rotas.py`
(A1): só introspecção do app FastAPI real e do `openapi.yaml` congelado, sem
tocar banco."""

from __future__ import annotations

from pathlib import Path

import yaml
from fastapi.routing import APIRoute

_RAIZ_REPO = Path(__file__).resolve().parents[6]
_OPENAPI = _RAIZ_REPO / "packages" / "contracts" / "openapi.yaml"

_METODOS = ("get", "post", "put", "patch", "delete", "head", "options")

#: Operações de ownership de A9 dentro da tag `sso` (PCF §5.2).
_OPERATION_IDS_A9 = frozenset(
    {"iniciarSso", "callbackSso", "obterConfiguracaoSso", "atualizarConfiguracaoSso"}
)


def _permissao_e_escopo_por_operation_id() -> dict[str, tuple[str | None, str | None]]:
    documento = yaml.safe_load(_OPENAPI.read_text(encoding="utf-8"))
    mapa: dict[str, tuple[str | None, str | None]] = {}
    for item in documento["paths"].values():
        for metodo, operacao in item.items():
            if metodo not in _METODOS or not isinstance(operacao, dict):
                continue
            op_id = operacao.get("operationId")
            if op_id:
                mapa[op_id] = (operacao.get("x-permissao"), operacao.get("x-escopo"))
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


def _rotas_a9_de_sso() -> list[APIRoute]:
    import sys

    raiz_api = Path(__file__).resolve().parents[4]
    if str(raiz_api) not in sys.path:
        sys.path.insert(0, str(raiz_api))
    from app.main import app  # import tardio: precisa do sys.path acima

    return [
        rota
        for rota in _todas_as_api_routes(app)
        if "sso" in (rota.tags or []) and rota.operation_id in _OPERATION_IDS_A9
    ]


def test_rotas_de_a9_foram_realmente_encontradas() -> None:
    """Prova negativa: nenhuma das quatro operações de A9 ficou fora da
    varredura por `operationId` não bater com rota real (o que indicaria
    rota não registrada -- já coberto por `tools/conferir_rotas.py`,
    reforçado aqui)."""
    ids_das_rotas_reais = {r.operation_id for r in _rotas_a9_de_sso()}
    assert ids_das_rotas_reais == _OPERATION_IDS_A9


def test_iniciar_e_callback_sso_nao_exigem_permissao_rbac() -> None:
    """RFC-018/ADR-013 decisão 4: fluxo de autenticação, acessível antes de
    existir sessão -- proteção é o `state`/assinatura, nunca RBAC."""
    permissao_e_escopo = _permissao_e_escopo_por_operation_id()
    for op_id in ("iniciarSso", "callbackSso"):
        assert permissao_e_escopo[op_id] == (None, None), op_id

    rotas = {r.operation_id: r for r in _rotas_a9_de_sso()}
    for op_id in ("iniciarSso", "callbackSso"):
        assert _permissao_declarada_na_rota(rotas[op_id]) is None, op_id


def test_admin_sso_provedores_declara_a_permissao_exata_do_contrato() -> None:
    permissao_e_escopo = _permissao_e_escopo_por_operation_id()
    rotas = {r.operation_id: r for r in _rotas_a9_de_sso()}

    divergencias: list[str] = []
    for op_id in ("obterConfiguracaoSso", "atualizarConfiguracaoSso"):
        esperado, _escopo = permissao_e_escopo[op_id]
        assert esperado == "admin.configurar"
        declarado = _permissao_declarada_na_rota(rotas[op_id])
        if declarado != esperado:
            divergencias.append(
                f"{op_id} ({rotas[op_id].path}): contrato exige x-permissao={esperado!r}, "
                f"handler declara Depends(exigir_permissao({declarado!r}))"
            )
    assert not divergencias, "\n".join(divergencias)
