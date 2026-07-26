"""Carregamento da chave RS256 do access token.

A chave privada NUNCA e literal no codigo nem versionada: vem de arquivo
apontado por `Configuracao.jwt_private_key_path` (variavel de ambiente
`JWT_PRIVATE_KEY_PATH`, ja prevista em `app/core/config.py` desde a Fase 0).
Em desenvolvimento e teste, o arquivo e gerado localmente com
`openssl genpkey` e descartado; em producao vem de `/run/secrets/jwt/private.pem`
(compose), como documenta o PCF desta fase.

O cache (`functools.lru_cache`) existe para nao reler o arquivo a cada
requisicao. Testes que trocam a chave em tempo de execucao devem chamar
`limpar_cache()` apos apontar `JWT_PRIVATE_KEY_PATH`/`JWT_PUBLIC_KEY_PATH` para
um par novo.
"""

from __future__ import annotations

import functools
import pathlib

from app.core.config import obter_configuracao


class ChaveJwtAusente(RuntimeError):
    """A configuracao nao aponta para um arquivo de chave utilizavel."""


def _ler(caminho: str, rotulo: str) -> str:
    if not caminho:
        raise ChaveJwtAusente(
            f"{rotulo} nao configurado. Defina JWT_PRIVATE_KEY_PATH e "
            "JWT_PUBLIC_KEY_PATH apontando para um par RS256 (ver "
            "infra/.env.example)."
        )
    arquivo = pathlib.Path(caminho)
    if not arquivo.is_file():
        raise ChaveJwtAusente(f"{rotulo}: arquivo nao encontrado em {caminho!r}.")
    return arquivo.read_text(encoding="utf-8")


@functools.lru_cache(maxsize=1)
def chave_privada() -> str:
    config = obter_configuracao()
    return _ler(config.jwt_private_key_path, "JWT_PRIVATE_KEY_PATH")


@functools.lru_cache(maxsize=1)
def chave_publica() -> str:
    config = obter_configuracao()
    return _ler(config.jwt_public_key_path, "JWT_PUBLIC_KEY_PATH")


def limpar_cache() -> None:
    """Descarta as chaves em cache. Uso exclusivo de teste."""
    chave_privada.cache_clear()
    chave_publica.cache_clear()
