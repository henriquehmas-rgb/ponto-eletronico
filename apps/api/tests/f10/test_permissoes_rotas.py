"""Critério de aceite 10 do PCF (`docs/fases/F10-workflows-aprovacoes-fechamento.md`,
§7): "toda rota declara Depends(exigir_permissao(...)) com exatamente o
x-permissao do contrato".

O PCF sugeria reaproveitar um teste equivalente já escrito por F4 -- não existe
nenhum (as buscas por `x-permissao`/`exigir_permissao`/`permiss` em `tests/f4`
não encontram nada; o único teste parecido, `tests/f1/rbac/test_catalogo_
permissoes.py`, confere que os códigos de `x-permissao` existem na tabela
`permissoes`, não que o HANDLER real declara o código exato). Este arquivo
fecha essa lacuna de verdade, para as quatro tags que a F10 possui
(`solicitacoes`, `aprovacoes`, `fechamentos`, `espelhos` -- `tipos-solicitacao`,
`delegacoes` e `periodos` vivem nos mesmos módulos de router, por convenção
herdada da Fase 0, ver relatório de A1/A2).

Não toca banco -- é estático, só introspecção do app FastAPI real e do
`openapi.yaml` congelado.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from fastapi.routing import APIRoute

_RAIZ_REPO = Path(__file__).resolve().parents[4]
_OPENAPI = _RAIZ_REPO / "packages" / "contracts" / "openapi.yaml"

_METODOS = ("get", "post", "put", "patch", "delete", "head", "options")

#: Tags de router cujo ownership é da F10 (ver docs/fases/
#: F10-workflows-aprovacoes-fechamento.md, §5 -- tabela de ownership).
_TAGS_F10 = frozenset({"solicitacoes", "aprovacoes", "fechamentos", "espelhos"})


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
    """Extrai o `codigo` capturado pelo closure de `exigir_permissao(codigo)`.

    `exigir_permissao` (`app/core/seguranca.py`) é uma fábrica de dependência:
    devolve uma função interna `_verificar` cujo `__closure__` guarda o
    `codigo` original -- é a única forma de recuperar, em runtime, qual
    x-permissao um `Depends(exigir_permissao("..."))` realmente carrega.
    """
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
    """Percorre a árvore de dependências reais da rota (`rota.dependant`,
    montada pelo FastAPI a partir da assinatura do handler) procurando a
    dependência produzida por `exigir_permissao`."""
    pendentes = list(rota.dependant.dependencies)
    while pendentes:
        dependencia = pendentes.pop()
        codigo = _codigo_de_exigir_permissao(dependencia.call)
        if codigo is not None:
            return codigo
        pendentes.extend(dependencia.dependencies)
    return None


def _todas_as_api_routes(app: object) -> list[APIRoute]:
    """Achata `app.routes` em `APIRoute`s reais.

    Achado ao escrever este teste: FastAPI >=0.137 passou a envolver cada
    router incluído (`app.include_router(...)`) num `_IncludedRouter`
    (`fastapi.routing`) em vez de expandir as rotas filhas diretamente na
    lista de `app.routes` -- `isinstance(rota, APIRoute)` direto em
    `app.routes` não encontra nada mais (confirmado: 35 entradas, 0
    `APIRoute`, todas as 30+ tags viram `_IncludedRouter`). As `APIRoute`
    reais ficam em `_IncludedRouter.original_router.routes`.
    `tools/conferir_rotas.py` nunca bateu nesse problema porque usa
    `app.openapi()` (schema gerado), não introspecção direta da árvore de
    rotas -- este teste precisa da árvore real porque é o único lugar do
    projeto que lê `route.dependant` para extrair o `Depends(...)` de
    verdade.
    """
    rotas: list[APIRoute] = []
    for rota in app.routes:  # type: ignore[attr-defined]
        if isinstance(rota, APIRoute):
            rotas.append(rota)
        elif type(rota).__name__ == "_IncludedRouter":
            rotas.extend(r for r in rota.original_router.routes if isinstance(r, APIRoute))
    return rotas


def _rotas_f10() -> list[APIRoute]:
    import sys

    raiz_api = Path(__file__).resolve().parents[2]
    if str(raiz_api) not in sys.path:
        sys.path.insert(0, str(raiz_api))
    from app.main import app  # import tardio: precisa do sys.path acima

    return [rota for rota in _todas_as_api_routes(app) if _TAGS_F10.intersection(rota.tags or [])]


def test_toda_rota_f10_declara_a_permissao_exata_do_contrato() -> None:
    permissao_do_contrato = _permissao_exigida_por_operation_id()
    rotas = _rotas_f10()
    assert rotas, "nenhuma rota com tag de F10 encontrada -- os routers não foram registrados?"

    divergencias: list[str] = []
    sem_permissao_no_contrato: list[str] = []

    for rota in rotas:
        op_id = rota.operation_id
        assert op_id, f"rota {rota.path} ({rota.methods}) sem operationId"

        esperado = permissao_do_contrato.get(op_id)
        if esperado is None:
            # Operação existe no contrato sem x-permissao (não é o caso de
            # nenhuma operação de F10 hoje, mas não é erro desta fase se
            # acontecer -- só não há o que comparar).
            sem_permissao_no_contrato.append(op_id)
            continue

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


def test_toda_rota_f10_do_contrato_com_x_permissao_foi_auditada() -> None:
    """Prova negativa: nenhuma operação de F10 no contrato ficou fora da
    varredura acima por operationId não bater com nenhuma rota real (o que
    indicaria uma rota não registrada -- já coberto por `conferir_rotas.py`,
    mas reforçado aqui porque este teste teria passado vazio silenciosamente
    caso `_rotas_f10()` não achasse nada por uma tag renomeada)."""
    permissao_do_contrato = _permissao_exigida_por_operation_id()
    ids_das_rotas_reais = {r.operation_id for r in _rotas_f10()}

    documento = yaml.safe_load(_OPENAPI.read_text(encoding="utf-8"))
    ids_f10_no_contrato = {
        operacao["operationId"]
        for item in documento["paths"].values()
        for metodo, operacao in item.items()
        if metodo in _METODOS
        and isinstance(operacao, dict)
        and _TAGS_F10.intersection(operacao.get("tags") or [])
        and operacao.get("operationId")
    }

    faltando = sorted(ids_f10_no_contrato - ids_das_rotas_reais)
    assert not faltando, f"operações de F10 no contrato sem rota real correspondente: {faltando}"
    # Confirma que o vocabulário de permissões usado é o mesmo dos dois lados.
    assert all(op in permissao_do_contrato for op in ids_f10_no_contrato)
