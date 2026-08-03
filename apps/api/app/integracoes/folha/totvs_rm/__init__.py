"""Exportador de folha para TOTVS RM. Ver `exportador.py` para o debito
tecnico de fidelidade documentado (T17, agente A6, F13).

`registro.registrar` no import (efeito colateral deliberado, mesmo padrao
que `app.integracoes.folha.comum.registro` documenta e que `app.
integracoes.folha.dominio` ja usa) -- nenhum outro modulo precisa "somar"
este parceiro em nenhuma lista central.
"""

from __future__ import annotations

from app.integracoes.folha.comum import registro
from app.integracoes.folha.totvs_rm.exportador import NOME_EXIBICAO, PARCEIRO, gerar

registro.registrar(PARCEIRO, gerar)

__all__ = ["NOME_EXIBICAO", "PARCEIRO", "gerar"]
