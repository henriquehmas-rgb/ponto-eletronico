"""Trilha de auditoria encadeada por hash (T10).

Ownership exclusivo da F1/A3. `hash_chain.py` fixa e documenta a formula do
hash e a alocacao de `sequencia` sem lacuna sob concorrencia; `servico.py`
implementa `listarAuditoria`, `obterRegistroAuditoria` e
`verificarCadeiaAuditoria`.
"""

from __future__ import annotations
