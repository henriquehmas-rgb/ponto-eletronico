"""Camada de tratamento (correção da apuração) -- ownership exclusivo de A3.

CRUD de tratamentos e tipos de tratamento (T8), decisão de tratamento com
trava de período fechado (T9) e recálculo determinístico/idempotente com
diff auditado (T10). Ver `docs/fases/F04-calculo-banco-de-horas.md`.
"""

from __future__ import annotations
