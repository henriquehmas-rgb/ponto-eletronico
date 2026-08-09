"""Testes do andaime do facial-svc (Fase 0).

Nao testam regra de negocio -- nao existe nenhuma, e nao ha motor carregado.
Testam o que a Fase 0 promete e o que `infra/docker-compose.yml` exige para o
servico ficar `healthy` (do que depende o `depends_on` da `api`):

* a aplicacao sobe e monta as cinco operacoes;
* `/health` responde 200 **sem** conferir os pesos do modelo — se conferisse,
  um volume vazio prenderia a stack inteira no `depends_on`;
* `/ready` reprova com `PONTO-INT-003` quando nao ha peso `.onnx`;
* as tres operacoes biometricas recusam corpo invalido em
  `application/problem+json` (eram 501 `PONTO-INT-005` antes de o motor existir;
  o pipeline de verdade e exercitado em `test_motor_facial.py`);
* o recorte de `errors.yaml` copiado em `facial/erros.py` continua identico ao
  catalogo congelado;
* **o limiar de similaridade nao vaza em nenhuma resposta** (ADR-006 e
  `expoe_regra: false` dos `PONTO-SCORE-*`).

O nome do arquivo carrega o sufixo `_facial_svc` de proposito: o CI roda
`pytest -q` a partir da RAIZ do monorepo, onde dois arquivos de teste de mesmo
nome em arvores diferentes colidem na importacao.
"""

from __future__ import annotations

import json
import pathlib

import pytest
import yaml
from fastapi.testclient import TestClient

from facial.config import obter_configuracao
from facial.erros import CATALOGO, MEDIA_TYPE_PROBLEMA
from facial.main import app

CONTRATO_ERROS = (
    pathlib.Path(__file__).resolve().parents[3] / "packages" / "contracts" / "errors.yaml"
)

STUBS: tuple[str, ...] = ("/enroll", "/verificar", "/liveness")


@pytest.fixture(scope="module")
def cliente() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Saude
# ---------------------------------------------------------------------------
def test_health_responde_200_mesmo_sem_pesos_do_modelo(cliente: TestClient) -> None:
    """A `api` depende deste healthcheck: volume vazio nao pode prender a stack."""
    resposta = cliente.get("/health")
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["status"] == "ok"
    assert corpo["servico"] == "ponto-facial-svc"
    assert corpo["modeloVersao"]


def test_ready_reprova_quando_nao_ha_peso_onnx(cliente: TestClient) -> None:
    """Sem modelo o servico esta vivo e inutil — que e o que readiness descreve."""
    config = obter_configuracao()
    resposta = cliente.get("/ready")
    if config.modelos_presentes:
        assert resposta.status_code == 200
        return
    assert resposta.status_code == 503
    assert resposta.headers["content-type"].startswith(MEDIA_TYPE_PROBLEMA)
    corpo = resposta.json()
    assert corpo["codigo"] == "PONTO-INT-003"
    assert corpo["tentarNovamenteEm"] == 15


# ---------------------------------------------------------------------------
# Stubs biometricos
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("caminho", STUBS)
def test_corpo_vazio_responde_400_com_codigo_do_catalogo(cliente: TestClient, caminho: str) -> None:
    """As tres operacoes existem e recusam corpo vazio em problem+json.

    Ate o motor existir, estas tres respondiam `501 PONTO-INT-005` a qualquer
    corpo. Agora que ha contrato Pydantic de verdade (`facial/esquemas.py`), o
    corpo vazio nao chega ao motor: vira `400 PONTO-VAL-001` com `errosCampo`,
    pelo tratador de `RequestValidationError` de `facial/erros.py`. O que o teste
    guarda continua sendo o mesmo: **nenhum caminho de falha devolve
    `application/json` cru nem stack trace** num servico que recebe rosto.
    """
    resposta = cliente.post(caminho, json={})
    assert resposta.status_code == 400, caminho
    assert resposta.headers["content-type"].startswith(MEDIA_TYPE_PROBLEMA), caminho
    corpo = resposta.json()
    assert corpo["codigo"] == "PONTO-VAL-001"
    assert corpo["status"] == 400
    assert corpo["instance"] == caminho
    assert corpo["errosCampo"], "o problema deve apontar quais campos faltaram"


def test_inventario_de_operacoes_esta_completo() -> None:
    """Duas de saude mais as tres biometricas, e nada alem disso.

    O inventario e lido do esquema OpenAPI gerado, e nao de `app.routes`: a
    partir do FastAPI 0.13x um roteador incluido aparece em `app.routes` como um
    unico objeto agregador.
    """
    caminhos = app.openapi()["paths"]
    operacoes = {
        (metodo.upper(), caminho)
        for caminho, item in caminhos.items()
        for metodo in item
        if metodo in ("get", "post", "put", "patch", "delete")
    }
    assert operacoes == {
        ("GET", "/health"),
        ("GET", "/ready"),
        ("POST", "/enroll"),
        ("POST", "/verificar"),
        ("POST", "/liveness"),
    }


def test_caminho_inexistente_sai_em_problem_json(cliente: TestClient) -> None:
    """Nenhum caminho de falha devolve `application/json` cru."""
    resposta = cliente.get("/nao-existe")
    assert resposta.status_code == 404
    assert resposta.headers["content-type"].startswith(MEDIA_TYPE_PROBLEMA)
    assert resposta.json()["codigo"] == "PONTO-REC-001"


# ---------------------------------------------------------------------------
# LGPD e ADR-006: o limiar nao sai daqui
# ---------------------------------------------------------------------------
def test_limiar_de_similaridade_nao_aparece_em_nenhuma_resposta(cliente: TestClient) -> None:
    """`PONTO-SCORE-003` tem `expoe_regra: false`: o placar nao volta ao cliente.

    O limiar padrao e 0.42. O teste procura o valor em qualquer forma dentro do
    corpo das rotas que respondem sem erro, incluindo `/ready`, que e o tipo de
    endpoint que acaba exposto em painel por descuido.
    """
    config = obter_configuracao()
    limiar = str(config.facial_limiar_similaridade)
    for caminho in ("/health", "/ready"):
        corpo = json.dumps(cliente.get(caminho).json(), ensure_ascii=False)
        assert limiar not in corpo, caminho
        assert "limiar" not in corpo.lower(), caminho


def test_recorte_do_catalogo_bate_com_errors_yaml() -> None:
    """O recorte em `facial/erros.py` e copia literal de `errors.yaml`."""
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


def test_todos_os_codigos_de_score_estao_no_recorte_e_nao_expoem_regra() -> None:
    """Os `PONTO-SCORE-*` sao produzidos aqui e nenhum deles pode expor a regra.

    `PONTO-SCORE-004` (camera virtual) e a excecao proposital do catalogo: dizer
    "detectamos camera virtual" nao ensina a burlar nada, e ajuda o usuario
    legitimo a desligar o OBS. Ele fica de fora do recorte de score deste
    servico porque a deteccao acontece no cliente (F8).
    """
    contrato = yaml.safe_load(CONTRATO_ERROS.read_text(encoding="utf-8"))
    do_score = {
        erro["codigo"]: erro
        for erro in contrato["erros"]
        if erro["codigo"].startswith("PONTO-SCORE-")
    }
    assert do_score, "errors.yaml deveria declarar codigos PONTO-SCORE-*"
    for codigo in ("PONTO-SCORE-002", "PONTO-SCORE-003"):
        assert codigo in CATALOGO
        assert CATALOGO[codigo].expoe_regra is False
        assert do_score[codigo]["expoe_regra"] is False
