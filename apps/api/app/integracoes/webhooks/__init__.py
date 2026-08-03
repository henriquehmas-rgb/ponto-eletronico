"""Motor de entrega de webhooks (F13, T9-T13, agente A3).

Sete operacoes de `webhooks` (`apps/api/app/routers/webhooks.py`), o fan-out
transacionalmente seguro de evento de dominio para `webhook_entregas`
(`fan_out.py`), a cifra do segredo HMAC (`cifra.py`), o CRUD/negocio
(`servico.py`) e o enfileiramento de tentativas de entrega (`despacho.py`).

Este pacote NAO cria `apps/api/app/integracoes/__init__.py` (ownership de A1,
"unico criador" -- PCF F13 secao 5.2). `app.integracoes` funciona como pacote
de namespace implicito (PEP 420) ate A1 acrescentar aquele arquivo; os dois
formatos coexistem sem conflito.
"""

from __future__ import annotations
