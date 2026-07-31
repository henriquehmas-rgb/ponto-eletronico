"""Testes de `app.fiscal.assinatura.cades` (F12/A3, T11) -- "pronto quando"
do PCF: `assinar_cades` + `validar_cades`, com um certificado de teste,
produzem uma assinatura estruturalmente válida (parseável de volta como
CMS/PKCS#7, `MessageDigest` confere).

Nenhum destes testes toca banco -- `assinar_cades`/`validar_cades` são
funções puras sobre bytes/certificado (PCF F12 §2.4/T11).
"""

from __future__ import annotations

from asn1crypto import cms
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.serialization import Encoding
from cryptography.hazmat.primitives.serialization import pkcs7 as _pkcs7

from app.fiscal.assinatura.cades import ATRIBUTOS_CADES_BES_MINIMOS, assinar_cades, validar_cades
from app.fiscal.assinatura.certificado import CertificadoConfig


def test_assinatura_estruturalmente_valida_e_message_digest_confere(
    certificado_teste: CertificadoConfig,
) -> None:
    conteudo = b"AFD DE TESTE\r\n" * 10
    assinatura = assinar_cades(conteudo, certificado_teste)

    resultado = validar_cades(conteudo, assinatura)

    assert resultado.estruturalmente_valido is True
    assert resultado.message_digest_confere is True
    assert resultado.assinatura_criptografica_valida is True
    assert resultado.certificado_dentro_da_validade is True
    assert resultado.valido is True
    # Ver docstring de `ResultadoValidacao`: cadeia ICP-Brasil NUNCA e
    # verificada nesta fase (nao ha AC real disponivel).
    assert resultado.cadeia_confianca_icp_brasil_verificada is False


def test_assinatura_e_um_p7s_detached_sem_conteudo_embutido(
    certificado_teste: CertificadoConfig,
) -> None:
    """`.p7s` destacado = o conteudo original NAO fica dentro do CMS (regra
    de leiaute: "detached significa .p7s separado do arquivo original,
    formato exigido para o AFD")."""
    from asn1crypto import cms

    conteudo = b"conteudo que NAO deve aparecer embutido no .p7s"
    assinatura = assinar_cades(conteudo, certificado_teste)

    info = cms.ContentInfo.load(assinatura)
    signed_data = info["content"]
    econtent = signed_data["encap_content_info"]["content"]
    assert econtent.native is None
    assert conteudo not in assinatura


def test_atributos_cades_bes_minimos_presentes(certificado_teste: CertificadoConfig) -> None:
    """Confirma, por inspecao direta da estrutura ASN.1 (nao por confiar
    cegamente na docstring), que os 3 atributos exigidos pelo perfil
    CAdES-BES saem por padrao da `cryptography.pkcs7`."""
    from asn1crypto import cms

    assinatura = assinar_cades(b"conteudo", certificado_teste)
    info = cms.ContentInfo.load(assinatura)
    signer_info = info["content"]["signer_infos"][0]
    tipos = {a["type"].native for a in signer_info["signed_attrs"]}
    assert tipos >= ATRIBUTOS_CADES_BES_MINIMOS


def test_conteudo_adulterado_reprova_message_digest(certificado_teste: CertificadoConfig) -> None:
    conteudo_original = b"conteudo original do AFD"
    assinatura = assinar_cades(conteudo_original, certificado_teste)

    resultado = validar_cades(conteudo_original + b" adulterado", assinatura)

    assert resultado.estruturalmente_valido is True  # o CMS em si continua bem formado
    assert resultado.message_digest_confere is False
    assert resultado.valido is False


def test_assinatura_corrompida_e_estruturalmente_invalida(
    certificado_teste: CertificadoConfig,
) -> None:
    conteudo = b"conteudo qualquer"
    assinatura = assinar_cades(conteudo, certificado_teste)

    resultado = validar_cades(conteudo, assinatura[:-20])

    assert resultado.estruturalmente_valido is False
    assert resultado.valido is False
    assert resultado.motivo_falha is not None


