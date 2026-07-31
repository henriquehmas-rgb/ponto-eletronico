"""Canais de entrega do agendamento de relatório (F11, T11/A3).

`relatorio_agendamentos.canal` é `email`, `webhook` ou `minio`
(`schema.sql` §16). Cada canal expõe a MESMA assinatura, fixada por
`docs/fases/F11-relatorios-espelho-exportacoes.md` §6/T11::

    async def entregar(execucao: RelatorioExecucao, agendamento: RelatorioAgendamento) -> bool

`executar_relatorio` (worker, `apps/worker/worker/tarefas/relatorios.py`)
chama `entregar(...)` do canal certo ao final de uma execução com
`agendamento_id` preenchido (T6, combinado com A1). Devolve `True` quando a
entrega foi tentada com sucesso (registrada), `False` em falha conhecida --
NUNCA levanta exceção para uma falha de entrega não impedir o
`RelatorioExecucao.status='concluido'` já alcançado (o arquivo já existe no
MinIO; falhar a notificação de entrega não deveria apagar o trabalho feito).

Nenhum dos três canais é o mecanismo completo de outra fase: `email.py` é o
MESMO tipo de adaptador provisório que `app.notificacao.canais.email` (F10)
já usa (log + marca como entregue, sem credencial SMTP real, PCF §2.9),
`webhook.py` é um `POST` HTTP simples (não a assinatura HMAC/retentativa/DLQ
da tag `webhooks`, F13) e `minio.py` é um no-op documentado (o arquivo já
está no MinIO ao final da execução -- "entregar" por este canal só confirma).
Nenhum dos três importa o módulo homônimo de outra fase (`app.notificacao.
canais.email`) -- disciplina própria, mesmo padrão que `docs/fases/
F11-relatorios-espelho-exportacoes.md` §5 já fixa para `entrega/email.py`
(A3) vs. `entrega/espelho_email.py` (A4).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ponto_contracts import RelatorioAgendamento, RelatorioExecucao

Entregador = Callable[["RelatorioExecucao", "RelatorioAgendamento"], Awaitable[bool]]

__all__ = ["Entregador"]
