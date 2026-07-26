"""Importadores CSV/XLSX (Fase F2 / agente A3), T10.

`POST /v1/colaboradores/importar` so registra a execucao (`importacoes`) e
enfileira: o processamento linha a linha roda no worker
(`apps/worker/worker/tarefas/importacoes.py`), nunca dentro do request --
`events.yaml` declara `importacao.concluida` com `origem: worker`.
"""

from __future__ import annotations
