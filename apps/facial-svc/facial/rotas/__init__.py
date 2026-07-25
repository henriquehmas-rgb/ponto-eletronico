"""Roteadores do facial-svc, montados em `facial/main.py`.

Dois grupos:

============  =========================================================
`saude`       `/health` e `/ready` — funcionais desde a Fase 0
`biometria`   `/enroll`, `/verificar`, `/liveness` — stubs 501 ate a F2/F7
============  =========================================================

Nenhum destes caminhos aparece em `packages/contracts/openapi.yaml`, e nem
poderia: o contrato publico descreve a API do produto, e **template biometrico
nunca sai pela API, para nenhum perfil, inclusive super admin** (ADR-006, item
5). Este servico e interno, so alcancavel pela rede `ponto-interna`, e existe
justamente para que o vetor nao precise transitar por nenhuma outra fronteira.
"""

from __future__ import annotations

from fastapi import FastAPI

from facial.rotas import biometria, saude

#: Ordem de montagem: saude primeiro, para que um erro de import no roteador
#: biometrico nao derrube o unico endpoint que diria o que houve.
ROTEADORES = (saude.roteador, biometria.roteador)


def registrar_rotas(app: FastAPI) -> None:
    """Monta todos os roteadores na aplicacao."""
    for roteador in ROTEADORES:
        app.include_router(roteador)


__all__ = ["ROTEADORES", "biometria", "registrar_rotas", "saude"]
