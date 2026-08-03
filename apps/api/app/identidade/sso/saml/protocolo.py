"""Fala SAML 2.0 de verdade: monta o AuthnRequest e valida a assinatura da
asserção de volta contra o certificado X.509 do IdP do tenant (T20/T22, A10).

**Escolha de biblioteca (T20).** `python3-saml` (pacote `onelogin.saml2`),
mantida pela OneLogin, MIT. Alternativa avaliada: `pysaml2` -- mais completa
(cobre tambem o lado IdP, que este sistema nunca precisa: somos sempre SP),
API mais pesada para o uso estreito daqui (validar UMA asserção assinada
contra UM certificado). `python3-saml` e a lib SP-only mais citada em guias de
integracao Python e sua API (`OneLogin_Saml2_Response.is_valid`) cobre
exatamente o que a fase exige: assinatura, `Conditions`
(NotBefore/NotOnOrAfter), `AudienceRestriction`, `Destination` e
`InResponseTo`, tudo com `strict=True`.

**Custo de dependencia (T20, "documente o custo de imagem Docker antes de
escolher").** `python3-saml` depende de `lxml` e `xmlsec` (bindings do
`libxmlsec1`, biblioteca C). Confirmado por instalacao real neste ambiente
(Windows, Python 3.12): `pip install python3-saml` traz wheels prontos
`cp312-win_amd64` para `lxml` e `xmlsec`, sem precisar compilar nada. Em
produção (`apps/api` roda em imagem Debian slim), `manylinux` wheels cobrem a
mesma superficie sem exigir `apt install libxmlsec1-dev` na imagem final --
so seria necessario se um wheel pre-compilado nao existisse para o alvo, o
que nao e o caso hoje (confirmado por `pip install --dry-run` nesta sessao).

**Prova de conceito (T20, "prototipo de troca... validado contra um IdP de
teste").** Antes de escrever este modulo, foi montado um IdP falso local
(certificado autoassinado gerado com `cryptography`, asserção XML assinada
com `xmlsec` diretamente) e confirmado que `OneLogin_Saml2_Response.is_valid`
aceita a asserção intacta e REJEITA a mesma asserção com um unico campo
(NameID) alterado apos a assinatura, sem gerar excecao nao tratada -- o
mesmo mecanismo que `apps/api/tests/f13/sso/saml/conftest.py` reproduz para
o teste adversarial oficial da fase (critério de aceite do T22).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from onelogin.saml2.authn_request import OneLogin_Saml2_Authn_Request
from onelogin.saml2.response import OneLogin_Saml2_Response
from onelogin.saml2.settings import OneLogin_Saml2_Settings
from onelogin.saml2.utils import OneLogin_Saml2_Utils

from app.core.erros import ErroDeAplicacao
from app.identidade.sso.saml.config import ConfigIdpSaml

BINDING_REDIRECT = "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
BINDING_POST = "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
NAME_ID_FORMAT = "urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress"


def _montar_settings(
    config: ConfigIdpSaml, *, acs_url: str, sp_entity_id: str
) -> OneLogin_Saml2_Settings:
    """`PONTO-REC-001` quando o tenant nao tem IdP SAML configurado --
    trata como recurso ausente (a propria configuracao), nao como falha de
    autenticacao: o cliente ainda nao chegou a apresentar credencial nenhuma.
    """
    if not config.configurado:
        raise ErroDeAplicacao("PONTO-REC-001", detalhe="IdP SAML nao configurado para este tenant")
    settings_dict: dict[str, Any] = {
        "strict": True,
        "sp": {
            "entityId": sp_entity_id,
            "assertionConsumerService": {"url": acs_url, "binding": BINDING_POST},
            "NameIDFormat": NAME_ID_FORMAT,
        },
        "idp": {
            "entityId": config.entity_id,
            "singleSignOnService": {"url": config.sso_url, "binding": BINDING_REDIRECT},
            "x509cert": config.certificado_x509,
        },
        "security": {
            # Nunca aceita asserção sem assinatura ("modo de compatibilidade")
            # -- e o requisito nao negociavel do criterio de aceite do T22.
            "wantAssertionsSigned": True,
            "wantMessagesSigned": False,
            "wantNameId": True,
            # A asserção minima que este sistema exige (NameID + Conditions +
            # AuthnStatement) nao inclui AttributeStatement -- exigi-lo
            # rejeitaria IdPs de teste que nao mandam atributo nenhum.
            "wantAttributeStatement": False,
        },
    }
    return OneLogin_Saml2_Settings(settings_dict, sp_validation_only=True)


def montar_authn_request(
    config: ConfigIdpSaml, *, acs_url: str, sp_entity_id: str
) -> tuple[str, str]:
    """Monta o AuthnRequest (deflate + base64, perfil HTTP-Redirect).

    Devolve `(saml_request, request_id)`: o chamador
    (`app.routers.sso.iniciar`) usa `request_id` para assinar o RelayState
    (`app.identidade.sso.saml.estado.gerar_estado`) ANTES de montar a URL
    final de redirecionamento com `montar_url_redirecionamento` -- por isso
    esta funcao devolve as duas pecas separadas, nunca a URL pronta.
    """
    settings = _montar_settings(config, acs_url=acs_url, sp_entity_id=sp_entity_id)
    authn_request = OneLogin_Saml2_Authn_Request(settings)
    return authn_request.get_request(), authn_request.get_id()


def montar_url_redirecionamento(
    config: ConfigIdpSaml, *, saml_request: str, relay_state: str
) -> str:
    assert config.sso_url is not None  # noqa: S101 -- invariante ja garantida por `configurado`
    url: str = OneLogin_Saml2_Utils.redirect(
        config.sso_url, {"SAMLRequest": saml_request, "RelayState": relay_state}
    )
    return url


@dataclass(frozen=True, slots=True)
class AssercaoValidada:
    name_id: str


def validar_resposta(
    config: ConfigIdpSaml,
    *,
    acs_url: str,
    sp_entity_id: str,
    saml_response_b64: str,
    request_data: dict[str, Any],
    request_id: str,
) -> AssercaoValidada:
    """`PONTO-AUTH-004` para qualquer falha de validacao: assinatura ausente
    ou que nao confere, `Conditions`/`Destination`/`InResponseTo` fora do
    esperado, ou resposta malformada. Nunca aceita uma asserção sem prova
    criptografica de origem.
    """
    settings = _montar_settings(config, acs_url=acs_url, sp_entity_id=sp_entity_id)
    try:
        resposta = OneLogin_Saml2_Response(settings, saml_response_b64)
    except Exception as exc:
        raise ErroDeAplicacao("PONTO-AUTH-004", detalhe="SAMLResponse malformado") from exc

    valido = resposta.is_valid(request_data, request_id=request_id)
    if not valido:
        raise ErroDeAplicacao(
            "PONTO-AUTH-004",
            detalhe="assinatura ou conteudo da asserção SAML invalidos",
            contexto_log={"erro_biblioteca": resposta.get_error()},
        )

    name_id = resposta.get_nameid()
    if not name_id:
        raise ErroDeAplicacao("PONTO-AUTH-004", detalhe="asserção sem NameID")
    return AssercaoValidada(name_id=name_id)
