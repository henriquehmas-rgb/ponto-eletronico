"""RBAC com escopo hierarquico: catalogo de permissoes, perfis e delegacao.

Ownership exclusivo da F1/A3. Publica, para as demais fases, o preenchimento
real de `app.core.seguranca` (`obter_sujeito`, `exigir_permissao`,
`exigir_alcance`) -- ninguem importa deste pacote diretamente, exceto os
proprios routers da F1 (`app/routers/admin.py`, `app/routers/auditoria.py`).
"""

from __future__ import annotations
