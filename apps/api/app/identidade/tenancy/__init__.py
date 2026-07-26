"""Resolucao de tenant e ligacao do Row Level Security (F1 / A2).

`resolucao.py` concentra a unica porta de entrada para descobrir o tenant a
partir do `X-Tenant` ou do subdominio, usando `fn_resolve_tenant` (RLS ainda
nao pode ser aplicada nesse instante -- ver `packages/contracts/schema.sql`,
secao 2, e `docs/adr/ADR-001-multi-tenancy-row-level-security.md`).
"""

from __future__ import annotations
