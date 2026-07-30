"""Fechamento de período, espelho de ponto e assinatura eletrônica (F10/A2).

Sequência do subpacote (PCF F10 §2, §6 T5-T9):

    períodos (`periodos.py`)
      -> conferência prévia (`conferencia.py`)
      -> fechamento -- trava a apuração (`servico.py`, materializado de fato
         pela tarefa assíncrona `apps/worker/worker/tarefas/fechamento.py`)
      -> espelho de ponto -- JSON + hash + PDF (`espelho.py`, `pdf.py`)
      -> assinatura eletrônica do colaborador (`assinatura.py`)

Este subpacote nunca escreve em `apuracoes_dia`, `apuracao_componentes` nem
`bh_lancamentos` fora de leitura; a trava de período em si
(`verificar_periodo_aberto`) já existe e já funciona, entregue pela F4
(`app.apuracao.tratamento.fechamento`) -- este pacote só cria a linha de
`Fechamento` que ativa essa trava (§2.6 do PCF).
"""

from __future__ import annotations
