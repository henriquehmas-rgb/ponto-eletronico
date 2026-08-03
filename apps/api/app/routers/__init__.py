"""Registro dos routers da API: um modulo por tag de `openapi.yaml`.

Os 30 modulos de tag sao GERADOS por `tools/gerar_do_contrato.py` e nao devem
ser editados a mao. Este arquivo e escrito a mao porque define a **ordem** de
montagem, e ordem importa: `saude` entra primeiro para que `/health` e `/ready`
continuem respondendo mesmo se algum router de dominio quebrar no import.

A conferencia de que nenhuma operacao do contrato ficou de fora e automatica --
`python tools/conferir_rotas.py` compara o inventario da aplicacao com o
`openapi.yaml` e falha se houver divergencia nos dois sentidos.
"""

from __future__ import annotations

from fastapi import APIRouter, FastAPI

from app.routers import (
    admin,
    afastamentos,
    aprovacoes,
    apuracoes,
    auditoria,
    auth,
    banco_horas,
    biometria,
    colaboradores,
    comprovantes,
    contratos,
    dispositivos,
    empresas,
    escalas,
    espelhos,
    fechamentos,
    feriados,
    fiscal,
    integracoes,
    jornadas,
    lgpd,
    marcacoes,
    organizacao,
    relatorios,
    saude,
    solicitacoes,
    sso,
    tenants,
    terminais,
    tratamentos,
    unidades,
    webhooks,
)

#: Ordem de montagem. `saude` primeiro; o resto segue a ordem das tags do
#: contrato, que e a ordem em que o portal OpenAPI exibe as secoes.
ROTEADORES: tuple[APIRouter, ...] = (
    saude.roteador,
    auth.roteador,
    sso.roteador,
    tenants.roteador,
    empresas.roteador,
    unidades.roteador,
    organizacao.roteador,
    colaboradores.roteador,
    contratos.roteador,
    biometria.roteador,
    dispositivos.roteador,
    terminais.roteador,
    jornadas.roteador,
    escalas.roteador,
    feriados.roteador,
    afastamentos.roteador,
    marcacoes.roteador,
    comprovantes.roteador,
    tratamentos.roteador,
    apuracoes.roteador,
    banco_horas.roteador,
    solicitacoes.roteador,
    aprovacoes.roteador,
    fechamentos.roteador,
    espelhos.roteador,
    relatorios.roteador,
    fiscal.roteador,
    webhooks.roteador,
    integracoes.roteador,
    auditoria.roteador,
    lgpd.roteador,
    admin.roteador,
)

__all__ = ["ROTEADORES", "registrar_routers"]


def registrar_routers(app: FastAPI) -> None:
    """Monta todos os routers na aplicacao."""
    for roteador in ROTEADORES:
        app.include_router(roteador)
