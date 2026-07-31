"""Prova de fumaça de `cliente`/`construir_sujeito`/`sobrescrever_sujeito`
(T1): a aplicação real sobe contra o banco de teste, resolve o tenant pelo
cabeçalho `X-Tenant` e aceita o sujeito sobrescrito.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.f11.conftest import ContextoF11, cabecalhos, construir_sujeito, sobrescrever_sujeito


def test_cliente_sobe_e_resolve_tenant_pelo_cabecalho(
    cliente: TestClient, contexto_f11: ContextoF11
) -> None:
    sobrescrever_sujeito(
        cliente,
        construir_sujeito(
            usuario_id=contexto_f11.usuario_rh_id,
            tenant_id=contexto_f11.tenant_id,
            permissoes=frozenset({"relatorios.ler"}),
        ),
    )
    resposta = cliente.get("/v1/relatorios", headers=cabecalhos(contexto_f11.tenant_slug))
    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()
    assert len(corpo["dados"]) == 24


def test_cliente_sem_sujeito_autenticado_responde_401(
    cliente: TestClient, contexto_f11: ContextoF11
) -> None:
    resposta = cliente.get("/v1/relatorios", headers=cabecalhos(contexto_f11.tenant_slug))
    assert resposta.status_code == 401, resposta.text
    assert resposta.json()["codigo"] == "PONTO-AUTH-002"
