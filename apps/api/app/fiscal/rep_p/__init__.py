"""Cadastro de REP-P e sequência de NSR (F12/A1).

`criarRepP` inicializa `nsr_sequencias` (`proximo_nsr=1`,
`ultimo_nsr_emitido=0`) na mesma transação em que cria a linha de `rep_ps` —
é o único lugar do sistema que ESCREVE em `nsr_sequencias` fora de
`app.marcacao.dominio.nsr.alocar_nsr`/`fechar_nsr` (F5), e só a linha
inicial: a alocação em si nunca é feita por este módulo.
"""

from __future__ import annotations
