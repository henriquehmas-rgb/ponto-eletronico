"""Testes do andaime do device-gw (Fase 0).

Nao testam regra de negocio -- nao existe nenhuma. Testam o que a Fase 0 promete
e o que `infra/docker-compose.yml` exige para o servico `device-gw` ficar
`healthy`:

* a aplicacao sobe e monta as rotas dos tres modos de comunicacao;
* `/health` responde 200 sem tocar em nenhuma dependencia (e o alvo do
  `healthcheck` do container e do Traefik);
* todo endpoint de protocolo responde 501 com `PONTO-INT-005` em
  `application/problem+json`;
* o recorte de `errors.yaml` copiado em `gateway/erros.py` continua identico ao
  catalogo congelado — se alguem alterar o contrato, o teste reprova aqui;
* o esqueleto do simulador cobre os tres `*.fcgi` que o aceite da F6 exercita.

O nome do arquivo carrega o sufixo `_device_gw` de proposito: o CI roda
`pytest -q` a partir da RAIZ do monorepo, onde dois arquivos de teste de mesmo
nome em arvores diferentes colidem na importacao.
"""

from __future__ import annotations

import pathlib

import pytest
import yaml
from fastapi.testclient import TestClient

from gateway.erros import CATALOGO, MEDIA_TYPE_PROBLEMA
from gateway.main import app
from gateway.simulador import descrever_simulador, gerar_access_log, resposta_login

CONTRATO_ERROS = (
    pathlib.Path(__file__).resolve().parents[3] / "packages" / "contracts" / "errors.yaml"
)

#: Endpoints de protocolo, no caminho declarado (com parametro). Todos devem
#: responder 501 na Fase 0.
STUBS_DECLARADOS: tuple[tuple[str, str], ...] = (
    ("post", "/new_connection.fcgi"),
    ("post", "/send_response.fcgi"),
    ("post", "/interno/terminais/{numero_serie}/comandos"),
    ("post", "/api/notifications/dao"),
    ("post", "/api/notifications/door"),
    ("post", "/api/notifications/catra"),
    ("post", "/api/notifications/template"),
    ("post", "/api/notifications/secbox"),
    ("post", "/api/notifications/operation_mode"),
    ("get", "/interno/terminais/{numero_serie}/marca-dagua"),
    ("post", "/interno/terminais/{numero_serie}/catch-up"),
)

#: Os mesmos caminhos, resolvidos com um numero de serie concreto, para o
#: cliente HTTP conseguir chamar.
SERIE = "IDF-2026-000417"
STUBS = tuple(
    (metodo, caminho.replace("{numero_serie}", SERIE)) for metodo, caminho in STUBS_DECLARADOS
)


@pytest.fixture(scope="module")
def cliente() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Saude
# ---------------------------------------------------------------------------
def test_health_responde_200_sem_dependencia(cliente: TestClient) -> None:
    """`/health` e liveness: nao pode depender de Redis nem da API."""
    resposta = cliente.get("/health")
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["status"] == "ok"
    assert corpo["servico"] == "ponto-device-gw"


def test_health_nao_e_o_mesmo_endpoint_que_ready(cliente: TestClient) -> None:
    """`/ready` toca dependencia e por isso pode falhar onde `/health` passa.

    Sem Redis e sem API no ambiente de teste, o esperado e 503 `PONTO-INT-003`
    em problem+json — que e exatamente o comportamento desejado do readiness.
    """
    resposta = cliente.get("/ready")
    assert resposta.status_code in (200, 503)
    if resposta.status_code == 503:
        assert resposta.headers["content-type"].startswith(MEDIA_TYPE_PROBLEMA)
        assert resposta.json()["codigo"] == "PONTO-INT-003"


# ---------------------------------------------------------------------------
# Stubs de protocolo
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(("metodo", "caminho"), STUBS)
def test_stub_responde_501_com_codigo_do_catalogo(
    cliente: TestClient, metodo: str, caminho: str
) -> None:
    """Toda operacao de protocolo existe, responde 501 e usa problem+json."""
    resposta = (
        cliente.post(caminho, json={}) if metodo == "post" else cliente.request(metodo, caminho)
    )
    assert resposta.status_code == 501, caminho
    assert resposta.headers["content-type"].startswith(MEDIA_TYPE_PROBLEMA), caminho
    corpo = resposta.json()
    assert corpo["codigo"] == "PONTO-INT-005"
    assert corpo["status"] == 501
    assert corpo["instance"] == caminho
    # `PONTO-INT-005` tem `expoe_regra: true`: o detalhe diz qual fase implementa.
    assert "F6" in corpo["detail"]


