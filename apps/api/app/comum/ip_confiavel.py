"""Resolução de IP do cliente final, com confiança condicional em
`X-Forwarded-For`/`X-Real-IP` (F14/A2, hardening).

**O achado (F13, fechamento, `docs/backlog.md` 2026-08-03).** Todo endpoint
que autentica ou registra IP (`sessoes.ip`, `oauth_tokens.ip`,
`api_clients`, `usuario.ultimo_acesso_ip`, e -- quando aplicável -- sinais
de antifraude) hoje lê `request.client.host` direto. Quando a requisição
passa pelo proxy Next.js (`apps/web`, servidor-a-servidor até a API --
login por senha, SSO, LGPD, exportação fiscal, espelho de ponto), esse valor
é o IP do PRÓPRIO PROXY, nunca o do usuário final: `apps/web` conecta como
cliente HTTP normal, e o socket que a API enxerga é o do container `web`,
não o do navegador da pessoa.

**Por que não se pode confiar cegamente em `X-Forwarded-For`.** Esse
cabeçalho é `Header()` comum, qualquer chamador pode mandar o valor que
quiser -- aceitá-lo sem checar de onde a requisição REALMENTE veio abre
spoofing de IP: um cliente malicioso simplesmente declara
`X-Forwarded-For: 1.2.3.4` e o sistema grava um IP que não é o dele (e pior,
se algum dia um sinal de antifraude usar geolocalização por IP, o cliente
escolhe a própria geolocalização).

**A regra.** `X-Forwarded-For`/`X-Real-IP` só é lido quando o IP do socket
IMEDIATO (`request.client.host`, o `peer` real da conexão TCP que chega
neste processo) está na allowlist `Configuracao.lista_proxies_confiaveis`
(IPs do(s) proxy(s) reverso(s) de produção -- Traefik, container `web`).
Fora da allowlist (`dev`/`ci` sem a variável configurada, ou uma tentativa
de conectar direto pulando o proxy), o cabeçalho é ignorado por completo e o
IP do peer é usado como está -- exatamente o comportamento de hoje, sem
regressão.

`X-Forwarded-For` pode conter uma CADEIA (`cliente, proxy1, proxy2`, RFC
7239 não padroniza o formato exato, mas esta é a convenção universal): o
PRIMEIRO valor é o mais próximo do cliente original. Usamos esse primeiro
valor -- qualquer proxy adicional entre o cliente e o nosso Traefik já
teria a própria entrada acrescentada à cadeia, não substituída.
"""

from __future__ import annotations

import ipaddress

from fastapi import Request

from app.core.config import obter_configuracao


def _ip_valido(candidato: str | None) -> str | None:
    """`None` quando `candidato` não é um IP válido -- mesma proteção que
    `app/routers/auth.py::_ip_do_cliente` já tinha: colunas `INET` do
    Postgres rejeitam valor não-IP (ex.: `"testclient"`, host padrão do
    `starlette.testclient.TestClient` sem transporte de rede real) com
    `DataError` cru, não um erro de domínio. Melhor `NULL` que quebrar a
    escrita por causa de um dado auxiliar."""
    if not candidato:
        return None
    candidato = candidato.strip()
    try:
        ipaddress.ip_address(candidato)
    except ValueError:
        return None
    return candidato


def ip_confiavel_do_cliente(request: Request) -> str | None:
    """IP do cliente final, honrando `X-Forwarded-For`/`X-Real-IP` SÓ quando
    a origem imediata da conexão está na allowlist de proxy reverso
    confiável (`Configuracao.proxies_confiaveis`). Ver docstring do módulo.
    """
    peer = request.client.host if request.client else None
    proxies_confiaveis = obter_configuracao().lista_proxies_confiaveis

    if not proxies_confiaveis or peer not in proxies_confiaveis:
        # Sem allowlist configurada (dev/ci) ou peer não é um proxy
        # conhecido: nunca confia em cabeçalho que qualquer chamador pode
        # forjar -- usa o IP do socket como está, mesmo comportamento de
        # antes deste módulo existir.
        return _ip_valido(peer)

    cabecalho_xff = request.headers.get("x-forwarded-for")
    if cabecalho_xff:
        primeiro = cabecalho_xff.split(",", 1)[0]
        candidato = _ip_valido(primeiro)
        if candidato is not None:
            return candidato

    cabecalho_real_ip = request.headers.get("x-real-ip")
    candidato = _ip_valido(cabecalho_real_ip)
    if candidato is not None:
        return candidato

    # Proxy confiável, mas nenhum dos dois cabeçalhos veio com IP válido:
    # cai para o peer (o proxy) em vez de `None` -- ainda é um IP real,
    # só não é o do usuário final; melhor que perder o dado por completo.
    return _ip_valido(peer)
