"""`app.identidade.sso.oidc.estado`: assinatura/validacao do `state` anti-CSRF.

Sem banco -- pura em memoria, so precisa de `SSO_ESTADO_CHAVE_SECRETA` no
ambiente (a fixture `_chave_estado` cuida disso e limpa o cache de
`obter_configuracao` antes/depois de cada teste)."""

from __future__ import annotations

import datetime as _dt
import os
import uuid

import jwt as pyjwt
import pytest

from app.core.config import obter_configuracao
from app.core.erros import ErroDeAplicacao
from app.identidade.sso.oidc import estado as estado_mod


@pytest.fixture(autouse=True)
def _chave_estado() -> None:
    anterior = os.environ.get("SSO_ESTADO_CHAVE_SECRETA")
    os.environ["SSO_ESTADO_CHAVE_SECRETA"] = "chave-de-teste-nao-usada-em-producao"
    obter_configuracao.cache_clear()
    yield
    if anterior is None:
        os.environ.pop("SSO_ESTADO_CHAVE_SECRETA", None)
    else:
        os.environ["SSO_ESTADO_CHAVE_SECRETA"] = anterior
    obter_configuracao.cache_clear()


def test_gerar_e_validar_estado_ida_e_volta() -> None:
    tenant_id = uuid.uuid4()
    state, nonce = estado_mod.gerar_estado(tenant_id=tenant_id, provedor="google")

    resolvido = estado_mod.validar_estado(state, provedor_esperado="google")

    assert resolvido.tenant_id == tenant_id
    assert resolvido.provedor == "google"
    assert resolvido.nonce == nonce


def test_validar_estado_provedor_errado_rejeita() -> None:
    state, _nonce = estado_mod.gerar_estado(tenant_id=uuid.uuid4(), provedor="google")

    with pytest.raises(ErroDeAplicacao) as excinfo:
        estado_mod.validar_estado(state, provedor_esperado="entra_id")

    assert excinfo.value.codigo == "PONTO-AUTH-004"


def test_validar_estado_expirado_rejeita() -> None:
    agora = _dt.datetime.now(_dt.UTC) - _dt.timedelta(seconds=estado_mod.VIDA_ESTADO_S + 60)
    state, _nonce = estado_mod.gerar_estado(tenant_id=uuid.uuid4(), provedor="google", agora=agora)

    with pytest.raises(ErroDeAplicacao) as excinfo:
        estado_mod.validar_estado(state, provedor_esperado="google")

    assert excinfo.value.codigo == "PONTO-AUTH-004"


def test_validar_estado_assinatura_adulterada_rejeita() -> None:
    state, _nonce = estado_mod.gerar_estado(tenant_id=uuid.uuid4(), provedor="google")
    adulterado = state[:-2] + ("aa" if state[-2:] != "aa" else "bb")

    with pytest.raises(ErroDeAplicacao) as excinfo:
        estado_mod.validar_estado(adulterado, provedor_esperado="google")

    assert excinfo.value.codigo == "PONTO-AUTH-004"


def test_validar_estado_assinado_com_outra_chave_rejeita() -> None:
    state_de_outra_chave = pyjwt.encode(
        {
            "tenant_id": str(uuid.uuid4()),
            "provedor": "google",
            "nonce": "x",
            "iat": int(_dt.datetime.now(_dt.UTC).timestamp()),
            "exp": int((_dt.datetime.now(_dt.UTC) + _dt.timedelta(minutes=5)).timestamp()),
        },
        "outra-chave-completamente-diferente",
        algorithm="HS256",
    )

    with pytest.raises(ErroDeAplicacao) as excinfo:
        estado_mod.validar_estado(state_de_outra_chave, provedor_esperado="google")

    assert excinfo.value.codigo == "PONTO-AUTH-004"


def test_validar_estado_sem_chave_configurada_falha_fechado() -> None:
    os.environ.pop("SSO_ESTADO_CHAVE_SECRETA", None)
    obter_configuracao.cache_clear()

    with pytest.raises(ErroDeAplicacao) as excinfo:
        estado_mod.gerar_estado(tenant_id=uuid.uuid4(), provedor="google")

    assert excinfo.value.codigo == "PONTO-INT-001"


# =============================================================================
# RFC-019 -- vinculo de navegador anti-login-CSRF (achado de revisao
# adversarial no fechamento da F13).
# =============================================================================


def _hash(vinculo: str) -> str:
    import hashlib

    return hashlib.sha256(vinculo.encode("utf-8")).hexdigest()


def test_gerar_e_validar_estado_com_vinculo_correto_ida_e_volta() -> None:
    vinculo = "vinculo-do-navegador-legitimo"
    state, _nonce = estado_mod.gerar_estado(
        tenant_id=uuid.uuid4(), provedor="google", vinculo_hash=_hash(vinculo)
    )

    resolvido = estado_mod.validar_estado(state, provedor_esperado="google", vinculo=vinculo)

    assert resolvido.provedor == "google"


def test_validar_estado_sem_vinculo_quando_state_exige_rejeita() -> None:
    state, _nonce = estado_mod.gerar_estado(
        tenant_id=uuid.uuid4(), provedor="google", vinculo_hash=_hash("vinculo-qualquer")
    )

    with pytest.raises(ErroDeAplicacao) as excinfo:
        estado_mod.validar_estado(state, provedor_esperado="google", vinculo=None)

    assert excinfo.value.codigo == "PONTO-AUTH-004"


def test_validar_estado_com_vinculo_de_outro_navegador_rejeita() -> None:
    """O cenario central da RFC-019: `state` genuino, `vinculo` de um
    navegador DIFERENTE do que gerou o `vinculoHash` embutido -- prova que a
    checagem discrimina corretamente, nao so ausencia total."""
    state, _nonce = estado_mod.gerar_estado(
        tenant_id=uuid.uuid4(), provedor="google", vinculo_hash=_hash("vinculo-da-vitima")
    )

    with pytest.raises(ErroDeAplicacao) as excinfo:
        estado_mod.validar_estado(state, provedor_esperado="google", vinculo="vinculo-do-atacante")

    assert excinfo.value.codigo == "PONTO-AUTH-004"


def test_gerar_e_validar_estado_sem_vinculo_nenhum_continua_funcionando() -> None:
    """Retrocompatibilidade da propria funcao (o roteador e quem exige
    `vinculo_hash` para google/entra_id -- `estado.py` continua utilizavel
    sem ele, ex.: por um teste unitario que nao exercita CSRF)."""
    state, nonce = estado_mod.gerar_estado(tenant_id=uuid.uuid4(), provedor="google")

    resolvido = estado_mod.validar_estado(state, provedor_esperado="google")

    assert resolvido.nonce == nonce
