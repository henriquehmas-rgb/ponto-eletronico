"""Aplicacao FastAPI do Ponto Eletronico (REP-P multiempresa).

A Fase 0 entrega CONTRATO E ANDAIME. O que existe aqui:

* `app.main` -- montagem da aplicacao, ciclo de vida, middlewares e tratadores.
* `app.core` -- configuracao, contexto de requisicao, log JSON, erros RFC 9457.
* `app.db` -- engine assincrona, fabrica de sessoes e dependencia de sessao.
* `app.routers` -- um modulo por tag de `packages/contracts/openapi.yaml`.
* `app.schemas` -- modelos Pydantic v2 espelhando `components.schemas`.

Nenhuma regra de negocio vive aqui: cada operacao do contrato responde 501 com
o codigo `PONTO-INT-005` ate a fase que a implementa entrar em execucao.
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "0.1.0"
