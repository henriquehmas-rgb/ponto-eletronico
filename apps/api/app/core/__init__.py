"""Nucleo de plataforma da API: configuracao, contexto, log, erros e middleware.

Nada aqui conhece o dominio do ponto eletronico. Sao as pecas que toda fase
posterior consome sem precisar reimplementar: `Configuracao`, o `request_id` e o
tenant corrente em `ContextVar`, o log JSON estruturado e o tratamento de erro
em `application/problem+json`.
"""

from __future__ import annotations
