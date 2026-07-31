"""Testes de `app.fiscal.assinatura.certificado` (F12/A3, T11).

Cobre: caminho ausente/inexistente devolve `None` (nunca levanta exceção --
"indisponível" é o estado real e esperado hoje, PCF F12 §2.4); um `.pfx`
real gerado na própria fixture é carregado corretamente; a checagem de
`expirado` bate com a janela `not_valid_before`/`not_valid_after`.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID

from app.core.config import Configuracao
from app.fiscal.assinatura.certificado import (
    CertificadoConfig,
    _nome_comum,
    carregar_de_arquivo,
    obter_certificado_configurado,
)


def test_caminho_vazio_devolve_none() -> None:
    assert carregar_de_arquivo("", "qualquer") is None


def test_caminho_inexistente_devolve_none(tmp_path: Path) -> None:
    assert carregar_de_arquivo(tmp_path / "nao-existe.pfx", "qualquer") is None


def test_arquivo_corrompido_devolve_none(tmp_path: Path) -> None:
    caminho = tmp_path / "corrompido.pfx"
    caminho.write_bytes(b"isto nao e um PKCS12 valido")
    assert carregar_de_arquivo(caminho, "qualquer") is None


def test_carrega_pfx_real_gerado_na_fixture(
    tmp_path: Path, certificado_teste: CertificadoConfig
) -> None:
    """Serializa o certificado de teste (já gerado por `conftest.py`) como
    `.pfx` de verdade e confere que `carregar_de_arquivo` o lê corretamente
    -- prova o caminho real de produção (leitura de arquivo em disco), não
    só o atalho em memória que os outros testes usam."""
    senha = "senha-de-teste-123"
    pfx_bytes = pkcs12.serialize_key_and_certificates(
        name=b"teste",
        key=certificado_teste.chave_privada,
        cert=certificado_teste.certificado,
        cas=None,
        encryption_algorithm=serialization.BestAvailableEncryption(senha.encode("utf-8")),
    )
    caminho = tmp_path / "certificado-teste.pfx"
    caminho.write_bytes(pfx_bytes)

    carregado = carregar_de_arquivo(caminho, senha)

    assert carregado is not None
    assert carregado.certificado.serial_number == certificado_teste.certificado.serial_number
    assert carregado.titular == certificado_teste.titular


def test_carrega_pfx_com_senha_errada_devolve_none(
    tmp_path: Path, certificado_teste: CertificadoConfig
) -> None:
    pfx_bytes = pkcs12.serialize_key_and_certificates(
        name=b"teste",
        key=certificado_teste.chave_privada,
        cert=certificado_teste.certificado,
        cas=None,
        encryption_algorithm=serialization.BestAvailableEncryption(b"senha-correta"),
    )
    caminho = tmp_path / "certificado-teste.pfx"
    caminho.write_bytes(pfx_bytes)

    assert carregar_de_arquivo(caminho, "senha-errada") is None


def test_expirado_property_bate_com_janela_de_validade(
    certificado_teste: CertificadoConfig, certificado_teste_expirado: CertificadoConfig
) -> None:
    assert certificado_teste.expirado is False
    assert certificado_teste_expirado.expirado is True


def test_obter_certificado_configurado_sem_variavel_de_ambiente_devolve_none(
    monkeypatch,
) -> None:
    """Estado real de hoje (PCF F12 §2.4, confirmado indisponível em
    30/07/2026): sem `CERT_ICP_PATH` configurado, `gerarAfd`/`gerarAej`
    concluem sem certificado, e `assinarArquivoFiscal` responde
    `PONTO-FISC-004` -- este teste prova a base dessa garantia."""
    config = Configuracao(cert_icp_path="", cert_icp_senha="")
    assert obter_certificado_configurado(config) is None


def test_nome_comum_sem_common_name_usa_rfc4514_como_fallback() -> None:
    """`_nome_comum` (usado para `titular`/`emissor`) cai para
    `rfc4514_string()` quando o `Name` não tem `CommonName` -- caso raro,
    mas um certificado X.509 tecnicamente pode ter um `subject`/`issuer`
    vazio ou só com outros atributos."""
    nome_vazio = x509.Name([])
    assert _nome_comum(nome_vazio) == nome_vazio.rfc4514_string()

    nome_so_org = x509.Name([x509.NameAttribute(NameOID.ORGANIZATION_NAME, "SEEG")])
    assert _nome_comum(nome_so_org) == nome_so_org.rfc4514_string()
    assert "CN=" not in _nome_comum(nome_so_org)


def test_carrega_pfx_sem_chave_privada_devolve_none(
    tmp_path: Path, certificado_teste: CertificadoConfig
) -> None:
    """Um `.pfx` só com certificado (sem a chave privada correspondente) --
    `pkcs12.load_key_and_certificates` devolve o certificado na lista de
    `cas` (adicionais), não no slot principal, então `certificado` também
    sai `None` daqui: o caminho real é `chave is None or certificado is
    None`, e este teste cobre o lado `certificado is None`."""
    senha = "senha-de-teste"
    pfx_bytes = pkcs12.serialize_key_and_certificates(
        name=b"teste",
        key=None,
        cert=certificado_teste.certificado,
        cas=None,
        encryption_algorithm=serialization.BestAvailableEncryption(senha.encode("utf-8")),
    )
    caminho = tmp_path / "sem-chave.pfx"
    caminho.write_bytes(pfx_bytes)

    assert carregar_de_arquivo(caminho, senha) is None


def test_carrega_pfx_com_chave_de_tipo_nao_suportado_devolve_none(tmp_path: Path) -> None:
    """Chave Ed25519: válida para PKCS#12 e para X.509, mas
    `cryptography.hazmat.primitives.serialization.pkcs7.PKCS7SignatureBuilder.
    add_signer` só aceita RSA/EC (`PKCS7PrivateKeyTypes`) -- este módulo
    recusa no carregamento, com um aviso explicativo, em vez de deixar o
    tipo incompatível estourar mais tarde dentro de `cades.assinar_cades`."""
    chave_ed25519 = ed25519.Ed25519PrivateKey.generate()
    nome = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "TESTE ED25519")])
    agora = dt.datetime.now(dt.UTC)
    certificado = (
        x509.CertificateBuilder()
        .subject_name(nome)
        .issuer_name(nome)
        .public_key(chave_ed25519.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(agora)
        .not_valid_after(agora + dt.timedelta(days=1))
        .sign(chave_ed25519, None)
    )
    senha = "senha-de-teste"
    pfx_bytes = pkcs12.serialize_key_and_certificates(
        name=b"teste",
        key=chave_ed25519,
        cert=certificado,
        cas=None,
        encryption_algorithm=serialization.BestAvailableEncryption(senha.encode("utf-8")),
    )
    caminho = tmp_path / "ed25519.pfx"
    caminho.write_bytes(pfx_bytes)

    assert carregar_de_arquivo(caminho, senha) is None
