"""Validacao de `Webhook.url` para `PONTO-WEBH-001` ("A URL precisa ser
HTTPS, publica e nao apontar para faixa privada ou de loopback",
`packages/contracts/errors.yaml`).

Verificacao ESTATICA sobre o texto da URL (esquema + host), sem resolucao de
DNS: resolver o host abriria uma segunda janela de TOCTOU (o DNS podia mudar
entre a validacao na criacao e a entrega de verdade em `enviar_webhook`,
T12) sem fechar o risco de qualquer forma definitiva -- a defesa completa
contra SSRF via DNS rebinding e reverificar o IP resolvido no momento do
`POST` de entrega, fora do escopo desta validacao de cadastro. Aqui o
objetivo mais estreito e explicito do catalogo de erros: recusar de cara o
cadastro obviamente errado (`http://`, `localhost`, `127.0.0.1`,
`192.168.x.x`, `10.x.x.x`, etc.).
"""

from __future__ import annotations

import ipaddress
from urllib.parse import urlsplit

__all__ = ["url_e_valida"]

_SUFIXOS_HOST_BLOQUEADOS = (".local", ".localhost", ".internal")
_HOSTS_BLOQUEADOS = frozenset({"localhost", "0.0.0.0", "metadata.google.internal"})  # noqa: S104


def _ip_bloqueado(host: str) -> bool:
    try:
        endereco = ipaddress.ip_address(host)
    except ValueError:
        return False
    return bool(
        endereco.is_private
        or endereco.is_loopback
        or endereco.is_link_local
        or endereco.is_multicast
        or endereco.is_reserved
        or endereco.is_unspecified
    )


def url_e_valida(url: str) -> bool:
    """`True` quando `url` e um destino HTTPS aceitavel para um webhook."""
    try:
        partes = urlsplit(url)
    except ValueError:
        return False
    if partes.scheme != "https":
        return False
    host = (partes.hostname or "").lower().rstrip(".")
    if not host:
        return False
    if host in _HOSTS_BLOQUEADOS:
        return False
    if any(host.endswith(sufixo) for sufixo in _SUFIXOS_HOST_BLOQUEADOS):
        return False
    # Host entre colchetes IPv6 (`urlsplit` ja remove os colchetes de `hostname`).
    return not _ip_bloqueado(host)
