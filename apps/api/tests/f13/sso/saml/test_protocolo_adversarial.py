"""Teste adversarial oficial do T22 (PCF F13, criterio de aceite 11 e §7):
assinatura de asserção SAML adulterada precisa ser rejeitada.

Usa o IdP falso de `conftest.py` (certificado autoassinado, asserção
assinada de verdade com `xmlsec`) para provar as quatro combinacoes:
asserção intacta aceita, `NameID` adulterado apos assinar rejeitado,
asserção sem assinatura nenhuma rejeitada, e certificado de outro par de
chaves (nao o configurado para o tenant) rejeitado.
"""

from __future__ import annotations

import datetime as _dt

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from app.core.erros import ErroDeAplicacao
from app.identidade.sso.saml.config import ConfigIdpSaml
from app.identidade.sso.saml.protocolo import montar_authn_request, validar_resposta
from tests.f13.sso.saml.conftest import IdpFalso, adulterar_name_id, montar_saml_response

ACS_URL = "https://api.ponto.teste.local/v1/sso/saml/acs"
SP_ENTITY_ID = ACS_URL
ISSUER_IDP = "https://idp-teste-f13-a10.example.com/metadata"


def _config(idp: IdpFalso) -> ConfigIdpSaml:
    return ConfigIdpSaml(
        entity_id=ISSUER_IDP,
        sso_url="https://idp-teste-f13-a10.example.com/sso",
        certificado_x509=idp.certificado_pem_sem_marcadores,
    )


def _request_data() -> dict[str, object]:
    return {
        "https": "on",
        "http_host": "api.ponto.teste.local",
        "script_name": "/v1/sso/saml/acs",
        "get_data": {},
        "post_data": {},
    }


def test_authn_request_tem_id_unico(idp_falso: IdpFalso) -> None:
    config = _config(idp_falso)
    _, id1 = montar_authn_request(config, acs_url=ACS_URL, sp_entity_id=SP_ENTITY_ID)
    _, id2 = montar_authn_request(config, acs_url=ACS_URL, sp_entity_id=SP_ENTITY_ID)
    assert id1 != id2
    assert id1 and id2


def test_assercao_intacta_e_aceita(idp_falso: IdpFalso) -> None:
    config = _config(idp_falso)
    resposta = montar_saml_response(
        idp_falso,
        name_id="pessoa@example.com",
        audience=SP_ENTITY_ID,
        acs_url=ACS_URL,
        issuer=ISSUER_IDP,
        in_response_to="_req123",
    )

    assercao = validar_resposta(
        config,
        acs_url=ACS_URL,
        sp_entity_id=SP_ENTITY_ID,
        saml_response_b64=resposta,
        request_data=_request_data(),
        request_id="_req123",
    )

    assert assercao.name_id == "pessoa@example.com"


def test_assercao_com_name_id_adulterado_apos_assinar_e_rejeitada(idp_falso: IdpFalso) -> None:
    """O teste adversarial central do T22: o NameID e trocado DEPOIS que a
    asserção ja foi assinada, sem gerar nova assinatura -- exatamente o
    ataque que `wantAssertionsSigned` existe para barrar."""
    config = _config(idp_falso)
    resposta_legitima = montar_saml_response(
        idp_falso,
        name_id="vitima@example.com",
        audience=SP_ENTITY_ID,
        acs_url=ACS_URL,
        issuer=ISSUER_IDP,
        in_response_to="_req456",
    )
    resposta_adulterada = adulterar_name_id(
        resposta_legitima, de="vitima@example.com", para="atacante@example.com"
    )

    with pytest.raises(ErroDeAplicacao) as excinfo:
        validar_resposta(
            config,
            acs_url=ACS_URL,
            sp_entity_id=SP_ENTITY_ID,
            saml_response_b64=resposta_adulterada,
            request_data=_request_data(),
            request_id="_req456",
        )
    assert excinfo.value.codigo == "PONTO-AUTH-004"


def test_assercao_sem_assinatura_e_rejeitada(idp_falso: IdpFalso) -> None:
    config = _config(idp_falso)
    resposta_sem_assinatura = montar_saml_response(
        idp_falso,
        name_id="pessoa@example.com",
        audience=SP_ENTITY_ID,
        acs_url=ACS_URL,
        issuer=ISSUER_IDP,
        in_response_to="_req789",
        assinar=False,
    )

    with pytest.raises(ErroDeAplicacao) as excinfo:
        validar_resposta(
            config,
            acs_url=ACS_URL,
            sp_entity_id=SP_ENTITY_ID,
            saml_response_b64=resposta_sem_assinatura,
            request_data=_request_data(),
            request_id="_req789",
        )
    assert excinfo.value.codigo == "PONTO-AUTH-004"


def test_assercao_assinada_por_chave_de_outro_idp_e_rejeitada() -> None:
    """O certificado configurado para o tenant e de um IdP; a asserção chega
    assinada por outro par de chaves inteiramente -- simula um atacante com
    seu proprio par de chaves tentando se passar pelo IdP do tenant."""

    def _gerar() -> IdpFalso:
        chave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        nome = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "outro-idp")])
        agora = _dt.datetime.now(_dt.UTC)
        cert = (
            x509.CertificateBuilder()
            .subject_name(nome)
            .issuer_name(nome)
            .public_key(chave.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(agora - _dt.timedelta(days=1))
            .not_valid_after(agora + _dt.timedelta(days=3650))
            .sign(chave, hashes.SHA256())
        )
        return IdpFalso(chave=chave, certificado=cert)

    idp_legitimo = _gerar()
    idp_atacante = _gerar()
    config_do_tenant = _config(idp_legitimo)  # so confia no certificado do IdP legitimo

    resposta_assinada_pelo_atacante = montar_saml_response(
        idp_atacante,
        name_id="pessoa@example.com",
        audience=SP_ENTITY_ID,
        acs_url=ACS_URL,
        issuer=ISSUER_IDP,
        in_response_to="_reqXYZ",
    )

    with pytest.raises(ErroDeAplicacao) as excinfo:
        validar_resposta(
            config_do_tenant,
            acs_url=ACS_URL,
            sp_entity_id=SP_ENTITY_ID,
            saml_response_b64=resposta_assinada_pelo_atacante,
            request_data=_request_data(),
            request_id="_reqXYZ",
        )
    assert excinfo.value.codigo == "PONTO-AUTH-004"


def test_config_ausente_levanta_recurso_nao_encontrado() -> None:
    config_vazia = ConfigIdpSaml(entity_id=None, sso_url=None, certificado_x509=None)
    with pytest.raises(ErroDeAplicacao) as excinfo:
        montar_authn_request(config_vazia, acs_url=ACS_URL, sp_entity_id=SP_ENTITY_ID)
    assert excinfo.value.codigo == "PONTO-REC-001"
