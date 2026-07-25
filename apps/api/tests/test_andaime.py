"""Testes do andaime da Fase 0.

Nao testam regra de negocio -- nao existe nenhuma. Testam o que a Fase 0
promete: a aplicacao sobe, o inventario de rotas e identico ao contrato, o
sinal de vida funciona sem banco, e todo caminho de falha sai em
`application/problem+json` com codigo do catalogo.
"""

from __future__ import annotations

import pathlib

import pytest
import yaml
from fastapi.testclient import TestClient

from app.core.catalogo_erros import CATALOGO
from app.main import app

CONTRATO = pathlib.Path(__file__).resolve().parents[3] / "packages" / "contracts" / "openapi.yaml"
MEDIA_TYPE = "application/problem+json"


@pytest.fixture(scope="module")
def cliente() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Inventario
# ---------------------------------------------------------------------------
def test_inventario_de_rotas_bate_com_o_contrato() -> None:
    """Toda operacao do contrato existe na aplicacao, e nada alem dela."""
    metodos = ("get", "post", "put", "patch", "delete")
    isentos = {"/health", "/ready", "/docs", "/redoc", "/openapi.json"}

    def inventario(esquema: dict[str, object]) -> set[tuple[str, str]]:
        caminhos = esquema["paths"]
        assert isinstance(caminhos, dict)
        return {
            (m.upper(), c)
            for c, item in caminhos.items()
            if c not in isentos
            for m in item
            if m in metodos
        }

    contrato = yaml.safe_load(CONTRATO.read_text(encoding="utf-8"))
    assert inventario(app.openapi()) == inventario(contrato)


# ---------------------------------------------------------------------------
# Saude
# ---------------------------------------------------------------------------
def test_health_responde_sem_dependencia(cliente: TestClient) -> None:
    """Liveness nao pode depender de banco: e o alvo do healthcheck do Docker."""
    resposta = cliente.get("/health")
    assert resposta.status_code == 200
    assert resposta.json()["status"] == "ok"


def test_ready_relata_dependencias(cliente: TestClient) -> None:
    """Readiness responde 200 com o mapa de dependencias ou 503 PONTO-INT-003."""
    resposta = cliente.get("/ready")
    assert resposta.status_code in (200, 503)
    if resposta.status_code == 503:
        assert resposta.headers["content-type"].startswith(MEDIA_TYPE)
        assert resposta.json()["codigo"] == "PONTO-INT-003"
        assert resposta.headers["Retry-After"] == "5"
    else:
        assert set(resposta.json()["dependencias"]) == {"banco", "redis"}


# ---------------------------------------------------------------------------
# Contrato de erro
# ---------------------------------------------------------------------------
def test_stub_responde_501_com_codigo_do_catalogo(cliente: TestClient) -> None:
    resposta = cliente.get("/v1/colaboradores")
    assert resposta.status_code == 501
    assert resposta.headers["content-type"].startswith(MEDIA_TYPE)
    corpo = resposta.json()
    assert corpo["codigo"] == "PONTO-INT-005"
    assert corpo["status"] == 501
    assert corpo["type"].endswith("PONTO-INT-005")
    # O detalhe diz qual fase implementa: e o que o integrador precisa saber.
    assert "listarColaboradores" in corpo["detail"]
    assert corpo["requestId"].startswith("req_")


def test_todas_as_operacoes_do_contrato_respondem_501_ou_saude(
    cliente: TestClient,
) -> None:
    """Nenhuma rota de dominio finge estar pronta na Fase 0."""
    esquema = app.openapi()
    implementadas = {"obterSaude"}
    stubs = [
        (m, c)
        for c, item in esquema["paths"].items()
        for m, op in item.items()
        if m in ("get", "post", "put", "patch", "delete")
        and op.get("operationId") not in implementadas
    ]
    assert len(stubs) == 214

    # Amostra representativa: uma operacao GET sem parametro de caminho por tag.
    amostra = [
        "/v1/marcacoes",
        "/v1/apuracoes?de=2026-07-01&ate=2026-07-31",
        "/v1/banco-horas/contas",
        "/v1/fiscal/afd",
        "/v1/auditoria",
        "/v1/jornadas",
        "/v1/webhooks",
    ]
    for caminho in amostra:
        resposta = cliente.get(caminho)
        assert resposta.status_code == 501, caminho
        assert resposta.json()["codigo"] == "PONTO-INT-005", caminho


def test_rota_inexistente_devolve_problema(cliente: TestClient) -> None:
    resposta = cliente.get("/v1/nao-existe")
    assert resposta.status_code == 404
    assert resposta.headers["content-type"].startswith(MEDIA_TYPE)
    assert resposta.json()["codigo"] == "PONTO-REC-001"


def test_parametro_invalido_devolve_erros_campo(cliente: TestClient) -> None:
    resposta = cliente.get("/v1/colaboradores/nao-e-uuid")
    assert resposta.status_code == 400
    corpo = resposta.json()
    assert corpo["codigo"] == "PONTO-VAL-005"
    assert corpo["errosCampo"][0]["campo"] == "colaboradorId"


def test_cabecalho_obrigatorio_ausente(cliente: TestClient) -> None:
    """POST sem `Idempotency-Key` falha antes de chegar ao stub."""
    resposta = cliente.post("/v1/empresas", json={})
    assert resposta.status_code == 400
    assert resposta.json()["codigo"] == "PONTO-VAL-011"


def test_todo_codigo_usado_existe_no_catalogo() -> None:
    """O tratador nunca inventa codigo fora de `errors.yaml`."""
    from app.core import erros

    usados = {*erros.CODIGO_POR_STATUS.values(), erros.CODIGO_NAO_IMPLEMENTADO}
    assert usados <= set(CATALOGO)


# ---------------------------------------------------------------------------
# Contexto de requisicao
# ---------------------------------------------------------------------------
def test_request_id_e_gerado_e_devolvido(cliente: TestClient) -> None:
    resposta = cliente.get("/health")
    assert resposta.headers["X-Request-Id"].startswith("req_")


def test_request_id_do_cliente_e_preservado(cliente: TestClient) -> None:
    enviado = "req_TESTE_DO_CLIENTE"
    resposta = cliente.get("/v1/colaboradores", headers={"X-Request-Id": enviado})
    assert resposta.headers["X-Request-Id"] == enviado
    assert resposta.json()["requestId"] == enviado


def test_tenant_resolvido_por_cabecalho(cliente: TestClient) -> None:
    resposta = cliente.get("/v1/colaboradores", headers={"X-Tenant": "seeg"})
    assert resposta.status_code == 501


def test_tempo_de_resposta_e_publicado(cliente: TestClient) -> None:
    resposta = cliente.get("/health")
    assert float(resposta.headers["X-Tempo-Resposta-Ms"]) >= 0
