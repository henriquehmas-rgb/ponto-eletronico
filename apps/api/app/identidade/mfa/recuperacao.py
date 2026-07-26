"""Recuperacao de senha por token de uso unico.

O token vive como uma linha de `credenciais` (`tipo = 'recuperacao'`,
`algoritmo = 'nenhum'` -- nao e uma senha, e um segredo de posse de e-mail).
`credenciais.hash` guarda o SHA-256 do token (comparacao de posse, nao de
memoria humana: nao ha por que pagar o custo do Argon2id aqui). A unicidade
parcial `uq_credenciais_ativa (tenant_id, usuario_id, tipo) WHERE ativo`
garante no maximo um token de recuperacao ativo por usuario: pedir de novo
desativa o anterior.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import secrets
from dataclasses import dataclass

ALGORITMO = "nenhum"
VIDA_TOKEN = _dt.timedelta(minutes=30)


@dataclass(frozen=True, slots=True)
class TokenGerado:
    token: str
    hash: str
    expira_em: _dt.datetime


def gerar(agora: _dt.datetime | None = None) -> TokenGerado:
    agora = agora or _dt.datetime.now(_dt.UTC)
    bruto = secrets.token_urlsafe(32)
    return TokenGerado(token=bruto, hash=hash_token(bruto), expira_em=agora + VIDA_TOKEN)


def hash_token(token_bruto: str) -> str:
    return hashlib.sha256(token_bruto.encode("utf-8")).hexdigest()
