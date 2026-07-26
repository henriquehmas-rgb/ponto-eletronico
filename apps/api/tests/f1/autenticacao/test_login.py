"""T4 -- senha, login e bloqueio progressivo."""

from __future__ import annotations

import datetime as dt
import secrets

import httpx
import sqlalchemy as sa
from fastapi.testclient import TestClient
from ponto_contracts import Credencial

from app.db.sessao import aplicar_tenant
from app.identidade.autenticacao import bloqueio
from tests.f1.autenticacao.conftest import IdentidadeDeTeste, cabecalhos


def _login(cliente: TestClient, identidade: IdentidadeDeTeste, senha: str) -> httpx.Response:
    return cliente.post(
        "/v1/auth/login",
        json={"email": identidade.email, "senha": senha},
        headers=cabecalhos(identidade.tenant_slug),
    )


def test_login_com_credenciais_corretas_emite_tokens(
    cliente: TestClient, identidade: IdentidadeDeTeste
) -> None:
    resposta = _login(cliente, identidade, identidade.senha)
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["mfaRequerido"] is False
    assert corpo["accessToken"]
    assert corpo["refreshToken"]
    assert corpo["tokenType"] == "Bearer"
    assert corpo["usuario"]["email"] == identidade.email


def test_senha_errada_e_usuario_inexistente_respondem_identico(
    cliente: TestClient, identidade: IdentidadeDeTeste
) -> None:
    """Exigencia explicita do contrato: as duas causas nao podem ser distinguiveis."""
    resposta_senha_errada = _login(cliente, identidade, "senha-completamente-errada")
    resposta_usuario_inexistente = cliente.post(
        "/v1/auth/login",
        json={"email": "nao-existe-de-jeito-nenhum@exemplo.com.br", "senha": "qualquer-coisa-123"},
        headers=cabecalhos(identidade.tenant_slug),
    )

    assert resposta_senha_errada.status_code == 401
    assert resposta_usuario_inexistente.status_code == 401

    corpo_1 = resposta_senha_errada.json()
    corpo_2 = resposta_usuario_inexistente.json()
    # Remove os campos que legitimamente variam por requisicao (correlacao).
    for corpo in (corpo_1, corpo_2):
        corpo.pop("requestId", None)
        corpo.pop("instance", None)
    assert corpo_1 == corpo_2
    assert corpo_1["codigo"] == "PONTO-AUTH-001"


def test_login_tenant_inexistente_responde_ten_001(cliente: TestClient) -> None:
    resposta = cliente.post(
        "/v1/auth/login",
        json={"email": "a@b.com", "senha": "12345678"},
        headers=cabecalhos(f"tenant-que-nao-existe-{secrets.token_hex(4)}"),
    )
    assert resposta.status_code == 404
    assert resposta.json()["codigo"] == "PONTO-TEN-001"


async def test_bloqueio_progressivo_entra_apos_n_falhas_e_libera_depois(
    cliente: TestClient, identidade: IdentidadeDeTeste, sessao_db
) -> None:
    # `LIMITE_TENTATIVAS_LIVRES + 1` falhas: a ULTIMA delas e a que faz
    # `tentativas_falhas` cruzar o limite e grava `bloqueado_ate` -- mas ainda
    # responde 401 comum, porque o bloqueio so e CONSULTADO no INICIO da
    # proxima tentativa, nao na que acabou de estoura-lo.
    for _ in range(bloqueio.LIMITE_TENTATIVAS_LIVRES + 1):
        resposta = _login(cliente, identidade, "senha-errada")
        assert resposta.status_code == 401
        assert resposta.json()["codigo"] == "PONTO-AUTH-001"

    # Agora sim: a tentativa seguinte encontra o bloqueio ja gravado.
    resposta_bloqueio = _login(cliente, identidade, "senha-errada")
    assert resposta_bloqueio.status_code == 423
    assert resposta_bloqueio.json()["codigo"] == "PONTO-AUTH-009"

    # Mesmo com a senha CORRETA, o bloqueio por tempo prevalece.
    resposta_senha_certa_bloqueada = _login(cliente, identidade, identidade.senha)
    assert resposta_senha_certa_bloqueada.status_code == 423
    assert resposta_senha_certa_bloqueada.json()["codigo"] == "PONTO-AUTH-009"

    # Libera manualmente o bloqueio (equivalente a esperar o prazo) e confirma
    # que a senha correta volta a funcionar. `aplicar_tenant` precisa ser
    # chamado de novo: o `SET LOCAL app.tenant_id` da fixture `identidade` nao
    # sobrevive ao `commit` daquela fixture (e ela mesma quem confirma a
    # transacao), entao esta e uma transacao nova, sem tenant publicado.
    await aplicar_tenant(sessao_db, str(identidade.tenant_id))
    await sessao_db.execute(
        sa.update(Credencial)
        .where(
            Credencial.tenant_id == identidade.tenant_id,
            Credencial.usuario_id == identidade.usuario_id,
            Credencial.tipo == "senha",
        )
        .values(bloqueado_ate=dt.datetime.now(dt.UTC) - dt.timedelta(seconds=1))
    )
    await sessao_db.commit()

    resposta_liberada = _login(cliente, identidade, identidade.senha)
    assert resposta_liberada.status_code == 200


async def test_usuario_bloqueado_responde_auth_010(
    cliente: TestClient, identidade: IdentidadeDeTeste, sessao_db
) -> None:
    from ponto_contracts import Usuario

    await aplicar_tenant(sessao_db, str(identidade.tenant_id))
    await sessao_db.execute(
        sa.update(Usuario).where(Usuario.id == identidade.usuario_id).values(status="bloqueado")
    )
    await sessao_db.commit()

    resposta = _login(cliente, identidade, identidade.senha)
    assert resposta.status_code == 401
    assert resposta.json()["codigo"] == "PONTO-AUTH-010"


def test_argon2id_e_o_algoritmo_gravado(identidade: IdentidadeDeTeste) -> None:
    from app.identidade.autenticacao.senha import ALGORITMO

    assert ALGORITMO == "argon2id"
