"""Cofre de arquivos fiscais (F12/A3, T12).

Listagem, obtencao de metadados e download de AFD/AEJ ja gerados
(`app.fiscal.afd`/`app.fiscal.aej`, A1/A2 -- este pacote so LE
`afd_arquivos`/`aej_arquivos`, nunca gera conteudo). O download devolve os
bytes exatamente como gravados (ISO-8859-1, sem reencodar) e registra a
trilha de auditoria.
"""

from __future__ import annotations
