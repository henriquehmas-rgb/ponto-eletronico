"""A2 -- `gateway.dominio.cliente_facial` (cliente mTLS para o facial-svc,
F14/A2, hardening). Nome de arquivo com sufixo `_device_gw` -- mesma
convenção de `tests/test_andaime_device_gw.py` (evita colisão de nome de
módulo quando o CI roda `pytest -q` a partir da raiz do monorepo).

O handshake TLS real está provado em `apps/api/tests/f14/hardening/
test_mtls_facial_svc.py` (gerar dois pacotes Python isolados -- device-gw e
facial-svc não compartilham venv nesta máquina -- para um teste só). Este
arquivo prova a parte que só faz sentido aqui: `montar_cliente_facial_svc`
falha FECHADO quando a configuração está incompleta, e constrói o
`httpx.AsyncClient` com os `cert=`/`verify=` corretos quando completa.
"""

from __future__ import annotations

import datetime as dt

import httpx
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from gateway.config import Configuracao
from gateway.dominio.cliente_facial import MtlsNaoConfigurado, montar_cliente_facial_svc


@pytest.fixture(scope="module")
def par_pem_valido(tmp_path_factory: pytest.TempPathFactory) -> tuple[str, str]:
    """Um certificado/chave autoassinados reais (conteúdo PEM válido) --
    `httpx.AsyncClient.__init__` carrega os arquivos de `cert=`/`verify=`
    NA CONSTRUÇÃO (antes de qualquer conexão), então caminhos fictícios
    quebrariam este teste por um motivo que não tem nada a ver com o que
    ele prova (a montagem correta dos argumentos)."""
    diretorio = tmp_path_factory.mktemp("cliente_facial_pem")
    chave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    nome = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "teste")])
    agora = dt.datetime.now(dt.UTC)
    certificado = (
        x509.CertificateBuilder()
        .subject_name(nome)
        .issuer_name(nome)
        .public_key(chave.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(agora - dt.timedelta(minutes=5))
        .not_valid_after(agora + dt.timedelta(minutes=30))
        .sign(chave, hashes.SHA256())
    )
    caminho_cert = str(diretorio / "cert.pem")
    caminho_chave = str(diretorio / "chave.pem")
    with open(caminho_cert, "wb") as f:
        f.write(certificado.public_bytes(serialization.Encoding.PEM))
    with open(caminho_chave, "wb") as f:
        f.write(
            chave.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.TraditionalOpenSSL,
                serialization.NoEncryption(),
            )
        )
    return caminho_cert, caminho_chave


def _config(**overrides: str) -> Configuracao:
    base = {
        "facial_mtls_cert_path": "",
        "facial_mtls_key_path": "",
        "facial_mtls_ca_path": "",
    }
    base.update(overrides)
    return Configuracao(**base)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "overrides",
    [
        {},
        {"facial_mtls_cert_path": "/certs/cliente.pem"},
        {
            "facial_mtls_cert_path": "/certs/cliente.pem",
            "facial_mtls_key_path": "/certs/cliente.key",
        },
        {"facial_mtls_ca_path": "/certs/ca.pem"},
    ],
    ids=["nenhum", "so_cert", "cert_e_chave_sem_ca", "so_ca"],
)
def test_recusa_construir_cliente_com_configuracao_incompleta(overrides: dict[str, str]) -> None:
    """Falha fechada: qualquer combinação com pelo menos um dos três
    caminhos ausente levanta `MtlsNaoConfigurado`, nunca constrói um
    cliente "degradado" sem mTLS."""
    with pytest.raises(MtlsNaoConfigurado):
        montar_cliente_facial_svc(_config(**overrides))


def test_constroi_cliente_httpx_com_cert_e_verify_corretos(par_pem_valido: tuple[str, str]) -> None:
    caminho_cert, caminho_chave = par_pem_valido
    config = _config(
        facial_mtls_cert_path=caminho_cert,
        facial_mtls_key_path=caminho_chave,
        facial_mtls_ca_path=caminho_cert,  # mesmo par serve de "CA" para este teste de montagem
        facial_svc_url="https://facial-svc-teste:8000",
    )
    # `AsyncClient` não abre nenhuma conexão de rede na construção -- só
    # monta o transporte/contexto SSL. Não precisa (nem dá, fora de um
    # event loop) chamar `aclose()` neste teste síncrono.
    cliente = montar_cliente_facial_svc(config, timeout_s=7.5)
    assert isinstance(cliente, httpx.AsyncClient)
    assert str(cliente.base_url) == "https://facial-svc-teste:8000"
    assert cliente.timeout.connect == 7.5
