"""Pacote `app.workflow.aprovacoes`: fila de aprovação, decisão de etapa e
delegação temporária (F10, agente A1) -- PCF §5.

`servico.py` (`listarAprovacoesPendentes`/`decidirAprovacao`),
`resolucao.py` (resolução do aprovador pré-atribuído de uma etapa via
`colaborador_gestores`, F2) e `delegacoes.py`
(`listarDelegacoes`/`criarDelegacao`, e `delegacao_vigente` para consulta
interna) -- ownership exclusivo de A1.
"""

from __future__ import annotations
