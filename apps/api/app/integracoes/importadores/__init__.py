"""Importadores genéricos da tag `integracoes` (F13).

Pacote pai dos importadores concretos. Hoje só `afd_terceiro/**` (A8, T19)
mora aqui, mas o nome é plural de propósito: uma fase futura que precisar de
outro importador dedicado (ex.: `marcacoes` de um relógio de ponto legado sem
AFD) tem onde crescer sem reabrir `afd_terceiro/**`.

**Nota de ownership (PCF F13 §5.2):** `apps/api/app/integracoes/__init__.py`
(o nível acima deste) é criação exclusiva de A1 -- este pacote (`importadores/`
e tudo abaixo) não está nomeado explicitamente na tabela de ownership, mas
está inteiramente sob `apps/api/app/integracoes/`, onde nenhum outro agente
desta fase tem trabalho planejado (A2 usa `sandbox/`, A3 usa `webhooks/`, A5/
A6/A7 usam `folha/`). Criado por A8 (T19) como extensão natural do próprio
ownership (`apps/api/app/integracoes/importadores/afd_terceiro/**`), decisão
registrada no relatório final da fase.
"""

from __future__ import annotations
