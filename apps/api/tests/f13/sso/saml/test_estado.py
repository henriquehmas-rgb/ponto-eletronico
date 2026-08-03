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
    # Troca o ultimo caractere do payload assinado -- qualquer bit alterado
    # invalida a assinatura HS256.
    adulterado = token[:-1] + ("a" if token[-1] != "a" else "b")

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
