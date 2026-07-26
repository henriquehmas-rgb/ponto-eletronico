"""Pertencimento de IP a allowlist CIDR (`redes_permitidas`).

`ipaddress`, da biblioteca padrao, ja resolve IPv4 e IPv6 de forma uniforme:
`ip_address` aceita as duas familias e o operador `in` sobre `ip_network`
implementa exatamente o mesmo teste de contencao que o operador `>>=` do tipo
`CIDR` do PostgreSQL usa em `ix_redes_permitidas_lookup`.

Este modulo e puro. A F2 cadastra a allowlist e expoe esta funcao; **aplicar**
a regra no momento de bater ponto e da F8.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass

from app.core.erros import ErroDeAplicacao


@dataclass(frozen=True, slots=True)
class FaixaPermitida:
    """Uma linha de `redes_permitidas`, so com o que a verificacao precisa."""

    cidr: str
    ativo: bool = True


def ip_valido(ip: str) -> bool:
    """`True` quando `ip` e um endereco IPv4 ou IPv6 sintaticamente valido."""
    try:
        ipaddress.ip_address(ip)
    except ValueError:
        return False
    return True


def cidr_valido(cidr: str) -> bool:
    """`True` quando `cidr` e uma faixa IPv4 ou IPv6 sintaticamente valida."""
    try:
        ipaddress.ip_network(cidr, strict=False)
    except ValueError:
        return False
    return True


def ip_autorizado(faixas: list[FaixaPermitida], ip: str) -> bool:
    """`True` quando `ip` pertence a alguma faixa ativa de `faixas`.

    `faixas` ja deve chegar filtrada pelo escopo (empresa, unidade opcional,
    canal opcional) -- este modulo so decide a contencao IP-em-CIDR, nao
    resolve escopo.
    """
    try:
        endereco = ipaddress.ip_address(ip)
    except ValueError as exc:
        raise ErroDeAplicacao("PONTO-VAL-005", detalhe=f"IP de origem invalido: {ip!r}") from exc

    for faixa in faixas:
        if not faixa.ativo:
            continue
        rede = ipaddress.ip_network(faixa.cidr, strict=False)
        # Familias diferentes (IPv4 vs IPv6) nunca se contem; `in` levantaria
        # TypeError em algumas versoes do modulo se comparadas diretamente.
        if endereco.version != rede.version:
            continue
        if endereco in rede:
            return True
    return False