def test_os_tres_modos_de_comunicacao_estao_montados() -> None:
    """Push, Monitor e catch-up: nenhum roteador pode ter ficado de fora.

    O inventario e lido do esquema OpenAPI gerado, e nao de `app.routes`: a
    partir do FastAPI 0.13x um roteador incluido aparece em `app.routes` como um
    unico objeto agregador, e contar entradas dessa lista nao diz quantas
    operacoes existem.
    """
    caminhos = set(app.openapi()["paths"])
    assert "/health" in caminhos
    assert "/ready" in caminhos
    assert "/new_connection.fcgi" in caminhos
    assert "/api/notifications/dao" in caminhos
    assert "/interno/terminais/{numero_serie}/catch-up" in caminhos


def test_inventario_de_operacoes_esta_completo() -> None:
    """Duas operacoes funcionais (saude) mais os stubs de protocolo declarados."""
    caminhos = app.openapi()["paths"]
    operacoes = {
        (metodo.upper(), caminho)
        for caminho, item in caminhos.items()
        for metodo in item
        if metodo in ("get", "post", "put", "patch", "delete")
    }
    esperadas = {(metodo.upper(), caminho) for metodo, caminho in STUBS_DECLARADOS}
    assert esperadas <= operacoes
    assert ("GET", "/health") in operacoes
    assert ("GET", "/ready") in operacoes
    assert len(operacoes) == len(esperadas) + 2


def test_caminho_inexistente_sai_em_problem_json(cliente: TestClient) -> None:
    """Nenhum caminho de falha devolve `application/json` cru."""
    resposta = cliente.get("/nao-existe")
    assert resposta.status_code == 404
    assert resposta.headers["content-type"].startswith(MEDIA_TYPE_PROBLEMA)
    assert resposta.json()["codigo"] == "PONTO-REC-001"


# ---------------------------------------------------------------------------
# Fidelidade ao catalogo de erros congelado
# ---------------------------------------------------------------------------
def test_recorte_do_catalogo_bate_com_errors_yaml() -> None:
    """O recorte em `gateway/erros.py` e copia literal de `errors.yaml`."""
    contrato = yaml.safe_load(CONTRATO_ERROS.read_text(encoding="utf-8"))
    por_codigo = {erro["codigo"]: erro for erro in contrato["erros"]}
    for codigo, linha in CATALOGO.items():
        oficial = por_codigo.get(codigo)
        assert oficial is not None, f"{codigo} nao existe em errors.yaml"
        assert linha.http_status == oficial["http_status"], codigo
        assert linha.titulo == oficial["titulo"], codigo
        assert linha.categoria == oficial["categoria"], codigo
        assert linha.retentavel == oficial["retentavel"], codigo
        assert linha.expoe_regra == oficial["expoe_regra"], codigo


def test_todos_os_codigos_de_terminal_estao_no_recorte() -> None:
    """O device-gw e quem produz `PONTO-TERM-*`: nenhum pode faltar aqui."""
    contrato = yaml.safe_load(CONTRATO_ERROS.read_text(encoding="utf-8"))
    do_terminal = {
        erro["codigo"] for erro in contrato["erros"] if erro["codigo"].startswith("PONTO-TERM-")
    }
    assert do_terminal, "errors.yaml deveria declarar codigos PONTO-TERM-*"
    assert do_terminal <= set(CATALOGO)


# ---------------------------------------------------------------------------
# Simulador
# ---------------------------------------------------------------------------
def test_simulador_cobre_os_tres_fcgi_do_aceite_da_f6() -> None:
    """Sem estes tres, o simulador da F6 nao consegue nem abrir sessao."""
    descricao = descrever_simulador()
    assert descricao["implementado"] is False
    assert descricao["fase"] == "F6"
    assert set(descricao["endpointsCobertos"]) == {
        "login.fcgi",
        "load_objects.fcgi",
        "execute_actions.fcgi",
    }
    assert "access_logs" in descricao["tabelas"]


def test_access_log_gerado_tem_os_campos_da_marca_dagua() -> None:
    """`id` e `time` sao a marca d'agua e a evidencia de relogio: nao podem sumir."""
    registro = gerar_access_log(41208, user_id=314)
    assert registro["id"] == 41208
    assert isinstance(registro["time"], int)
    assert registro["user_id"] == 314


def test_resposta_de_login_tem_a_chave_session() -> None:
    """Toda chamada `*.fcgi` seguinte depende deste token na query string."""
    assert "session" in resposta_login()