def test_certificado_esperado_diferente_e_recusado(
    certificado_teste: CertificadoConfig, certificado_teste_expirado: CertificadoConfig
) -> None:
    """Defesa contra substituicao de certificado: o CMS por si so so prova
    "este certificado assinou isto", nao "este e o certificado autorizado" --
    `certificado_esperado` fecha essa lacuna."""
    conteudo = b"conteudo assinado pelo certificado A"
    assinatura = assinar_cades(conteudo, certificado_teste)

    certificado_b_der = certificado_teste_expirado.certificado.public_bytes(Encoding.DER)
    resultado = validar_cades(conteudo, assinatura, certificado_esperado=certificado_b_der)

    assert resultado.valido is False
    assert "certificado" in (resultado.motivo_falha or "").lower()


def test_certificado_expirado_reprova_janela_de_validade(
    certificado_teste_expirado: CertificadoConfig,
) -> None:
    assert certificado_teste_expirado.expirado is True

    conteudo = b"conteudo assinado com certificado ja expirado"
    assinatura = assinar_cades(conteudo, certificado_teste_expirado)

    resultado = validar_cades(conteudo, assinatura)

    assert resultado.message_digest_confere is True
    assert resultado.assinatura_criptografica_valida is True
    assert resultado.certificado_dentro_da_validade is False
    assert resultado.valido is False


def test_determinismo_do_message_digest_para_o_mesmo_conteudo(
    certificado_teste: CertificadoConfig,
) -> None:
    """Duas assinaturas do MESMO conteudo tem `message-digest` identico
    (mesmo que `signing-time`/a assinatura RSA em si variem por causa do
    relogio e do padding aleatorio de PKCS#1v1.5)."""
    from asn1crypto import cms

    conteudo = b"mesmo conteudo, duas assinaturas"
    assinatura_1 = assinar_cades(conteudo, certificado_teste)
    assinatura_2 = assinar_cades(conteudo, certificado_teste)

    def _message_digest(sig: bytes) -> bytes:
        info = cms.ContentInfo.load(sig)
        attrs = info["content"]["signer_infos"][0]["signed_attrs"]
        return next(a["values"][0].native for a in attrs if a["type"].native == "message_digest")

    assert _message_digest(assinatura_1) == _message_digest(assinatura_2)
    assert validar_cades(conteudo, assinatura_1).valido
    assert validar_cades(conteudo, assinatura_2).valido


# ---------------------------------------------------------------------------
# Estruturas CMS deliberadamente mal-formadas, montadas com `asn1crypto`
# diretamente (não via `assinar_cades`) para exercitar cada ramo defensivo de
# `validar_cades` que um `.p7s` produzido pelo próprio `assinar_cades` nunca
# alcança sozinho (ele sempre produz CMS bem formado). Cobrem exatamente as
# checagens estruturais que a docstring do módulo promete.
# ---------------------------------------------------------------------------


def test_content_type_diferente_de_signed_data_e_invalido() -> None:
    ci = cms.ContentInfo({"content_type": "data", "content": b"nao e signed_data"})
    resultado = validar_cades(b"qualquer coisa", ci.dump())
    assert resultado.estruturalmente_valido is False
    assert resultado.valido is False
    assert "SignedData" in (resultado.motivo_falha or "")


def _cms_valido(
    certificado_teste: CertificadoConfig, conteudo: bytes
) -> tuple[bytes, dict[str, object]]:
    """Assina de verdade e devolve `(bytes, {'sd': SignedData reconstruído})`
    -- ponto de partida para as mutações ASN.1 abaixo."""
    assinatura = assinar_cades(conteudo, certificado_teste)
    info = cms.ContentInfo.load(assinatura)
    return assinatura, {"sd": info["content"]}


def test_mais_de_um_signer_info_e_invalido(certificado_teste: CertificadoConfig) -> None:
    conteudo = b"conteudo com dois signers simulados"
    assinatura, ctx = _cms_valido(certificado_teste, conteudo)
    sd = ctx["sd"]
    si_unico = sd["signer_infos"][0]
    sd["signer_infos"] = cms.SignerInfos([si_unico, si_unico])
    ci = cms.ContentInfo({"content_type": "signed_data", "content": sd})

    resultado = validar_cades(conteudo, ci.dump())

    assert resultado.estruturalmente_valido is False
    assert "1 SignerInfo" in (resultado.motivo_falha or "")


