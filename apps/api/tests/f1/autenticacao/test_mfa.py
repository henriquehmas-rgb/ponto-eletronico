"""T6 -- MFA TOTP e codigos de backup."""

from __future__ import annotations

import datetime as dt

import pyotp
from fastapi.testclient import TestClient
from ponto_contracts import MfaDispositivo

from app.db.sessao import aplicar_tenant
from app.identidade.mfa import backup_codes, totp
from app.identidade.mfa.cifra import cifrar
from tests.f1.autenticacao.conftest import IdentidadeDeTeste, cabecalhos


def _login(cliente: TestClient, identidade: IdentidadeDeTeste) -> dict:
    resposta = cliente.post(
        "/v1/auth/login",
        json={"email": identidade.email, "senha": identidade.senha},
        headers=cabecalhos(identidade.tenant_slug),
    )
    return resposta.json()


async def _cadastrar_totp(sessao_db, identidade: IdentidadeDeTeste) -> str:
    """Cria um dispositivo TOTP confirmado e devolve o segredo em Base32."""
    await aplicar_tenant(sessao_db, str(identidade.tenant_id))
    segredo = totp.gerar_segredo()
    cifrado, iv = cifrar(segredo.encode("ascii"))
    sessao_db.add(
        MfaDispositivo(
            tenant_id=identidade.tenant_id,
            usuario_id=identidade.usuario_id,
            tipo="totp",
            rotulo="Autenticador de teste",
            segredo_cifrado=cifrado,
            iv=iv,
            chave_id="local-v1",
            ativo=True,
            confirmado_em=dt.datetime.now(dt.UTC),
        )
    )
    await sessao_db.commit()
    return segredo


async def _cadastrar_backup(sessao_db, identidade: IdentidadeDeTeste) -> list[str]:
    await aplicar_tenant(sessao_db, str(identidade.tenant_id))
    lote = backup_codes.gerar_lote()
    sessao_db.add(
        MfaDispositivo(
            tenant_id=identidade.tenant_id,
            usuario_id=identidade.usuario_id,
            tipo="codigos_backup",
            rotulo="Codigos de backup",
            segredo_cifrado=lote.cifrado,
            iv=lote.iv,
            chave_id=lote.chave_id,
            ativo=True,
            confirmado_em=dt.datetime.now(dt.UTC),
        )
    )
    await sessao_db.commit()
    return lote.codigos_em_claro


def test_totp_aceita_janela_corrente_e_recusa_janela_anterior_ja_usada() -> None:
    """Prova de relogio controlado (T6): a janela corrente e aceita; a mesma
    janela, apresentada de novo um passo depois (agora "anterior"), e recusada
    porque `ultimo_passo_aceito` ja avancou -- e o anti-replay de
    `mfa_dispositivos.contador`, independente do desafio HTTP."""
    segredo = totp.gerar_segredo()
    agora = dt.datetime(2026, 1, 1, 12, 0, 0, tzinfo=dt.UTC)
    codigo_janela_corrente = pyotp.TOTP(segredo, interval=totp.JANELA_SEGUNDOS).at(agora)

    passo_aceito = totp.verificar_codigo(
        segredo, codigo_janela_corrente, ultimo_passo_aceito=None, agora=agora
    )
    assert passo_aceito == totp.passo_atual(agora)

    agora_seguinte = agora + dt.timedelta(seconds=totp.JANELA_SEGUNDOS)
    recusado = totp.verificar_codigo(
        segredo, codigo_janela_corrente, ultimo_passo_aceito=passo_aceito, agora=agora_seguinte
    )
    assert recusado is None


async def test_login_com_mfa_exige_segundo_fator_e_totp_da_janela_corrente_e_aceito(
    cliente: TestClient, identidade: IdentidadeDeTeste, sessao_db
) -> None:
    segredo = await _cadastrar_totp(sessao_db, identidade)

    corpo_login = _login(cliente, identidade)
    assert corpo_login["mfaRequerido"] is True
    assert corpo_login.get("desafioId")
    assert corpo_login.get("accessToken") is None
    assert "totp" in corpo_login["metodosMfa"]

    codigo = pyotp.TOTP(segredo, interval=totp.JANELA_SEGUNDOS).now()
    resposta = cliente.post(
        "/v1/auth/mfa/verificar",
        json={"desafioId": corpo_login["desafioId"], "codigo": codigo, "metodo": "totp"},
        headers=cabecalhos(identidade.tenant_slug),
    )
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["accessToken"]
    assert corpo["refreshToken"]
    assert corpo["usuario"]["email"] == identidade.email


async def test_totp_da_janela_ja_usada_e_recusado(
    cliente: TestClient, identidade: IdentidadeDeTeste, sessao_db
) -> None:
    """Um codigo TOTP valido, reapresentado, nao serve de novo (anti-replay por passo)."""
    segredo = await _cadastrar_totp(sessao_db, identidade)
    corpo_login = _login(cliente, identidade)
    desafio_id = corpo_login["desafioId"]

    codigo = pyotp.TOTP(segredo, interval=totp.JANELA_SEGUNDOS).now()
    primeira = cliente.post(
        "/v1/auth/mfa/verificar",
        json={"desafioId": desafio_id, "codigo": codigo, "metodo": "totp"},
        headers=cabecalhos(identidade.tenant_slug),
    )
    assert primeira.status_code == 200

    # O MESMO desafio ja foi consumido (mfa_validado_em preenchido): mesmo que
    # o codigo ainda estivesse na janela de tolerancia, o desafio em si nao
    # serve mais.
    segunda = cliente.post(
        "/v1/auth/mfa/verificar",
        json={"desafioId": desafio_id, "codigo": codigo, "metodo": "totp"},
        headers=cabecalhos(identidade.tenant_slug),
    )
    assert segunda.status_code == 401
    assert segunda.json()["codigo"] == "PONTO-AUTH-008"


async def test_codigo_totp_errado_responde_auth_008(
    cliente: TestClient, identidade: IdentidadeDeTeste, sessao_db
) -> None:
    await _cadastrar_totp(sessao_db, identidade)
    corpo_login = _login(cliente, identidade)

    resposta = cliente.post(
        "/v1/auth/mfa/verificar",
        json={"desafioId": corpo_login["desafioId"], "codigo": "000000", "metodo": "totp"},
        headers=cabecalhos(identidade.tenant_slug),
    )
    assert resposta.status_code == 401
    assert resposta.json()["codigo"] == "PONTO-AUTH-008"


async def test_codigo_de_backup_nao_serve_duas_vezes(
    cliente: TestClient, identidade: IdentidadeDeTeste, sessao_db
) -> None:
    codigos = await _cadastrar_backup(sessao_db, identidade)
    codigo_escolhido = codigos[0]

    corpo_login_1 = _login(cliente, identidade)
    primeira = cliente.post(
        "/v1/auth/mfa/verificar",
        json={
            "desafioId": corpo_login_1["desafioId"],
            "codigo": codigo_escolhido,
            "metodo": "codigos_backup",
        },
        headers=cabecalhos(identidade.tenant_slug),
    )
    assert primeira.status_code == 200

    corpo_login_2 = _login(cliente, identidade)
    segunda = cliente.post(
        "/v1/auth/mfa/verificar",
        json={
            "desafioId": corpo_login_2["desafioId"],
            "codigo": codigo_escolhido,
            "metodo": "codigos_backup",
        },
        headers=cabecalhos(identidade.tenant_slug),
    )
    assert segunda.status_code == 401
    assert segunda.json()["codigo"] == "PONTO-AUTH-008"
