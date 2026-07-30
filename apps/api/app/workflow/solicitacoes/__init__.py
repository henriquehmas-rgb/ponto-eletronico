"""Pacote `app.workflow.solicitacoes`: motor de solicitações (F10, agente A1).

`tipos.py`/`servico.py` (CRUD de tipos de solicitação e solicitações),
`materializacao.py` (despachante genérico que cria `Tratamento` para as
categorias com `tipo_tratamento_id`) e `eventos.py` (`ajuste.aprovado`/
`ajuste.reprovado` para as categorias que não passam por `decidir_tratamento`
de F4) são ownership de A1 (PCF F10 §5). `afastamentos.py` (ramo
`ferias`/`folga` do mesmo despachante) é o único arquivo deste pacote com
ownership de A4.

Nota de execução: este arquivo (`__init__.py`, docstring e nada mais) é
ownership de A1 (T1/T2, "todos os demais dependem desta tarefa"); foi criado
aqui por A4 porque não existia no momento em que T12 foi executada nesta
sessão (os quatro agentes da fase rodam em paralelo -- mesmo precedente já
documentado por `apps/api/tests/f4/tratamento/conftest.py` e por
`apps/api/app/workflow/__init__.py`, que A2 já enfrentou e resolveu da mesma
forma). Conteúdo estritamente estrutural (nenhum código); se A1 também criar
este arquivo em paralelo, é um conflito trivial de merge para o orquestrador
reconciliar.
"""

from __future__ import annotations
