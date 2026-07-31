"""Conformidade REP-P (Portaria MTP 671/2021): AFD, AEJ, assinatura CAdES e
cofre de arquivos fiscais (F12).

Três submódulos, três agentes, três responsabilidades que nunca se
confundem (ver `docs/fases/F12-conformidade-rep-p.md` §1):

- `app.fiscal.rep_p` / `app.fiscal.afd` (A1): cadastro de REP-P e gerador do
  Arquivo Fonte de Dados, que deriva EXCLUSIVAMENTE das marcações — nenhum
  tratamento entra aqui.
- `app.fiscal.aej` (A2): gerador do Arquivo Eletrônico de Jornada, que É
  quem enxerga tratamento, ausência, horário contratual e banco de horas.
- `app.fiscal.assinatura` / `app.fiscal.cofre` (A3): assinatura CAdES em
  `.p7s` destacado e o cofre de arquivos fiscais (listagem, obtenção,
  download, histórico de assinatura).

`app.fiscal.comum` é módulo de fronteira entre A1 e A2 (criado por A1 na
T1, importado por A2, nunca editado por A2) — formatação de data/hora e
montagem de arquivo texto, idênticas nos dois leiautes.
"""

from __future__ import annotations
