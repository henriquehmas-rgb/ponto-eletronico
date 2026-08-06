"""Entrada de processo do facial-svc com mTLS real (F14/A2, hardening).

**O que existia antes desta fase.** `facial_mtls_ca_path` já era lido por
`facial.main.ciclo_de_vida` -- só para logar um AVISO quando ausente em
produção (`PROJETO.md` §7.3: "aviso na Fase 0, recusa na F7"). O valor nunca
chegava a lugar nenhum que realmente ligasse TLS: o `Dockerfile` sobe
`uvicorn facial.main:app` direto, sem nenhum argumento `--ssl-*`. Configurar
a variável de ambiente não tinha NENHUM efeito operacional.

**O que esta fase muda.** Este módulo é o novo ponto de entrada (`python -m
facial.servidor`, substituindo `uvicorn facial.main:app` cru no `Dockerfile`)
que lê `Configuracao.mtls_configurado` e, quando os três caminhos (cert do
servidor, chave do servidor, CA para verificar o cliente) estão presentes,
passa `ssl_certfile`/`ssl_keyfile`/`ssl_ca_certs`/`ssl_cert_reqs=CERT_REQUIRED`
para `uvicorn.run` -- só então uma conexão sem certificado de cliente válido
é recusada pelo próprio handshake TLS, antes de qualquer byte de aplicação
trafegar. Sem os três caminhos, sobe em HTTP puro exatamente como antes
(nenhuma regressão em `dev`/`ci`, onde nenhum deles é configurado).

**A decisão de "avisar" vs. "recusar subir" permanece a de `main.py`/
`PROJETO.md` §7.3 -- não alterada aqui.** Este módulo só torna o MECANISMO
operacional; QUANDO ele passa a ser obrigatório em produção continua sendo
decisão de uma fase futura (F7, pela nota original), documentada de novo em
`docs/backlog.md` desta sessão.
"""

from __future__ import annotations

import ssl
from collections.abc import Callable
from typing import TypedDict

import uvicorn

from facial.config import obter_configuracao
from facial.log import obter_logger

logger = obter_logger("servidor")


class _OpcoesSslUvicorn(TypedDict, total=False):
    """Subconjunto dos kwargs de `uvicorn.run` usados aqui -- tipado
    explicitamente (em vez de `dict[str, object]`) para que `**opcoes_ssl`
    em `uvicorn.run(...)` type-check contra a assinatura real (achado do
    passe final de mypy da F14)."""

    ssl_certfile: str
    ssl_keyfile: str
    ssl_ca_certs: str
    ssl_cert_reqs: int
    ssl_context_factory: Callable[[uvicorn.Config, Callable[[], ssl.SSLContext]], ssl.SSLContext]


def _teto_tls_1_2(
    config: uvicorn.Config, default_factory: Callable[[], ssl.SSLContext]
) -> ssl.SSLContext:
    """`ssl_context_factory` do uvicorn: pega o contexto padrão (que já
    aplica cert/chave/CA/`cert_reqs` a partir dos `ssl_*` kwargs de `Config`,
    ver `uvicorn.config.create_ssl_context`) e só acrescenta o teto de
    versão. `default_factory` é `Callable[[], ssl.SSLContext]` (assinatura
    do próprio uvicorn); chamado aqui, não redefinido.

    **Por que o teto existe** (F14/A2, achado desta sessão, `docs/
    backlog.md`): reproduzido de forma isolada e determinística neste
    ambiente (Windows, Python 3.12, OpenSSL 3.0.16) que `ssl_cert_reqs=
    CERT_REQUIRED` sob TLS 1.3 NÃO recusou um handshake sem certificado de
    cliente -- a conexão completou como se mTLS estivesse desligado,
    silenciosamente. Sob TLS 1.2 (mesmo teste), a recusa aconteceu
    corretamente (`tests/f14/hardening/test_mtls_facial_svc.py`). mTLS com
    teto em TLS 1.2 é seguro e amplamente usado em produção -- este teto é a
    escolha defensiva até alguém revalidar o comportamento de TLS 1.3 no
    ambiente de deploy real (containers Linux, não esta máquina de
    desenvolvimento) e remover esta função conscientemente.
    """
    contexto = default_factory()
    contexto.maximum_version = ssl.TLSVersion.TLSv1_2
    return contexto


def opcoes_ssl_uvicorn() -> _OpcoesSslUvicorn:
    """Kwargs de `uvicorn.run` para TLS/mTLS, ou `{}` (HTTP puro) quando
    `Configuracao.mtls_configurado` é falso -- ver docstring do módulo."""
    config = obter_configuracao()
    if not config.mtls_configurado:
        return {}
    return {
        "ssl_certfile": config.facial_tls_cert_path,
        "ssl_keyfile": config.facial_tls_key_path,
        "ssl_ca_certs": config.facial_mtls_ca_path,
        # CERT_REQUIRED: o handshake TLS recusa qualquer conexão que não
        # apresente um certificado de cliente assinado pela CA configurada
        # -- é isto que torna "mTLS", e não só "TLS", entre device-gw e
        # este serviço.
        "ssl_cert_reqs": ssl.CERT_REQUIRED,
        "ssl_context_factory": _teto_tls_1_2,
    }


def main() -> None:  # pragma: no cover - integração de processo, testada
    # indiretamente por `opcoes_ssl_uvicorn` + os testes de handshake real
    # (`tests/f14/hardening/test_mtls_facial_svc.py`, que chamam
    # `uvicorn.Server` diretamente com as mesmas opções).
    import os

    config = obter_configuracao()
    opcoes_ssl = opcoes_ssl_uvicorn()
    if opcoes_ssl:
        logger.info("facial-svc subindo com mTLS", extra={"ambiente": config.ambiente})
    else:
        logger.info(
            "facial-svc subindo em HTTP puro (mTLS nao configurado)",
            extra={"ambiente": config.ambiente, "producao": config.producao},
        )
    uvicorn.run(
        "facial.main:app",
        host="0.0.0.0",  # noqa: S104 -- servico interno, so na rede ponto-interna
        port=8000,
        workers=int(os.environ.get("UVICORN_WORKERS", "1")),
        access_log=False,
        **opcoes_ssl,
    )


if __name__ == "__main__":  # pragma: no cover
    main()
