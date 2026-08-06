"""A2 -- `app.comum.ip_confiavel.ip_confiavel_do_cliente` (mecanismo de IP
confiável, PCF F14 §5 A2).

Testes unitários puros (constroem `Request` do Starlette diretamente, sem
banco/Redis) -- a lógica é pura função de `(peer, cabeçalhos, allowlist)`.
"""

from __future__ import annotations

import pytest
from starlette.requests import Request

from app.comum.ip_confiavel import ip_confiavel_do_cliente
from app.core.config import obter_configuracao


def _requisicao(*, peer: str | None, cabecalhos: dict[str, str] | None = None) -> Request:
    escopo = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [
            (k.lower().encode("latin-1"), v.encode("latin-1"))
            for k, v in (cabecalhos or {}).items()
        ],
        "client": (peer, 12345) if peer is not None else None,
    }
    return Request(escopo)


@pytest.fixture(autouse=True)
def _limpar_configuracao(monkeypatch: pytest.MonkeyPatch):
    yield
    monkeypatch.delenv("PROXIES_CONFIAVEIS", raising=False)
    obter_configuracao.cache_clear()


def test_sem_allowlist_configurada_ignora_x_forwarded_for(monkeypatch: pytest.MonkeyPatch) -> None:
    """Padrão de `dev`/`ci`: `PROXIES_CONFIAVEIS` vazio -- o cabeçalho nunca
    é confiado, mesmo vindo de qualquer peer."""
    monkeypatch.delenv("PROXIES_CONFIAVEIS", raising=False)
    obter_configuracao.cache_clear()

    requisicao = _requisicao(peer="10.0.0.5", cabecalhos={"X-Forwarded-For": "203.0.113.9"})
    assert ip_confiavel_do_cliente(requisicao) == "10.0.0.5"


def test_peer_fora_da_allowlist_ignora_x_forwarded_for(monkeypatch: pytest.MonkeyPatch) -> None:
    """Allowlist configurada, mas a conexão não veio de um proxy conhecido
    (tentativa de spoofing direto, pulando o Traefik): cabeçalho ignorado."""
    monkeypatch.setenv("PROXIES_CONFIAVEIS", "10.0.0.9")
    obter_configuracao.cache_clear()

    requisicao = _requisicao(peer="203.0.113.66", cabecalhos={"X-Forwarded-For": "1.2.3.4"})
    assert ip_confiavel_do_cliente(requisicao) == "203.0.113.66"


def test_peer_confiavel_usa_primeiro_ip_do_x_forwarded_for(monkeypatch: pytest.MonkeyPatch) -> None:
    """Peer é o proxy reverso configurado: o PRIMEIRO IP da cadeia
    `X-Forwarded-For` (o mais próximo do cliente original) é usado."""
    monkeypatch.setenv("PROXIES_CONFIAVEIS", "10.0.0.9")
    obter_configuracao.cache_clear()

    requisicao = _requisicao(
        peer="10.0.0.9", cabecalhos={"X-Forwarded-For": "203.0.113.9, 10.0.0.9"}
    )
    assert ip_confiavel_do_cliente(requisicao) == "203.0.113.9"


def test_peer_confiavel_sem_xff_usa_x_real_ip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PROXIES_CONFIAVEIS", "10.0.0.9")
    obter_configuracao.cache_clear()

    requisicao = _requisicao(peer="10.0.0.9", cabecalhos={"X-Real-Ip": "203.0.113.44"})
    assert ip_confiavel_do_cliente(requisicao) == "203.0.113.44"


def test_peer_confiavel_com_xff_invalido_cai_para_x_real_ip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PROXIES_CONFIAVEIS", "10.0.0.9")
    obter_configuracao.cache_clear()

    requisicao = _requisicao(
        peer="10.0.0.9",
        cabecalhos={"X-Forwarded-For": "nao-e-um-ip", "X-Real-Ip": "203.0.113.44"},
    )
    assert ip_confiavel_do_cliente(requisicao) == "203.0.113.44"


def test_peer_confiavel_sem_nenhum_cabecalho_usa_o_proprio_peer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PROXIES_CONFIAVEIS", "10.0.0.9")
    obter_configuracao.cache_clear()

    requisicao = _requisicao(peer="10.0.0.9")
    assert ip_confiavel_do_cliente(requisicao) == "10.0.0.9"


def test_sem_client_devolve_none() -> None:
    requisicao = _requisicao(peer=None)
    assert ip_confiavel_do_cliente(requisicao) is None


def test_host_de_teste_nao_e_ip_valido_devolve_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """`starlette.testclient.TestClient` usa `"testclient"` como peer, que
    não é IP válido -- mesma proteção que `app/routers/auth.py` já tinha
    antes deste retrofit (coluna `INET` do Postgres rejeitaria com
    `DataError` cru)."""
    monkeypatch.delenv("PROXIES_CONFIAVEIS", raising=False)
    obter_configuracao.cache_clear()

    requisicao = _requisicao(peer="testclient")
    assert ip_confiavel_do_cliente(requisicao) is None
