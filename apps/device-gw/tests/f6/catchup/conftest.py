"""Reaproveita as fixtures de banco/Redis/ambiente de `tests/f6/push/conftest.py`
(mesmo tenant/terminal, mesmo ambiente `CONTROLID_SIMULADOR=true`) -- T5
precisa exatamente da mesma infraestrutura que T2/T4."""

from __future__ import annotations

from f6.push.conftest import (  # noqa: F401
    TenantSemeado,
    TerminalSemeado,
    _ambiente_device_gw,
    _engines_por_teste,
    _limpar_redis,
    tenant_gw,
    terminal_ativo,
    terminal_inativo,
    url_admin,
)
