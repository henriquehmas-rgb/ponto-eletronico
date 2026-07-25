"""Roteadores do device-gw, montados em `gateway/main.py`.

Quatro grupos, separados por **quem inicia a conversa** — que e o que muda o
desenho, a autenticacao e o dono do caminho da URL:

============  ===========================  =========================================
Modulo        Quem chama                   Dono do caminho
============  ===========================  =========================================
`saude`       Docker, Traefik, operacao    nosso
`push`        o terminal (busca comando)   firmware Control iD (confirmar na F6)
`monitor`     o terminal (avisa evento)    firmware Control iD (confirmar na F6)
`catchup`     nosso worker / scheduler     nosso
============  ===========================  =========================================

Nenhum destes caminhos aparece em `packages/contracts/openapi.yaml`, e isso e
deliberado: o contrato congelado descreve a API do produto, consumida por
navegador, aplicativo e integrador. O device-gw fala o protocolo de um
fabricante de um lado e chama a API interna do outro — ajustar caminho aqui na
F6 nao exige RFC. O que **nao** muda sem RFC e o codigo de erro devolvido
(`packages/contracts/errors.yaml`) e o formato da marcacao entregue a API.
"""

from __future__ import annotations

from fastapi import FastAPI

from gateway.rotas import catchup, monitor, push, saude

#: Ordem de montagem: saude primeiro, para que um erro de import em qualquer
#: roteador de protocolo nao derrube o unico endpoint que diria o que houve.
ROTEADORES = (saude.roteador, push.roteador, monitor.roteador, catchup.roteador)


def registrar_rotas(app: FastAPI) -> None:
    """Monta todos os roteadores na aplicacao."""
    for roteador in ROTEADORES:
        app.include_router(roteador)


__all__ = ["ROTEADORES", "catchup", "monitor", "push", "registrar_rotas", "saude"]
