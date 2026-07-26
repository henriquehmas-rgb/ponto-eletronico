"""Codigos de backup de MFA, de uso unico.

Guardados como um blob JSON (lista de hashes SHA-256 + flag de uso), cifrado
em AES-256-GCM do mesmo jeito que o segredo TOTP
(`mfa_dispositivos.tipo = 'codigos_backup'`, `segredo_cifrado`/`iv`). Os
codigos em claro so existem na resposta de geracao -- nunca sao persistidos
nem logados.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from dataclasses import dataclass

from app.identidade.mfa.cifra import CHAVE_ID_PADRAO, cifrar, decifrar

QUANTIDADE_CODIGOS = 10
TAMANHO_CODIGO = 10
#: Sem caracteres ambiguos (I/1, O/0).
_ALFABETO = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _gerar_codigo() -> str:
    return "".join(secrets.choice(_ALFABETO) for _ in range(TAMANHO_CODIGO))


def _normalizar(codigo: str) -> str:
    return codigo.strip().upper().replace("-", "").replace(" ", "")


def _hash(codigo: str) -> str:
    return hashlib.sha256(_normalizar(codigo).encode("ascii")).hexdigest()


@dataclass(frozen=True, slots=True)
class LoteGerado:
    codigos_em_claro: list[str]
    cifrado: bytes
    iv: bytes
    chave_id: str


def gerar_lote() -> LoteGerado:
    codigos = [_gerar_codigo() for _ in range(QUANTIDADE_CODIGOS)]
    estado = {"codigos": [{"hash": _hash(c), "usado": False} for c in codigos]}
    cifrado, iv = cifrar(json.dumps(estado).encode("utf-8"))
    return LoteGerado(codigos_em_claro=codigos, cifrado=cifrado, iv=iv, chave_id=CHAVE_ID_PADRAO)


@dataclass(frozen=True, slots=True)
class ResultadoConsumo:
    sucesso: bool
    cifrado: bytes
    iv: bytes
    restantes: int


def consumir(cifrado: bytes, iv: bytes, chave_id: str, codigo_informado: str) -> ResultadoConsumo:
    """Tenta consumir um codigo. Idempotente em falha: nunca reescreve o blob sem sucesso."""
    estado = json.loads(decifrar(cifrado, iv, chave_id=chave_id).decode("utf-8"))
    hash_informado = _hash(codigo_informado)
    encontrado = False
    for item in estado["codigos"]:
        if item["hash"] == hash_informado and not item["usado"]:
            item["usado"] = True
            encontrado = True
            break
    if not encontrado:
        restantes = sum(1 for item in estado["codigos"] if not item["usado"])
        return ResultadoConsumo(sucesso=False, cifrado=cifrado, iv=iv, restantes=restantes)
    novo_cifrado, novo_iv = cifrar(json.dumps(estado).encode("utf-8"), chave_id=chave_id)
    restantes = sum(1 for item in estado["codigos"] if not item["usado"])
    return ResultadoConsumo(sucesso=True, cifrado=novo_cifrado, iv=novo_iv, restantes=restantes)
