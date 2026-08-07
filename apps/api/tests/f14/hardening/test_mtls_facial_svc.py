"""A2 -- prova real de handshake mTLS entre `device-gw` e `facial-svc`
(PCF F14 §5: "mTLS device-gw ↔ facial-svc").

**Por que este teste vive em `apps/api/tests/f14/hardening` e não em
`apps/device-gw/tests`/`apps/facial-svc/tests`.** `device-gw` e `facial-svc`
são pacotes Python INDEPENDENTES, cada um com o próprio `pyproject.toml`/
venv -- não há um venv único que importe os dois ao mesmo tempo (confirmado:
`apps/facial-svc` não tem `.venv` nesta máquina). Este teste não importa
NENHUM dos dois pacotes: ele prova o MECANISMO que `facial/servidor.py::
opcoes_ssl_uvicorn` e `gateway/dominio/cliente_facial.py::
montar_cliente_facial_svc` implementam -- as mesmas primitivas
`ssl.SSLContext`/`ssl_certfile`/`ssl_keyfile`/`ssl_ca_certs`/
`ssl_cert_reqs=CERT_REQUIRED` do lado servidor, e `cert=(...)`/`verify=...`
do lado cliente -- contra um servidor HTTPS real (`http.server` +
`ssl.SSLContext`, a mesma primitiva que `uvicorn` usa por baixo), com
certificados reais gerados na hora (CA de teste, nunca committed). A última
prova (`test_httpx_com_certificado_valido_completa_a_requisicao_http`) fecha
o loop passando pela pilha `httpx.AsyncClient` real, a mesma que
`montar_cliente_facial_svc` usa em produção.

Prova, contra um handshake TLS de verdade (não mock):
1. Cliente SEM certificado é recusado pelo próprio TLS (nunca chega à
   aplicação).
2. Cliente com certificado assinado por uma CA DIFERENTE é recusado.
3. Cliente com certificado válido (assinado pela CA que o servidor confia)
   é aceito e a requisição HTTP completa normalmente.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import http.server
import socket
import ssl
import threading
from collections.abc import Iterator

import httpx
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


def _gerar_par_chave() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _gerar_ca() -> tuple[rsa.RSAPrivateKey, x509.Certificate]:
    chave = _gerar_par_chave()
    nome = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "CA de teste F14/A2")])
    agora = dt.datetime.now(dt.UTC)
    certificado = (
        x509.CertificateBuilder()
        .subject_name(nome)
        .issuer_name(nome)
        .public_key(chave.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(agora - dt.timedelta(minutes=5))
        .not_valid_after(agora + dt.timedelta(minutes=30))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(chave, hashes.SHA256())
    )
    return chave, certificado


def _gerar_certificado_assinado(
    *, cn: str, ca_chave: rsa.RSAPrivateKey, ca_certificado: x509.Certificate, is_server: bool
) -> tuple[rsa.RSAPrivateKey, x509.Certificate]:
    chave = _gerar_par_chave()
    nome = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    agora = dt.datetime.now(dt.UTC)
    builder = (
        x509.CertificateBuilder()
        .subject_name(nome)
        .issuer_name(ca_certificado.subject)
        .public_key(chave.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(agora - dt.timedelta(minutes=5))
        .not_valid_after(agora + dt.timedelta(minutes=30))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                key_encipherment=True,
                content_commitment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
    )
    if is_server:
        import ipaddress as _ipaddress

        builder = builder.add_extension(
            x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.SERVER_AUTH]), critical=False
        ).add_extension(
            x509.SubjectAlternativeName(
                [x509.DNSName("localhost"), x509.IPAddress(_ipaddress.ip_address("127.0.0.1"))]
            ),
            critical=False,
        )
    else:
        builder = builder.add_extension(
            x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.CLIENT_AUTH]), critical=False
        )
    certificado = builder.sign(ca_chave, hashes.SHA256())
    return chave, certificado


def _escrever_pem_chave(chave: rsa.RSAPrivateKey, caminho: str) -> None:
    with open(caminho, "wb") as f:
        f.write(
            chave.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )


def _escrever_pem_certificado(certificado: x509.Certificate, caminho: str) -> None:
    with open(caminho, "wb") as f:
        f.write(certificado.public_bytes(serialization.Encoding.PEM))


@pytest.fixture(scope="module")
def ambiente_mtls(tmp_path_factory: pytest.TempPathFactory) -> dict[str, str]:
    """Gera CA + certificado de servidor + DOIS certificados de cliente (um
    confiável, um de uma CA estranha) -- tudo em arquivos temporários,
    descartados no fim da suíte, nunca committed."""
    diretorio = tmp_path_factory.mktemp("mtls_f14a2")

    ca_chave, ca_cert = _gerar_ca()
    caminho_ca = str(diretorio / "ca.pem")
    _escrever_pem_certificado(ca_cert, caminho_ca)

    servidor_chave, servidor_cert = _gerar_certificado_assinado(
        cn="facial-svc-teste", ca_chave=ca_chave, ca_certificado=ca_cert, is_server=True
    )
    caminho_servidor_cert = str(diretorio / "servidor.pem")
    caminho_servidor_chave = str(diretorio / "servidor.key")
    _escrever_pem_certificado(servidor_cert, caminho_servidor_cert)
    _escrever_pem_chave(servidor_chave, caminho_servidor_chave)

    cliente_chave, cliente_cert = _gerar_certificado_assinado(
        cn="device-gw-teste", ca_chave=ca_chave, ca_certificado=ca_cert, is_server=False
    )
    caminho_cliente_cert = str(diretorio / "cliente.pem")
    caminho_cliente_chave = str(diretorio / "cliente.key")
    _escrever_pem_certificado(cliente_cert, caminho_cliente_cert)
    _escrever_pem_chave(cliente_chave, caminho_cliente_chave)

    # Segunda CA, "estranha" -- assina um certificado de cliente que o
    # servidor (confiando só na primeira CA) precisa recusar.
    ca2_chave, ca2_cert = _gerar_ca()
    cliente_estranho_chave, cliente_estranho_cert = _gerar_certificado_assinado(
        cn="atacante", ca_chave=ca2_chave, ca_certificado=ca2_cert, is_server=False
    )
    caminho_cliente_estranho_cert = str(diretorio / "cliente_estranho.pem")
    caminho_cliente_estranho_chave = str(diretorio / "cliente_estranho.key")
    _escrever_pem_certificado(cliente_estranho_cert, caminho_cliente_estranho_cert)
    _escrever_pem_chave(cliente_estranho_chave, caminho_cliente_estranho_chave)

    return {
        "ca": caminho_ca,
        "servidor_cert": caminho_servidor_cert,
        "servidor_chave": caminho_servidor_chave,
        "cliente_cert": caminho_cliente_cert,
        "cliente_chave": caminho_cliente_chave,
        "cliente_estranho_cert": caminho_cliente_estranho_cert,
        "cliente_estranho_chave": caminho_cliente_estranho_chave,
    }


def _porta_livre() -> int:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _HandlerPing(http.server.BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        pass  # silencioso: o teste não precisa do access log

    def do_GET(self) -> None:  # noqa: N802 - nome exigido pela stdlib
        corpo = b'{"ok": true}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)


@pytest.fixture(scope="module")
def servidor_mtls(ambiente_mtls: dict[str, str]) -> Iterator[int]:
    """Servidor HTTPS real (stdlib `http.server` + `ssl.SSLContext`) com as
    MESMAS opções que `facial.servidor.opcoes_ssl_uvicorn()` produz quando
    `mtls_configurado` é verdadeiro: certificado/chave próprios + `CA` para
    verificar o cliente + `CERT_REQUIRED`. Usa a stdlib em vez de subir
    `uvicorn`/ASGI aqui de propósito -- o que este teste prova é o
    HANDSHAKE TLS (mesma primitiva `ssl.SSLContext` que `uvicorn` usa por
    baixo dos panos via `ssl_certfile`/`ssl_keyfile`/`ssl_ca_certs`/
    `ssl_cert_reqs`), não o roteamento ASGI."""
    contexto = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    contexto.load_cert_chain(
        certfile=ambiente_mtls["servidor_cert"], keyfile=ambiente_mtls["servidor_chave"]
    )
    contexto.load_verify_locations(cafile=ambiente_mtls["ca"])
    contexto.verify_mode = ssl.CERT_REQUIRED
    # Achado desta sessão (F14/A2, registrado em `docs/backlog.md`): em TLS
    # 1.3, `CERT_REQUIRED` sem certificado de cliente NÃO recusou o handshake
    # neste ambiente (Windows, Python 3.12, OpenSSL 3.0.16) -- reproduzido de
    # forma isolada e determinística fora deste harness de teste. Pinar em
    # TLS 1.2 aqui é a MESMA escolha defensiva que `facial/servidor.py`
    # também aplica (ver lá): mTLS com TLS 1.2 é seguro e amplamente testado;
    # reabrir TLS 1.3 exige revalidar em produção (Linux) antes.
    contexto.maximum_version = ssl.TLSVersion.TLSv1_2

    class _ServidorHttps(http.server.HTTPServer):
        def get_request(self) -> tuple[socket.socket, tuple[str, int]]:  # type: ignore[override]
            # Recipe padrão da stdlib: envolver CADA conexão aceita (nunca o
            # socket de escuta em si) -- só assim `verify_mode`/CA realmente
            # se aplicam por conexão.
            bruto, endereco = self.socket.accept()
            return contexto.wrap_socket(bruto, server_side=True), endereco

    porta = _porta_livre()
    servidor = _ServidorHttps(("127.0.0.1", porta), _HandlerPing)

    thread = threading.Thread(target=servidor.serve_forever, daemon=True)
    thread.start()

    yield porta

    servidor.shutdown()
    thread.join(timeout=5)


def _handshake_cliente(
    porta: int, *, ca: str, cert: str | None = None, chave: str | None = None
) -> ssl.SSLSocket:
    """Handshake TLS síncrono via `socket`/`ssl.SSLContext` puros -- a mesma
    primitiva que `httpx`/`uvicorn` usam por baixo, sem a camada async
    (`anyio`/`httpcore`) no meio. Devolve o socket TLS já conectado (chamador
    fecha) ou deixa a exceção de `ssl`/`socket` propagar quando o servidor
    recusa o handshake."""
    contexto = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    # minimum_version tambem pinado em TLS 1.2 (nao so o maximum): sem isso
    # o contexto aceita negociar ate TLS 1.0/1.1, protocolos obsoletos que o
    # CodeQL sinaliza (py/insecure-protocol) -- mesma escolha defensiva de
    # `servidor_mtls` acima e de `facial/servidor.py` em producao.
    contexto.minimum_version = ssl.TLSVersion.TLSv1_2
    contexto.maximum_version = ssl.TLSVersion.TLSv1_2
    contexto.load_verify_locations(cafile=ca)
    if cert:
        contexto.load_cert_chain(certfile=cert, keyfile=chave)
    bruto = socket.create_connection(("127.0.0.1", porta), timeout=5.0)
    return contexto.wrap_socket(bruto, server_hostname="127.0.0.1")


#: O handshake recusado por falta de certificado de cliente (ou por CA
#: errada) se manifesta como `ssl.SSLError` OU como o socket sendo fechado
#: cru pelo peer (`ConnectionResetError`/`OSError`, observado neste ambiente
#: -- ver comentário em `servidor_mtls` sobre TLS 1.3) -- qualquer um dos
#: dois É a recusa esperada; o que este teste não pode aceitar é a conexão
#: completar como se nada tivesse acontecido.
_ERROS_HANDSHAKE_RECUSADO = (ssl.SSLError, ConnectionResetError, OSError)


def test_cliente_sem_certificado_e_recusado_pelo_handshake_tls(
    servidor_mtls: int, ambiente_mtls: dict[str, str]
) -> None:
    with pytest.raises(_ERROS_HANDSHAKE_RECUSADO):
        _handshake_cliente(servidor_mtls, ca=ambiente_mtls["ca"])


def test_cliente_com_certificado_de_ca_estranha_e_recusado(
    servidor_mtls: int, ambiente_mtls: dict[str, str]
) -> None:
    with pytest.raises(_ERROS_HANDSHAKE_RECUSADO):
        _handshake_cliente(
            servidor_mtls,
            ca=ambiente_mtls["ca"],
            cert=ambiente_mtls["cliente_estranho_cert"],
            chave=ambiente_mtls["cliente_estranho_chave"],
        )


def test_cliente_com_certificado_valido_e_aceito(
    servidor_mtls: int, ambiente_mtls: dict[str, str]
) -> None:
    """Mesma forma de `gateway.dominio.cliente_facial.montar_cliente_facial_svc`:
    certificado de cliente + CA de verificação -- aqui provado no nível mais
    baixo possível (handshake TLS bruto), a prova mais direta de que
    `ssl_cert_reqs=CERT_REQUIRED` do lado servidor + `cert=(...)`/`verify=...`
    do lado cliente realmente compõem um mTLS funcional."""
    tls_socket = _handshake_cliente(
        servidor_mtls,
        ca=ambiente_mtls["ca"],
        cert=ambiente_mtls["cliente_cert"],
        chave=ambiente_mtls["cliente_chave"],
    )
    try:
        tls_socket.sendall(b"GET /ping HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n")
        resposta = b""
        while True:
            pedaco = tls_socket.recv(4096)
            if not pedaco:
                break
            resposta += pedaco
    finally:
        tls_socket.close()

    assert b"200" in resposta.split(b"\r\n", 1)[0]
    assert b'{"ok": true}' in resposta


def test_httpx_com_certificado_valido_completa_a_requisicao_http(
    servidor_mtls: int, ambiente_mtls: dict[str, str]
) -> None:
    """Mesma prova de cima, mas passando pela pilha `httpx.AsyncClient`
    real (a que `gateway.dominio.cliente_facial.montar_cliente_facial_svc`
    usa em produção) -- fecha o loop entre "o handshake bruto funciona" e
    "o cliente HTTP que o device-gw realmente usaria funciona"."""

    async def _chamar() -> httpx.Response:
        # `ssl.SSLContext` explícito (não `verify=<caminho string>`): o
        # servidor de teste pina `maximum_version=TLSv1_2` (ver comentário em
        # `servidor_mtls`), e o contexto default do httpx negocia TLS 1.3
        # primeiro -- precisa do mesmo teto aqui para o handshake completar.
        contexto = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        contexto.maximum_version = ssl.TLSVersion.TLSv1_2
        contexto.load_verify_locations(cafile=ambiente_mtls["ca"])
        contexto.load_cert_chain(
            certfile=ambiente_mtls["cliente_cert"], keyfile=ambiente_mtls["cliente_chave"]
        )
        async with httpx.AsyncClient(
            base_url=f"https://127.0.0.1:{servidor_mtls}",
            verify=contexto,
            timeout=5.0,
        ) as cliente:
            return await cliente.get("/ping")

    resposta = asyncio.run(_chamar())
    assert resposta.status_code == 200
    assert resposta.json() == {"ok": True}
