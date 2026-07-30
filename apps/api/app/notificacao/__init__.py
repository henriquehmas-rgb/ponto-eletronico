"""Pacote `app.notificacao`: motor de notificações multicanal (F10, A3).

Ownership exclusivo de A3 (PCF F10, §5): `motor.py` (regras, resolução de
destinatário, criação das linhas de `notificacoes`), `mensagens.py`
(templates em português por evento), `preferencias.py` (leitura/gravação de
`notificacao_preferencias`, sem rota HTTP nesta fase -- achado de contrato,
PCF §2.7 item 1) e `canais/` (adaptadores de envio por canal: `push`,
`email`, `in_app`).

Dois caminhos de disparo, nunca um "barramento genérico" (PCF §2.7):

1. **Reativo**, para os eventos que a própria F10 publica
   (`ajuste.solicitado`, `ajuste.aprovado`, `ajuste.reprovado`,
   `periodo.fechado`, `periodo.reaberto`, `espelho.assinado`): o código de
   A1/A2/A4 chama `app.notificacao.motor.processar_evento` em processo,
   logo após publicar o envelope local.
2. **Por varredura periódica** (`worker.notificacoes_verificacao`, T11),
   para sinais que nascem em domínios já concluídos (`ocorrencias` de F4) ou
   que não têm evento de domínio correspondente (pendência de aprovação há
   N dias) -- reconstrói um envelope sintético e chama o mesmo
   `processar_evento`.

Nenhum módulo aqui escreve em `apuracoes_dia`, `apuracao_componentes`,
`bh_lancamentos` ou em `tratamentos` fora das funções de F4 (não há
nenhuma razão para isso: notificação nunca corrige jornada).
"""

from __future__ import annotations
