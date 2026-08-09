"""Postura de mTLS do cliente de `apps/api` para o `facial-svc`.

Nao repete `tests/f14/hardening/test_mtls_facial_svc.py` (que ja prova o
aperto de mao TLS mutuo contra um servidor real): aqui o que esta em jogo e a
DECISAO de montar, ou recusar montar, o cliente -- que e onde uma configuracao
pela metade vira uma conexao sem certificado em producao sem ninguem perceber.

Nao toca banco nem rede: so `Configuracao`.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from app.biometria.cliente_facial import MtlsNaoConfigurado, montar_cliente_facial_svc
from app.core.config import Configuracao


def _config(**overrides: object) -> Configuracao:
    base: dict[str, object] = {
        "ambiente": "dev",
        "facial_svc_url": "https://facial-svc-teste:8000",
        "facial_mtls_cert_path": "",
        "facial_mtls_key_path": "",
        "facial_mtls_ca_path": "",
    }
    base.update(overrides)
    return Configuracao(**base)  # type: ignore[arg-type]


def test_dev_sem_mtls_sobe_em_http_puro() -> None:
    """Mesma postura do proprio `facial-svc` (`facial/servidor.py`): sem os
    tres caminhos ele nao apresenta TLS, entao exigir mTLS do cliente em `dev`
    quebraria o desenvolvimento local sem proteger nada."""
    cliente = montar_cliente_facial_svc(_config(), timeout_s=3.0)
    assert str(cliente.base_url).rstrip("/") == "https://facial-svc-teste:8000"


@pytest.mark.parametrize(
    "overrides",
    [
        {"facial_mtls_cert_path": "/certs/cliente.pem"},
        {"facial_mtls_cert_path": "/certs/cliente.pem", "facial_mtls_key_path": "/certs/c.key"},
        {"facial_mtls_ca_path": "/certs/ca.pem"},
    ],
    ids=["so-cert", "cert-e-chave", "so-ca"],
)
def test_configuracao_parcial_e_sempre_recusada(overrides: dict[str, object]) -> None:
    """Metade de um mTLS nao e meio seguro: e configuracao errada silenciosa.

    O modo de falha que isto impede e concreto -- alguem preenche o certificado
    de cliente, esquece a CA, e o cliente passa a NAO verificar o servidor:
    conexao "com certificado" e sem autenticacao do outro lado.
    """
    with pytest.raises(MtlsNaoConfigurado):
        montar_cliente_facial_svc(_config(**overrides), timeout_s=3.0)


@pytest.mark.parametrize("ambiente", ["hml", "prd"])
def test_producao_sem_mtls_recusa_montar(ambiente: str) -> None:
    """Falha fechada onde importa: `infra/docker-compose.prod.yml` ja torna
    `FACIAL_MTLS_*` obrigatorio para o servidor; o cliente nao pode ser o elo
    que aceita degradar para HTTP puro com biometria dentro."""
    with pytest.raises(MtlsNaoConfigurado):
        montar_cliente_facial_svc(_config(ambiente=ambiente), timeout_s=3.0)


def test_tres_caminhos_preenchidos_montam_cliente_mtls(tmp_path: Path) -> None:
    """Os tres juntos produzem um cliente com contexto TLS de verdade.

    Os arquivos precisam existir e ser certificado/chave validos: o `httpx`
    monta o `SSLContext` na construcao, nao na primeira conexao. O par e gerado
    aqui, na hora, autoassinado e descartavel -- nenhum certificado de teste
    entra no repositorio.
    """
    cert, chave = _par_autoassinado(tmp_path)
    cliente = montar_cliente_facial_svc(
        _config(
            facial_mtls_cert_path=str(cert),
            facial_mtls_key_path=str(chave),
            # O proprio certificado serve de "CA" para este teste de MONTAGEM
            # (o aperto de mao real ja e provado em
            # `tests/f14/hardening/test_mtls_facial_svc.py`).
            facial_mtls_ca_path=str(cert),
        ),
        timeout_s=7.5,
    )
    assert cliente.timeout.connect == 7.5


def _par_autoassinado(destino: Path) -> tuple[Path, Path]:
    """Certificado + chave RSA autoassinados, validos, em arquivos temporarios."""
    chave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    nome = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "facial-svc-teste")])
    agora = dt.datetime.now(dt.UTC)
    certificado = (
        x509.CertificateBuilder()
        .subject_name(nome)
        .issuer_name(nome)
        .public_key(chave.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(agora - dt.timedelta(minutes=5))
        .not_valid_after(agora + dt.timedelta(hours=1))
        .sign(chave, hashes.SHA256())
    )
    caminho_cert = destino / "cliente.pem"
    caminho_chave = destino / "cliente.key"
    caminho_cert.write_bytes(certificado.public_bytes(serialization.Encoding.PEM))
    caminho_chave.write_bytes(
        chave.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    return caminho_cert, caminho_chave
