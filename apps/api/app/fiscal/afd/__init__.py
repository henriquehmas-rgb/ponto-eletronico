"""Gerador do Arquivo Fonte de Dados (AFD) do REP-P (F12/A1).

Deriva EXCLUSIVAMENTE das marcações (`marcacoes`) — nenhum tratamento entra
aqui, garantido estruturalmente por `tipos_tratamento.afeta_afd` ter
`CHECK (afeta_afd = FALSE)` (`docs/fases/F12-conformidade-rep-p.md` §2.13).

Texto ASCII ISO-8859-1, largura fixa por posição (SEM delimitador — `|` é
exclusivo do AEJ), linhas terminadas em CR+LF, registros ordenados por NSR
(não por data/hora — ADR-003 consequência (d), exceção deliberada do AFD).
"""

from __future__ import annotations
