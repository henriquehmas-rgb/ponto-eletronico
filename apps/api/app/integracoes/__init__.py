"""API pública, webhooks e integrações (F13).

Pacote raiz de tudo que esta fase constrói sob `app.integracoes.*`:

* `app.integracoes.clientes` — gestão de clientes de API e chaves (A1, T2).
* `app.integracoes.sandbox` — sandbox com dados sintéticos (A2, T8).
* `app.integracoes.webhooks` — motor de entrega de webhooks (A3).
* `app.integracoes.folha` — exportadores de folha de pagamento (A5/A6/A7).
* `app.integracoes.importadores` — importadores de terceiro, ex. AFD (A8).

Cada subpacote é ownership exclusivo de um agente (PCF F13 §5.2) — este
`__init__.py` é o único arquivo do nível raiz do pacote, criado por A1 (T1),
e não contém lógica: só documenta o mapa do pacote para quem chega depois.
"""

from __future__ import annotations
