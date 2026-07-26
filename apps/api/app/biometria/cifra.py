"""Envelope encryption do template biometrico (ADR-006, decisao fechada).

Regras que este modulo implementa e que NAO se redecidem:

1. **AES-256-GCM** com uma chave de dados (DEK) por tenant. A DEK nunca e
   persistida: e derivada por HKDF-SHA256 a partir da chave mestra (KEK) mais
   o `tenant_id`, o que da "uma DEK por tenant" (ADR-006 regra 1) sem exigir
   uma tabela nova para guardar DEK cifrada -- `schema.sql` nao tem essa
   tabela e esta fase nao cria migration (secao 9 do PCF). `chave_id` guarda a
   versao da KEK usada, para rotacao futura.
2. A **KEK** vive fora do PostgreSQL: variavel de ambiente
   `PONTO_BIOMETRIA_CHAVE_MESTRA`, hexadecimal de 64 caracteres (32 bytes) --
   em `dev`/`hml` montada por volume, em `prd` um cofre gerenciado (fora do
   escopo desta fase). O banco jamais guarda a KEK nem a DEK.
3. Os **dados associados (AAD)** da cifra incluem `tenant_id` e
   `colaborador_id`: decifrar um template com o AAD de outra pessoa falha
   (`InvalidTag`), nunca devolve um vetor errado silenciosamente.
4. GCM entrega autenticacao: qualquer alteracao de um byte do texto cifrado
   ou da tag falha a decifragem.

Nada aqui persiste a imagem crua nem o vetor em claro -- essas duas coisas
vivem apenas em memoria, pelo tempo mínimo necessario para cifrar.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from uuid import UUID

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

__all__ = [
    "ALGORITMO_CIFRA",
    "TAMANHO_TAG_BYTES",
    "ChaveMestraAusente",
    "CifraResultado",
    "TemplateIlegivel",
    "chave_id_atual",
    "cifrar_vetor",
    "decifrar_vetor",
]

#: Nome da variavel de ambiente que guarda a KEK (64 chars hex = 32 bytes).
#: Fora do banco por decisao do ADR-006 -- nunca versionar valor real aqui.
_VAR_CHAVE_MESTRA = "PONTO_BIOMETRIA_CHAVE_MESTRA"

#: Identificador de versao da KEK corrente. Rotacionar a chave (F14) sobe este
#: valor; `biometria_templates.chave_id` grava qual versao cifrou cada linha,
#: permitindo conviver com templates cifrados por KEKs diferentes.
_VERSAO_KEK_ATUAL = "kek-v1"

ALGORITMO_CIFRA = "AES-256-GCM"
#: GCM padrao: nonce de 96 bits, tag de autenticacao de 128 bits.
_TAMANHO_NONCE_BYTES = 12
TAMANHO_TAG_BYTES = 16


class ChaveMestraAusente(RuntimeError):
    """`PONTO_BIOMETRIA_CHAVE_MESTRA` ausente ou com formato invalido."""


class TemplateIlegivel(RuntimeError):
    """Falha de autenticacao GCM: texto cifrado, tag ou AAD nao conferem.

    Cobre tanto corrupcao do dado quanto a tentativa de decifrar o template de
    um colaborador usando o AAD de outro -- o caso que o ADR-006 exige que
    falhe, em vez de devolver um vetor errado.
    """


@dataclass(frozen=True, slots=True)
class CifraResultado:
    """O que `biometria_templates` grava: nunca a chave, nunca o vetor cru."""

    template_cifrado: bytes
    iv: bytes
    tag_autenticacao: bytes
    chave_id: str
    algoritmo_cifra: str = ALGORITMO_CIFRA


def chave_id_atual() -> str:
    """Identificador de versao da KEK usada agora, gravado em `chave_id`."""
    return _VERSAO_KEK_ATUAL


def _kek_bytes() -> bytes:
    """Le a chave mestra do ambiente. Nunca cacheia em modulo-nivel para que
    testes possam trocar a variavel entre casos sem reiniciar o processo."""
    valor = os.environ.get(_VAR_CHAVE_MESTRA, "")
    if not valor:
        raise ChaveMestraAusente(
            f"Variavel de ambiente {_VAR_CHAVE_MESTRA} ausente. A chave mestra "
            "vive fora do banco (ADR-006): monte-a por volume/segredo, nunca "
            "a versione."
        )
    try:
        bruta = bytes.fromhex(valor)
    except ValueError as exc:
        raise ChaveMestraAusente(
            f"{_VAR_CHAVE_MESTRA} precisa ser hexadecimal (openssl rand -hex 32)."
        ) from exc
    if len(bruta) != 32:
        raise ChaveMestraAusente(
            f"{_VAR_CHAVE_MESTRA} precisa ter 32 bytes (64 caracteres hex); "
            f"recebeu {len(bruta)} bytes."
        )
    return bruta


def _derivar_dek(tenant_id: UUID) -> bytes:
    """DEK por tenant (ADR-006 regra 1), derivada da KEK via HKDF-SHA256.

    HKDF com `info=tenant_id` produz uma chave de 32 bytes determinística por
    tenant sem precisar persistir a DEK cifrada em lugar nenhum: quem tem a
    KEK recalcula a DEK; quem so tem o dump do banco nao tem nenhuma das duas.
    """
    hkdf = HKDF(
        algorithm=SHA256(),
        length=32,
        salt=b"ponto-eletronico:biometria:dek",
        info=str(tenant_id).encode("ascii"),
    )
    return hkdf.derive(_kek_bytes())


def _aad(tenant_id: UUID, colaborador_id: UUID) -> bytes:
    """Dados associados: amarram o texto cifrado a ESTE tenant e ESTE
    colaborador. Trocar qualquer um dos dois faz a decifragem falhar."""
    return f"{tenant_id}:{colaborador_id}".encode("ascii")


def cifrar_vetor(*, tenant_id: UUID, colaborador_id: UUID, vetor: bytes) -> CifraResultado:
    """Cifra o vetor biometrico em claro. `vetor` nunca deve ser logado."""
    dek = _derivar_dek(tenant_id)
    nonce = os.urandom(_TAMANHO_NONCE_BYTES)
    aesgcm = AESGCM(dek)
    cifrado_com_tag = aesgcm.encrypt(nonce, vetor, _aad(tenant_id, colaborador_id))
    # `AESGCM.encrypt` devolve ciphertext||tag; o schema guarda as duas partes
    # em colunas separadas (`template_cifrado`, `tag_autenticacao`).
    texto_cifrado = cifrado_com_tag[:-TAMANHO_TAG_BYTES]
    tag = cifrado_com_tag[-TAMANHO_TAG_BYTES:]
    return CifraResultado(
        template_cifrado=texto_cifrado,
        iv=nonce,
        tag_autenticacao=tag,
        chave_id=chave_id_atual(),
    )


def decifrar_vetor(
    *,
    tenant_id: UUID,
    colaborador_id: UUID,
    template_cifrado: bytes,
    iv: bytes,
    tag_autenticacao: bytes,
) -> bytes:
    """Decifra o vetor. Levanta `TemplateIlegivel` se AAD, IV ou tag nao
    conferem -- inclusive quando alguem tenta usar o AAD de outro
    colaborador."""
    dek = _derivar_dek(tenant_id)
    aesgcm = AESGCM(dek)
    try:
        return aesgcm.decrypt(
            iv,
            template_cifrado + tag_autenticacao,
            _aad(tenant_id, colaborador_id),
        )
    except InvalidTag as exc:
        raise TemplateIlegivel(
            "Falha de autenticacao ao decifrar o template biometrico: dado "
            "corrompido ou AAD (tenant/colaborador) incompativel."
        ) from exc
