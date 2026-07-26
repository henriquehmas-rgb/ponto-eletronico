"""Envelope encryption de `terminais.senha_api_cifrada` (AES-256-GCM).

Mesmo padrao de `app/identidade/mfa/cifra.py` e `app/biometria/cifra.py` (T3
do PCF da F6 pede explicitamente "o mesmo padrao de envelope, ja usado por
..."): chave mestra fora do banco, lida de uma variavel de ambiente
(`PONTO_TERMINAL_CHAVE_MESTRA`, hex de 32 bytes, nunca versionada), AES-256-GCM
com IV novo a cada cifragem.

Diferenca deliberada em relacao a `app/biometria/cifra.py`: `senhaApi` nao e
biometria (ADR-006 nao se aplica aqui) e `terminais` nao tem coluna de IV
separada -- so `senha_api_cifrada BYTEA` e `chave_id TEXT`
(`packages/contracts/schema.sql`, secao 6). Por isso o formato empacota
`iv (12 bytes) || ciphertext||tag` num unico blob, e `chave_id` grava so a
versao da chave mestra usada (para rotacao futura), nao o IV.

Este modulo e uma COPIA deliberada de `apps/device-gw/gateway/dominio/
cifra.py` (mesma variavel de ambiente, mesmo algoritmo, mesmo empacotamento):
a API cifra na escrita, o `device-gw` decifra para abrir sessao no
equipamento real. Os dois processos nao compartilham pacote Python (mesma
razao de `gateway/log.py` duplicar `app/core/log.py`), mas PRECISAM
compartilhar a chave mestra (mesma variavel de ambiente nos dois containers).
"""

from __future__ import annotations

import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

__all__ = [
    "CHAVE_ID_ATUAL",
    "VARIAVEL_CHAVE_MESTRA",
    "ChaveTerminalAusente",
    "cifrar_senha",
    "decifrar_senha",
]

VARIAVEL_CHAVE_MESTRA = "PONTO_TERMINAL_CHAVE_MESTRA"
#: Versao da chave mestra corrente, gravada em `terminais.chave_id`.
CHAVE_ID_ATUAL = "term-v1"
_TAMANHO_IV_BYTES = 12
_TAMANHO_CHAVE_BYTES = 32


class ChaveTerminalAusente(RuntimeError):
    """`PONTO_TERMINAL_CHAVE_MESTRA` ausente ou com formato invalido."""


def _chave_bruta() -> bytes:
    """Nunca cacheia em modulo-nivel: testes trocam a variavel entre casos."""
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


def cifrar_senha(senha: str) -> tuple[bytes, str]:
    """Cifra `senhaApi` recebida em `TerminalCriar`/`TerminalAtualizar`.
    Devolve `(blob_empacotado, chave_id)` para gravar em
    `senha_api_cifrada`/`chave_id`. `senha` nunca deve ser logada."""
    iv = os.urandom(_TAMANHO_IV_BYTES)
    cifrado = AESGCM(_chave_bruta()).encrypt(iv, senha.encode("utf-8"), None)
    return iv + cifrado, CHAVE_ID_ATUAL


def decifrar_senha(blob: bytes) -> str:
    """Decifra o blob gravado em `senha_api_cifrada`. So usado por teste e
    por rotinas internas -- nenhuma leitura da API devolve `senhaApi`."""
    iv, cifrado = blob[:_TAMANHO_IV_BYTES], blob[_TAMANHO_IV_BYTES:]
    return AESGCM(_chave_bruta()).decrypt(iv, cifrado, None).decode("utf-8")
