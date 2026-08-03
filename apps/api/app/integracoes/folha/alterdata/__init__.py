"""Exportador para o sistema Alterdata Departamento Pessoal, parceiro
`alterdata` do enum `IntegracaoFolha.parceiro` (F13/A5, T16).

**O único parceiro desta fase com posição de campo pública e verificável**
(PCF F13 secao 6, T16) -- ver `layout.py` para a tabela completa e a fonte
exata. Este e o exportador que pode legitimamente ser descrito como
"validado contra layout de referencia do parceiro" no relatorio final da
fase (PCF secao 7, criterio de aceite 3).
"""

from __future__ import annotations

from app.integracoes.folha.alterdata.layout import gerar
from app.integracoes.folha.comum import registro

registro.registrar("alterdata", gerar)

__all__ = ["gerar"]
