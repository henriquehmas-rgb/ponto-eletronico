"""RelayState assinado (T22, A10): emissao, validacao, e rejeicao de
adulteracao/expiracao. `apps/api/tests/f13/sso/saml/conftest.py` publica
`SSO_SAML_ESTADO_CHAVE` no ambiente antes de qualquer teste rodar."""

from __future__ import annotations

import datetime as _dt
import uuid

import pytest

from app.core.config import obter_configuracao
from app.core.erros import ErroDeAplicacao
from app.identidade.sso.saml import estado


def test_emitir_e_validar_relay_state_ida_e_volta() -> None:
    tenant_id = uuid.uuid4()
    token = estado.gerar_estado(tenant_id=tenant_id, request_id="_abc123")

    resultado = estado.validar_estado(token)

    assert resultado.tenant_id == tenant_id
    assert resultado.request_id == "_abc123"
    assert resultado.nonce


def test_dois_estados_tem_nonce_diferente() -> None:
    tenant_id = uuid.uuid4()
    primeiro = estado.gerar_estado(tenant_id=tenant_id, request_id="_a")
    segundo = estado.gerar_estado(tenant_id=tenant_id, request_id="_a")

    assert primeiro != segundo
    assert estado.validar_estado(primeiro).nonce != estado.validar_estado(segundo).nonce


def test_relay_state_adulterado_e_rejeitado() -> None:
    token = estado.gerar_estado(tenant_id=uuid.uuid4(), request_id="_abc")
    # Troca um caractere do MEIO do segmento de assinatura (nao o ultimo do
    # token inteiro): o ultimo caractere base64url de uma assinatura HS256
    # (32 bytes = 256 bits, nao multiplo de 6) carrega 2 bits de sobra que o
    # decodificador descarta -- ~1 em 4 caracteres alternativos decodifica
    # para o MESMO byte final, e a adulteracao vira um "achado" que nao
    # achou nada (achado real: flakiness reproduzida nesta sessao, causa
    # raiz identificada por leitura de `app.identidade.sso.saml.estado`,
    # jwt.encode/HS256). Um caractere do meio da assinatura nao tem essa
    # ambiguidade de borda -- qualquer troca ali sempre muda o byte
    # decodificado.
    partes = token.split(".")
    assinatura = partes[-1]
    indice_meio = len(assinatura) // 2
    substituto = "a" if assinatura[indice_meio] != "a" else "b"
    assinatura_adulterada = assinatura[:indice_meio] + substituto + assinatura[indice_meio + 1 :]
    adulterado = ".".join([*partes[:-1], assinatura_adulterada])

    with pytest.raises(ErroDeAplicacao) as excinfo:
        estado.validar_estado(adulterado)
    assert excinfo.value.codigo == "PONTO-AUTH-004"


def test_relay_state_expirado_e_rejeitado() -> None:
    agora_no_passado = _dt.datetime.now(_dt.UTC) - _dt.timedelta(minutes=30)
    token = estado.gerar_estado(tenant_id=uuid.uuid4(), request_id="_abc", agora=agora_no_passado)

    with pytest.raises(ErroDeAplicacao) as excinfo:
        estado.validar_estado(token)
    assert excinfo.value.codigo == "PONTO-AUTH-004"


def test_relay_state_ausente_e_rejeitado() -> None:
    with pytest.raises(ErroDeAplicacao) as excinfo:
        estado.validar_estado("")
    assert excinfo.value.codigo == "PONTO-AUTH-004"


def test_relay_state_de_outro_processo_com_chave_diferente_e_rejeitado(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`obter_configuracao()` e cacheada (`functools.lru_cache`) -- o proprio
    docstring do modulo instrui limpar o cache apos mexer em `os.environ`."""
    token = estado.gerar_estado(tenant_id=uuid.uuid4(), request_id="_abc")
    monkeypatch.setenv("SSO_SAML_ESTADO_CHAVE", "uma-chave-completamente-diferente")
    obter_configuracao.cache_clear()
    try:
        with pytest.raises(ErroDeAplicacao) as excinfo:
            estado.validar_estado(token)
        assert excinfo.value.codigo == "PONTO-AUTH-004"
    finally:
        obter_configuracao.cache_clear()
