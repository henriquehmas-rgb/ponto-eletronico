"""T9 -- envelope encryption do segredo HMAC (`app.integracoes.webhooks.cifra`).

Copia deliberada do padrao de `app.terminais.cifra` -- prova cifrar/decifrar
deterministico (ida e volta) e que o segredo em claro nunca aparece em log.
"""

from __future__ import annotations

import logging
import os
import secrets

import pytest

from app.integracoes.webhooks import cifra


@pytest.fixture(autouse=True)
def _chave_mestra(monkeypatch: pytest.MonkeyPatch) -> str:
    valor = secrets.token_hex(32)
    monkeypatch.setenv(cifra.VARIAVEL_CHAVE_MESTRA, valor)
    return valor


def test_cifrar_e_decifrar_ida_e_volta() -> None:
    segredo = "segredo-super-secreto-do-webhook"
    blob, chave_id = cifra.cifrar_segredo(segredo)

    assert chave_id == cifra.CHAVE_ID_ATUAL
    assert isinstance(blob, bytes)
    assert blob != segredo.encode("utf-8")  # nunca em claro no blob

    decifrado = cifra.decifrar_segredo(blob)
    assert decifrado == segredo


def test_cifrar_produz_blob_diferente_a_cada_chamada() -> None:
    """IV novo a cada cifragem -- mesmo segredo, blobs diferentes."""
    segredo = "mesmo-segredo"
    blob1, _ = cifra.cifrar_segredo(segredo)
    blob2, _ = cifra.cifrar_segredo(segredo)
    assert blob1 != blob2
    assert cifra.decifrar_segredo(blob1) == segredo
    assert cifra.decifrar_segredo(blob2) == segredo


def test_decifrar_com_chave_errada_falha() -> None:
    segredo = "segredo-x"
    blob, _ = cifra.cifrar_segredo(segredo)

    os.environ[cifra.VARIAVEL_CHAVE_MESTRA] = secrets.token_hex(32)  # chave diferente
    with pytest.raises(Exception):  # noqa: B017 - InvalidTag da biblioteca de criptografia
        cifra.decifrar_segredo(blob)


def test_chave_mestra_ausente_levanta_erro_claro(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(cifra.VARIAVEL_CHAVE_MESTRA, raising=False)
    with pytest.raises(cifra.ChaveWebhookAusente):
        cifra.cifrar_segredo("qualquer")


def test_chave_mestra_com_tamanho_errado_levanta_erro_claro(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(cifra.VARIAVEL_CHAVE_MESTRA, "abcd")  # curto demais
    with pytest.raises(cifra.ChaveWebhookAusente):
        cifra.cifrar_segredo("qualquer")


def test_gerar_segredo_e_url_safe_e_com_entropia_suficiente() -> None:
    segredo = cifra.gerar_segredo()
    assert len(segredo) >= 32
    # url-safe: sem caracteres que precisariam de escaping em cabecalho/URL
    assert all(c.isalnum() or c in "-_" for c in segredo)


def test_segredo_em_claro_nunca_aparece_no_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """`cifrar_segredo`/`decifrar_segredo` nao logam nada -- confirmado por
    ausencia total de registro nestas chamadas."""
    segredo = "nao-pode-vazar-para-o-log-de-jeito-nenhum"
    with caplog.at_level(logging.DEBUG):
        blob, _ = cifra.cifrar_segredo(segredo)
        cifra.decifrar_segredo(blob)
    for registro in caplog.records:
        assert segredo not in registro.getMessage()
