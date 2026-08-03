"""Envelope encryption de `webhooks.segredo_hmac_cifrado` (AES-256-GCM).

COPIA deliberada de `apps/api/app/terminais/cifra.py` (T9 do PCF da F13 pede
explicitamente essa copia: "cópia deliberada do padrão de
`apps/api/app/terminais/cifra.py`") -- mesmo algoritmo, mesmo empacotamento
`iv (12 bytes) || ciphertext || tag`, mesma variavel de ambiente por dominio
(`PONTO_WEBHOOK_CHAVE_MESTRA`, hex de 32 bytes, nunca versionada) e mesmo
`chave_id` fixo por versao da chave mestra (`webh-v1`).

Por que uma copia e nao um import de `app.terminais.cifra`
-------------------------------------------------------------
Chave mestra PROPRIA por dominio (nunca a mesma de `terminais`/`biometria`/
`mfa`): um vazamento da chave mestra de terminal nao deve permitir forjar
assinatura de webhook, e vice-versa. Mesmo raciocinio de isolamento que already
levou `app/biometria/cifra.py` e `app/identidade/mfa/cifra.py` a serem copias
irmas, nao um modulo compartilhado.

O segredo em claro (`segredoHmac`) so aparece UMA VEZ, na resposta de
`criarWebhook` (`WebhookCriado.segredoHmac`) -- nunca em log, nunca em
resposta de leitura subsequente. `decifrar_segredo` e uso exclusivo do worker
(assinar o corpo na entrega) e de teste.
"""

from __future__ import annotations

import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

__all__ = [
    "CHAVE_ID_ATUAL",
    "VARIAVEL_CHAVE_MESTRA",
    "ChaveWebhookAusente",
    "cifrar_segredo",
    "decifrar_segredo",
]

VARIAVEL_CHAVE_MESTRA = "PONTO_WEBHOOK_CHAVE_MESTRA"
#: Versao da chave mestra corrente, gravada em `webhooks.chave_id`.
CHAVE_ID_ATUAL = "webh-v1"
_TAMANHO_IV_BYTES = 12
_TAMANHO_CHAVE_BYTES = 32


class ChaveWebhookAusente(RuntimeError):
    """`PONTO_WEBHOOK_CHAVE_MESTRA` ausente ou com formato invalido."""


def _chave_bruta() -> bytes:
    """Nunca cacheia em modulo-nivel: testes trocam a variavel entre casos."""
    valor_hex = os.environ.get(VARIAVEL_CHAVE_MESTRA)
    if not valor_hex:
        raise ChaveWebhookAusente(
            f"{VARIAVEL_CHAVE_MESTRA} nao definido. Gere uma com "
            "`openssl rand -hex 32` e exporte no ambiente (nunca versione)."
        )
    try:
        chave = bytes.fromhex(valor_hex)
    except ValueError as exc:
        raise ChaveWebhookAusente(f"{VARIAVEL_CHAVE_MESTRA} nao e hexadecimal valido.") from exc
    if len(chave) != _TAMANHO_CHAVE_BYTES:
        raise ChaveWebhookAusente(
            f"{VARIAVEL_CHAVE_MESTRA} precisa ter {_TAMANHO_CHAVE_BYTES} bytes "
            f"({_TAMANHO_CHAVE_BYTES * 2} caracteres hex); tem {len(chave)}."
        )
    return chave


def cifrar_segredo(segredo: str) -> tuple[bytes, str]:
    """Cifra o segredo HMAC gerado na criacao do webhook.
    Devolve `(blob_empacotado, chave_id)` para gravar em
    `segredo_hmac_cifrado`/`chave_id`. `segredo` nunca deve ser logado."""
    iv = os.urandom(_TAMANHO_IV_BYTES)
    cifrado = AESGCM(_chave_bruta()).encrypt(iv, segredo.encode("utf-8"), None)
    return iv + cifrado, CHAVE_ID_ATUAL


def decifrar_segredo(blob: bytes) -> str:
    """Decifra o blob gravado em `segredo_hmac_cifrado`. Uso exclusivo do
    worker (assinatura HMAC na entrega, `enviar_webhook`) e de teste -- nenhuma
    leitura da API devolve o segredo em claro de novo."""
    iv, cifrado = blob[:_TAMANHO_IV_BYTES], blob[_TAMANHO_IV_BYTES:]
    return AESGCM(_chave_bruta()).decrypt(iv, cifrado, None).decode("utf-8")


def gerar_segredo() -> str:
    """Gera um novo segredo HMAC (256 bits, URL-safe) para `criarWebhook`."""
    import secrets

    return secrets.token_urlsafe(32)
