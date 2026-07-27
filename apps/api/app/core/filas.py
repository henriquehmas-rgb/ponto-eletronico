"""Nome da fila padrao do ARQ, duplicado de proposito de
`apps/worker/worker/filas.py::FILA_PADRAO`.

`apps/api` nao pode importar `apps/worker` (duas imagens Docker separadas,
sentido contrario da instalacao decidida em ADR-009 -- so o worker instala a
api como biblioteca, nunca o inverso). Mesma razao/precedente que
`apps/worker/worker/tarefas/importacoes.py` ja documenta para os validadores
de CPF/PIS duplicados: constante pequena e estavel, risco de desalinhamento
baixo, custo de uma dependencia cruzada nova mais alto.

Achado real (F9b/A3, corrigido pelo orquestrador): todo `pool.enqueue_job(...)`
desta base de codigo que cria seu proprio `ArqRedis` via `create_pool(...)`
SEM passar `default_queue_name=FILA_PADRAO` enfileira silenciosamente na fila
embutida padrao do ARQ (`"arq:queue"`), que nenhum worker real escuta --
`worker.main.WorkerSettings.queue_name` e' `FILA_PADRAO` ("ponto:padrao"), nao
o default do ARQ. O job fica orfao no Redis, sem erro nem log de falha em
lugar nenhum. Corrigido em todo `create_pool(...)` de `apps/api` passando
`default_queue_name=FILA_PADRAO` explicitamente -- nao em cada
`enqueue_job()` individual, para nao repetir o mesmo esquecimento em toda
chamada nova futura.

Se o valor mudar em `apps/worker/worker/filas.py`, muda aqui tambem no mesmo
commit -- e a unica obrigacao de sincronia desta duplicacao.
"""

from __future__ import annotations

from typing import Final

FILA_PADRAO: Final[str] = "ponto:padrao"
