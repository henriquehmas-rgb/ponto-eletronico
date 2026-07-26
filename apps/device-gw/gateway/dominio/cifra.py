"""Decifragem de `terminais.senha_api_cifrada` (AES-256-GCM).

Copia deliberada de `apps/api/app/terminais/cifra.py` -- os dois modulos
cifram/decifram com a MESMA variavel de ambiente (`PONTO_TERMINAL_CHAVE_MESTRA`)
e o MESMO empacotamento (`iv (12 bytes) || ciphertext||tag`), porque a API
cifra a senha na escrita (`POST/PATCH /v1/terminais`) e o `device-gw` decifra
para abrir sessao no equipamento real (`login.fcgi`) -- e o unico ponto do
gateway que toca a senha do terminal, e so em memoria, pelo tempo minimo
necessario para autenticar.

Nao ha tabela nova nem migration aqui: `terminais.senha_api_cifrada` e uma
unica coluna `BYTEA` (`packages/contracts/schema.sql`, secao 6), sem coluna de
IV separada -- por isso o IV viaja embutido no mesmo blob.
"""

from __future__ import annotations

import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

VARIAVEL_CHAVE_MESTRA = "PONTO_TERMINAL_CHAVE_MESTRA"
_TAMANHO_IV_BYTES = 12
_TAMANHO_CHAVE_BYTES = 32


class ChaveTerminalAusente(RuntimeError):
    """`PONTO_TERMINAL_CHAVE_MESTRA` ausente ou com formato invalido."""


def _chave_bruta() -> bytes:
    valor_hex = os.environ.get(VARIAVEL_CHAVE_MESTRA)
    if not valor_hex:
        raise ChaveTerminalAusente(
            f"{VARIAVEL_CHAVE_MESTRA} nao definido. Gere uma com "
            "`openssl rand -hex 32` e exporte no ambiente (nunca versione)."
        )
    try:
        chave = bytes.fromhex(valor_hex)
    except ValueError as exc:
        raise ChaveTerminalAusente(f"{VARIAVEL_CHAVE_MESTRA} nao e hexadecimal valido.") from exc
    if len(chave) != _TAMANHO_CHAVE_BYTES:
        raise ChaveTerminalAusente(
            f"{VARIAVEL_CHAVE_MESTRA} precisa ter {_TAMANHO_CHAVE_BYTES} bytes "
            f"({_TAMANHO_CHAVE_BYTES * 2} caracteres hex); tem {len(chave)}."
        )
    return chave


def decifrar_senha(blob: bytes) -> str:
    """Decifra `terminais.senha_api_cifrada`. Levanta `InvalidTag` (da
    biblioteca `cryptography`) se o blob estiver corrompido -- nunca devolve
    um valor errado silenciosamente."""
    iv, cifrado = blob[:_TAMANHO_IV_BYTES], blob[_TAMANHO_IV_BYTES:]
    return AESGCM(_chave_bruta()).decrypt(iv, cifrado, None).decode("utf-8")
