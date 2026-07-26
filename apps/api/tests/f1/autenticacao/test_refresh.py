"""T5 -- JWT RS256, sessao e refresh rotativo com deteccao de reuso."""

from __future__ import annotations

import sqlalchemy as sa
from fastapi.testclient import TestClient
from ponto_contracts import Sessao

from app.db.sessao import aplicar_tenant
from tests.f1.autenticacao.conftest import IdentidadeDeTeste, cabecalhos


def _login(cliente: TestClient, identidade: IdentidadeDeTeste) -> dict:
    resposta = cliente.post(
        "/v1/auth/login",
        json={"email": identidade.email, "senha": identidade.senha},
        headers=cabecalhos(identidade.tenant_slug),
    )
    assert resposta.status_code == 200
    return resposta.json()


def _refresh(cliente: TestClient, identidade: IdentidadeDeTeste, refresh_token: str):
    return cliente.post(
        "/v1/auth/refresh",
        json={"refreshToken": refresh_token},
        headers=cabecalhos(identidade.tenant_slug),
    )


def test_refresh_rotaciona_e_emite_novo_par(
    cliente: TestClient, identidade: IdentidadeDeTeste
) -> None:
    corpo_login = _login(cliente, identidade)
    resposta = _refresh(cliente, identidade, corpo_login["refreshToken"])
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["accessToken"] != corpo_login["accessToken"]
    assert corpo["refreshToken"] != corpo_login["refreshToken"]
    assert corpo["sessaoId"] == corpo_login["sessaoId"]


async def test_reapresentar_token_ja_usado_revoga_a_familia_inteira(
    cliente: TestClient, identidade: IdentidadeDeTeste, sessao_db
) -> None:
    corpo_login = _login(cliente, identidade)
    token_0 = corpo_login["refreshToken"]

    # Rotaciona tres vezes: token_0 -> token_1 -> token_2 -> token_3.
    token_1 = _refresh(cliente, identidade, token_0).json()["refreshToken"]
    token_2 = _refresh(cliente, identidade, token_1).json()["refreshToken"]
    resposta_3 = _refresh(cliente, identidade, token_2)
    assert resposta_3.status_code == 200
    token_3 = resposta_3.json()["refreshToken"]

    # Reapresenta o PRIMEIRO token (ja consumido na rotacao para token_1).
    resposta_reuso = _refresh(cliente, identidade, token_0)
    assert resposta_reuso.status_code == 401
    assert resposta_reuso.json()["codigo"] == "PONTO-AUTH-005"

    # O token mais recente (nunca usado) TAMBEM deve ter sido revogado: a
    # familia inteira cai, nao so o token reapresentado.
    resposta_com_token_novo = _refresh(cliente, identidade, token_3)
    assert resposta_com_token_novo.status_code == 401
    assert resposta_com_token_novo.json()["codigo"] == "PONTO-AUTH-006"

    # A sessao foi encerrada com o motivo correto.
    await aplicar_tenant(sessao_db, str(identidade.tenant_id))
    linha = (
        await sessao_db.execute(
            sa.select(Sessao).where(
                Sessao.tenant_id == identidade.tenant_id,
                Sessao.id == corpo_login["sessaoId"],
            )
        )
    ).scalar_one()
    assert linha.encerrada_em is not None
    assert linha.motivo_encerramento == "reuso_token"


async def test_reuso_encerra_sessao_com_motivo_correto(
    cliente: TestClient, identidade: IdentidadeDeTeste, sessao_db
) -> None:
    corpo_login = _login(cliente, identidade)
    token_0 = corpo_login["refreshToken"]
    _refresh(cliente, identidade, token_0)  # rotaciona uma vez
    resposta_reuso = _refresh(cliente, identidade, token_0)  # reapresenta o usado
    assert resposta_reuso.status_code == 401
    assert resposta_reuso.json()["codigo"] == "PONTO-AUTH-005"

    await aplicar_tenant(sessao_db, str(identidade.tenant_id))
    linha = (
        await sessao_db.execute(
            sa.select(Sessao).where(
                Sessao.tenant_id == identidade.tenant_id,
                Sessao.id == corpo_login["sessaoId"],
            )
        )
    ).scalar_one()
    assert linha.encerrada_em is not None
    assert linha.motivo_encerramento == "reuso_token"


def test_refresh_com_token_invalido_responde_auth_006(
    cliente: TestClient, identidade: IdentidadeDeTeste
) -> None:
    resposta = _refresh(cliente, identidade, "token-que-nunca-existiu-abc123")
    assert resposta.status_code == 401
    assert resposta.json()["codigo"] == "PONTO-AUTH-006"
