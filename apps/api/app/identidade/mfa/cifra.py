"""Cifra simetrica (AES-256-GCM) para segredos de MFA em repouso.

`mfa_dispositivos.segredo_cifrado`/`iv` guardam o resultado; `chave_id`
referencia QUAL chave cifrou aquele segredo. A chave em si nunca fica no
banco -- este modulo e o "cofre externo" desta fase: le a chave mestra de uma
variavel de ambiente (`PONTO_MFA_CHAVE_MESTRA`, hex de 32 bytes, gerada com
`openssl rand -hex 32` e nunca versionada). Um KMS real (AWS KMS, GCP KMS,
Vault) substitui a leitura de ambiente por uma chamada de rede sem mudar o
formato armazenado (`chave_id` continua identificando a chave; troca de KMS
so precisa reescrever este modulo).
"""

from __future__ import annotations

import functools
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

VARIAVEL_CHAVE_MESTRA = "PONTO_MFA_CHAVE_MESTRA"
CHAVE_ID_PADRAO = "local-v1"
_TAMANHO_IV_BYTES = 12
_TAMANHO_CHAVE_BYTES = 32


class ChaveMfaAusente(RuntimeError):
    """A chave mestra nao esta configurada ou tem tamanho invalido."""


@functools.lru_cache(maxsize=8)
def _chave_bruta(chave_id: str) -> bytes:
    valor_hex = os.environ.get(VARIAVEL_CHAVE_MESTRA)
    if not valor_hex:
        raise ChaveMfaAusente(
            f"{VARIAVEL_CHAVE_MESTRA} nao definido. Gere uma com "
            "`openssl rand -hex 32` e exporte no ambiente (nunca versione)."
        )
    try:
        chave = bytes.fromhex(valor_hex)
    except ValueError as exc:
        raise ChaveMfaAusente(f"{VARIAVEL_CHAVE_MESTRA} nao e hexadecimal valido.") from exc
    if len(chave) != _TAMANHO_CHAVE_BYTES:
        raise ChaveMfaAusente(
            f"{VARIAVEL_CHAVE_MESTRA} precisa ter {_TAMANHO_CHAVE_BYTES} bytes "
            f"({_TAMANHO_CHAVE_BYTES * 2} caracteres hex); tem {len(chave)}."
        )
    return chave


def limpar_cache() -> None:
    """Descarta a chave em cache. Uso exclusivo de teste."""
    _chave_bruta.cache_clear()


def cifrar(segredo: bytes, *, chave_id: str = CHAVE_ID_PADRAO) -> tuple[bytes, bytes]:
    """Devolve `(cifrado, iv)`. Um IV novo e sorteado a cada chamada."""
    iv = os.urandom(_TAMANHO_IV_BYTES)
    cifrado = AESGCM(_chave_bruta(chave_id)).encrypt(iv, segredo, None)
    return cifrado, iv


def decifrar(cifrado: bytes, iv: bytes, *, chave_id: str = CHAVE_ID_PADRAO) -> bytes:
    return AESGCM(_chave_bruta(chave_id)).decrypt(iv, cifrado, None)
