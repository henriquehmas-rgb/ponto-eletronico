"""Workers assincronos do Ponto Eletronico (ARQ sobre Redis 7).

Dois processos saem deste pacote, ambos declarados em
`infra/docker-compose.yml`:

* `worker`    -> `arq worker.main.WorkerSettings` -- consome a fila.
* `scheduler` -> `arq worker.scheduler.SchedulerSettings` -- dispara o que tem
  hora marcada (vencimento de banco de horas, expurgo LGPD, coleta de terminal,
  relatorio agendado).

Fase 0 entrega ANDAIME. As oito tarefas do sistema ja existem com nome, fila e
assinatura definitivos e devolvem um resultado marcado como nao implementado
(`PONTO-INT-005`). Nenhum calculo acontece aqui ainda: a apuracao chega na F4,
os arquivos fiscais na F12, os relatorios na F11 e os webhooks na F13.
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "0.1.0"