def test_sem_atributos_assinados_e_invalido(certificado_teste: CertificadoConfig) -> None:
    conteudo = b"conteudo sem atributos assinados"
    assinatura = (
        _pkcs7.PKCS7SignatureBuilder()
        .set_data(conteudo)
        .add_signer(
            certificado_teste.certificado,
            certificado_teste.chave_privada,
            hashes.SHA256(),
        )
        .sign(
            Encoding.DER,
            [
                _pkcs7.PKCS7Options.DetachedSignature,
                _pkcs7.PKCS7Options.Binary,
                _pkcs7.PKCS7Options.NoAttributes,
            ],
        )
    )

    resultado = validar_cades(conteudo, assinatura)

    assert resultado.estruturalmente_valido is False
    assert "sem atributos assinados" in (resultado.motivo_falha or "")


def test_atributo_cades_bes_faltando_e_invalido(certificado_teste: CertificadoConfig) -> None:
    """Remove só o atributo `signing_time` de um CMS válido (mantendo
    `content_type`/`message_digest`) -- o caso realista de um CMS quase
    conforme, faltando exatamente um atributo obrigatório."""
    conteudo = b"conteudo com um atributo CAdES-BES faltando"
    _assinatura, ctx = _cms_valido(certificado_teste, conteudo)
    sd = ctx["sd"]
    si = sd["signer_infos"][0]
    atributos_restantes = [a for a in si["signed_attrs"] if a["type"].native != "signing_time"]
    si["signed_attrs"] = cms.CMSAttributes(atributos_restantes)
    sd["signer_infos"] = cms.SignerInfos([si])
    ci = cms.ContentInfo({"content_type": "signed_data", "content": sd})

    resultado = validar_cades(conteudo, ci.dump())

    assert resultado.estruturalmente_valido is False
    assert "signing_time" in (resultado.motivo_falha or "")


def test_sem_certificado_embutido_e_invalido(certificado_teste: CertificadoConfig) -> None:
    conteudo = b"conteudo sem certificado embutido"
    assinatura = (
        _pkcs7.PKCS7SignatureBuilder()
        .set_data(conteudo)
        .add_signer(
            certificado_teste.certificado,
            certificado_teste.chave_privada,
            hashes.SHA256(),
        )
        .sign(
            Encoding.DER,
            [
                _pkcs7.PKCS7Options.DetachedSignature,
                _pkcs7.PKCS7Options.Binary,
                _pkcs7.PKCS7Options.NoCerts,
            ],
        )
    )

    resultado = validar_cades(conteudo, assinatura)

    assert resultado.estruturalmente_valido is False
    assert "certificado embutido" in (resultado.motivo_falha or "")


def test_assinatura_criptografica_corrompida_reprova_sem_derrubar_message_digest(
    certificado_teste: CertificadoConfig,
) -> None:
    """Corrompe só os bytes da assinatura RSA (não o conteúdo, não o
    `message-digest`) -- o único jeito de alcançar o ramo `except
    InvalidSignature` de `validar_cades` (T11: `assinar_cades`/
    `validar_cades` nunca produzem essa combinação sozinhos)."""
    conteudo = b"conteudo com assinatura RSA corrompida"
    _assinatura, ctx = _cms_valido(certificado_teste, conteudo)
    sd = ctx["sd"]
    si = sd["signer_infos"][0]
    bytes_corrompidos = bytearray(si["signature"].native)
    bytes_corrompidos[10] ^= 0xFF
    si["signature"] = bytes(bytes_corrompidos)
    sd["signer_infos"] = cms.SignerInfos([si])
    ci = cms.ContentInfo({"content_type": "signed_data", "content": sd})

    resultado = validar_cades(conteudo, ci.dump())

    assert resultado.estruturalmente_valido is True
    assert resultado.message_digest_confere is True
    assert resultado.assinatura_criptografica_valida is False
    assert resultado.valido is False
