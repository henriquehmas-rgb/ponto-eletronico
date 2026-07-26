"""Hash e verificacao de senha em Argon2id.

Parametros deliberadamente documentados aqui (nao apenas "padrao da biblioteca"),
porque a formula de custo e decisao de seguranca, nao detalhe de implementacao:

* `time_cost=3`      -- 3 iteracoes internas.
* `memory_cost=65536` -- 64 MiB por hash. Alto o suficiente para encarecer
  ataque por GPU/ASIC, baixo o suficiente para nao afogar o processo da API
  sob concorrencia de login.
* `parallelism=2`     -- graus de paralelismo interno do Argon2id.

Estes valores seguem a recomendacao da OWASP Password Storage Cheat Sheet para
Argon2id (perfil "segunda opcao", adequado a um servico web com CPU
compartilhada). `credenciais.algoritmo = 'argon2id'` e o unico algoritmo usado
para senha nova; `bcrypt`/`scrypt`/`pbkdf2` seguem previstos no CHECK do
contrato apenas para migracao de base legada (nao escritos por este modulo).
"""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

ALGORITMO = "argon2id"

_TIME_COST = 3
_MEMORY_COST_KIB = 64 * 1024
_PARALELISMO = 2
_TAMANHO_HASH = 32
_TAMANHO_SAL = 16

_hasher = PasswordHasher(
    time_cost=_TIME_COST,
    memory_cost=_MEMORY_COST_KIB,
    parallelism=_PARALELISMO,
    hash_len=_TAMANHO_HASH,
    salt_len=_TAMANHO_SAL,
)


def gerar_hash(segredo: str) -> str:
    """Gera o hash Argon2id de uma senha (ou de qualquer segredo textual)."""
    return _hasher.hash(segredo)


def verificar_hash(hash_armazenado: str, segredo_informado: str) -> bool:
    """Compara o segredo informado com o hash em tempo constante.

    Nunca levanta excecao para fora deste modulo: hash corrompido ou segredo
    errado sao a mesma resposta (`False`) do ponto de vista do chamador, o que
    e exatamente o comportamento que impede oraculo de erro.
    """
    try:
        return _hasher.verify(hash_armazenado, segredo_informado)
    except (VerifyMismatchError, InvalidHashError, VerificationError):
        return False


def precisa_rehash(hash_armazenado: str) -> bool:
    """Verdadeiro quando os parametros de custo do hash estao desatualizados."""
    try:
        return _hasher.check_needs_rehash(hash_armazenado)
    except InvalidHashError:
        return True
