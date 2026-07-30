"""Pacote `app.workflow`: motor de solicitações, aprovações e fechamento (F10).

Docstring e nada mais (PCF F10, §5, T1) -- os subpacotes carregam a lógica:
`app.workflow.solicitacoes` (A1: tipos de solicitação, solicitações, o
despachante genérico de materialização; A4: o ramo `ferias`/`folga`),
`app.workflow.aprovacoes` (A1: fila de aprovação, decisão de etapa,
delegações) e `app.workflow.fechamento` (A2: períodos, conferência,
fechamento, espelho e assinatura eletrônica).

Nota de execução: este arquivo é ownership de A1 (T1, "todos os demais
dependem desta tarefa"); ele foi criado aqui por A2 porque não existia no
momento em que T5-T9 foram executadas nesta sessão (os quatro agentes da
fase rodam em paralelo -- mesmo precedente já documentado por
`apps/api/tests/f4/tratamento/conftest.py`, que também não bloqueia na
ordem de chegada de outra tarefa/agente). Conteúdo estritamente o combinado
pelo PCF (docstring, nenhum código); se A1 também criar este arquivo em
paralelo, é um conflito trivial de merge para o orquestrador reconciliar.
"""

from __future__ import annotations
