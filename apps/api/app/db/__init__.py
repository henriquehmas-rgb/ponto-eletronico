"""Acesso a dados: engine assincrona, fabrica de sessoes e dependencia FastAPI.

O modelo de dados NAO vive aqui. A fonte da verdade e
`packages/contracts/schema.sql`, traduzida nos models SQLAlchemy do pacote
`ponto_contracts` (`packages/contracts/models/`). Este pacote so cuida da
conexao e do ciclo de vida da sessao.
"""

from __future__ import annotations

from app.db.sessao import (
    SessaoDb,
    encerrar_engine,
    fabrica_de_sessoes,
    obter_engine,
    obter_sessao,
    verificar_banco,
)

__all__ = [
    "SessaoDb",
    "encerrar_engine",
    "fabrica_de_sessoes",
    "obter_engine",
    "obter_sessao",
    "verificar_banco",
]
