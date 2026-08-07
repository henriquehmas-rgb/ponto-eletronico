"""Testes do andaime da Fase 0.

Nao testam regra de negocio -- isso e trabalho de cada fase, em `tests/fXX/`.
Testam o que o ANDAIME promete e que vale para sempre, fase apos fase: a
aplicacao sobe, o inventario de rotas e identico ao contrato, o sinal de vida
funciona sem banco, todo caminho de falha sai em `application/problem+json`
com codigo do catalogo, e nenhuma operacao do contrato responde com um erro
nao tratado (500) -- ela responde ou com o stub `501` de andaime, ou com a
implementacao real da fase dona.

RFC-005: as asserções deste arquivo tinham a contagem de stubs (214) e uma
lista de caminhos gravada em pedra, presumindo que NENHUMA fase teria
implementado nada ainda. Isso quebra na primeira rota real que qualquer fase
entrega -- o que já aconteceu com F1 e F2 na Onda 1, e vai continuar
acontecendo a cada fase até a F15. Por isso os testes abaixo NUNCA presumem
"esta rota especifica ainda e stub": eles perguntam a app.openapi() e a
resposta de verdade, em tempo de execucao, se e stub ou implementacao, e
verificam a invariante que continua valendo nos dois casos. Nenhuma fase
futura precisa editar este arquivo so porque implementou uma rota.
"""

from __future__ import annotations

import pathlib
import uuid

import pytest
import yaml
from fastapi.testclient import TestClient

from app.core.catalogo_erros import CATALOGO
from app.main import app

CONTRATO = pathlib.Path(__file__).resolve().parents[3] / "packages" / "contracts" / "openapi.yaml"
MEDIA_TYPE = "application/problem+json"
METODOS = ("get", "post", "put", "patch", "delete")
ISENTOS = {"/health", "/ready", "/docs", "/redoc", "/openapi.json"}


@pytest.fixture(scope="module")
def cliente() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


def _e_stub(resposta) -> bool:  # type: ignore[no-untyped-def]
    """Formato exato do stub de andaime: 501 + codigo PONTO-INT-005."""
    if resposta.status_code != 501:
        return False
    corpo = resposta.json()
    return corpo.get("codigo") == "PONTO-INT-005"


def _caminhos_get_sem_parametro() -> list[str]:
    """Caminhos GET do contrato, fora dos isentos, sem `{parametro}` na URL.

    Chamaveis diretamente sem massa de dados: nao precisam de um UUID valido
    de path para responder (nem como stub, nem implementados).
    """
    esquema = app.openapi()
    return sorted(
        caminho
        for caminho, item in esquema["paths"].items()
        if caminho not in ISENTOS and "get" in item and "{" not in caminho
    )


def _caminhos_get_com_um_parametro() -> list[str]:
    """Caminhos GET do contrato com exatamente um `{parametro}` na URL."""
    esquema = app.openapi()
    return sorted(
        caminho
        for caminho, item in esquema["paths"].items()
        if caminho not in ISENTOS and "get" in item and caminho.count("{") == 1
    )


# ---------------------------------------------------------------------------
# Inventario
# ---------------------------------------------------------------------------
def test_inventario_de_rotas_bate_com_o_contrato() -> None:
    """Toda operacao do contrato existe na aplicacao, e nada alem dela."""

    def inventario(esquema: dict[str, object]) -> set[tuple[str, str]]:
        caminhos = esquema["paths"]
        assert isinstance(caminhos, dict)
        return {
            (m.upper(), c)
            for c, item in caminhos.items()
            if c not in ISENTOS
            for m in item
            if m in METODOS
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
# Contrato de erro do stub de andaime
# ---------------------------------------------------------------------------
def test_stub_responde_501_com_codigo_do_catalogo(cliente: TestClient) -> None:
    """O formato do stub de andaime, onde quer que ele ainda exista.

    Nao fixa qual operacao e stub -- pergunta ao contrato, em tempo de
    execucao, e usa a PRIMEIRA que encontrar. Continua encontrando alguma ate
    a ultima fase implementar a ultima rota (F15); antes disso, falhar aqui
    por "nenhum stub restante" e uma noticia boa, nao um defeito deste teste.
    """
    candidatos = _caminhos_get_sem_parametro()
    stubs = [(c, cliente.get(c)) for c in candidatos]
    stubs = [(c, r) for c, r in stubs if _e_stub(r)]
    assert stubs, "nenhum caminho GET sem parametro ainda responde como stub de andaime"

    caminho, resposta = stubs[0]
    assert resposta.headers["content-type"].startswith(MEDIA_TYPE)
    corpo = resposta.json()
    assert corpo["codigo"] == "PONTO-INT-005"
    assert corpo["status"] == 501
    assert corpo["type"].endswith("PONTO-INT-005")
    # O detalhe diz qual fase implementa: e o que o integrador precisa saber.
    assert corpo["detail"], caminho
    assert corpo["requestId"].startswith("req_")


def test_nenhuma_operacao_quebra_sem_tratamento(cliente: TestClient) -> None:
    """Toda operacao GET sem parametro responde -- nunca 500 sem tratamento.

    A Fase 0 garantia isto testando "tudo e 501". Isso deixa de ser verdade
    fase a fase, de proposito -- o que nao pode deixar de ser verdade e que
    nenhuma operacao vaza uma excecao nao tratada. Onde ainda for stub, o
    formato e exatamente o de `_e_stub`; onde ja for implementacao real, so
    exigimos que a resposta seja bem formada (nunca 500) -- o contrato
    especifico de cada fase e testado em `tests/fXX/`, nao aqui.
    """
    caminhos = _caminhos_get_sem_parametro()
    assert len(caminhos) > 0

    falhas_500 = []
    stubs = 0
    implementados = 0
    for caminho in caminhos:
        resposta = cliente.get(caminho)
        if resposta.status_code == 500:
            falhas_500.append(caminho)
            continue
        if _e_stub(resposta):
            stubs += 1
        else:
            implementados += 1
    assert not falhas_500, f"operacoes com erro nao tratado (500): {falhas_500}"
    # Registro informativo (nao falha o teste): quanto do contrato ja saiu do
    # andaime. Util para acompanhar o avanco das fases sem editar nada aqui.
    print(f"\n[andaime] {stubs} ainda em stub, {implementados} ja implementados.")


def test_rota_inexistente_devolve_problema(cliente: TestClient) -> None:
    resposta = cliente.get("/v1/nao-existe")
    assert resposta.status_code == 404
    assert resposta.headers["content-type"].startswith(MEDIA_TYPE)
    assert resposta.json()["codigo"] == "PONTO-REC-001"


def test_parametro_de_caminho_invalido_devolve_erros_campo(cliente: TestClient) -> None:
    """UUID malformado no path nunca produz 500, stub ou nao -- e prova o codigo
    quando a validacao chega a rodar.

    RFC-008: o FastAPI resolve toda a arvore de dependencias (`Depends()`) de
    uma rota antes de validar/converter os parametros de path do proprio
    endpoint. Numa rota real (nao mais stub), se `SessaoDb` (sem tenant
    resolvido) ou `exigir_permissao` (sem autenticacao) levantam primeiro, a
    requisicao aborta ali -- o codigo nunca chega a ser `PONTO-VAL-005`,
    mesmo com o path malformado. Isso e estrutural do framework (confirmado
    batendo em toda rota real de F1+F2 sem nenhum cabecalho: nenhuma devolveu
    `PONTO-VAL-005`, todas devolveram `PONTO-VAL-011` ou `PONTO-AUTH-002`,
    dependendo de qual dependencia dispara primeiro) e o orquestrador decidiu
    aceitar essa precedencia em vez de impor uma convencao nova em todo router
    com parametro de path -- ver `docs/rfc/RFC-008-precedencia-erro-contexto-
    vs-formato-de-caminho.md`.
    Um cliente autenticado, com tenant resolvido, que erra o formato de um ID
    continua recebendo `PONTO-VAL-005`: isso e responsabilidade dos testes de
    cada fase (com fixture de autenticacao real), nao deste arquivo, que de
    proposito nao assume nenhum fixture de tenant/autenticacao.
    """
    candidatos = _caminhos_get_com_um_parametro()
    assert candidatos, "nenhum caminho GET com parametro de path encontrado no contrato"

    verificados = 0
    formato_venceu = 0
    for caminho in candidatos[:5]:
        alvo = caminho.split("{", 1)[0].rstrip("/") + "/nao-e-uuid"
        resposta = cliente.get(alvo)
        if resposta.status_code == 404:
            # Caminho com mais segmentos depois do parametro (ex.: sub-recurso);
            # a substituicao ingenua nao produziu uma rota valida. Pula.
            continue
        assert resposta.status_code in (400, 401, 403), caminho
        assert resposta.headers["content-type"].startswith(MEDIA_TYPE), caminho
        corpo = resposta.json()
        assert corpo["codigo"] in CATALOGO, caminho
        if corpo["codigo"] == "PONTO-VAL-005":
            assert corpo["errosCampo"], caminho
            formato_venceu += 1
        verificados += 1
    assert verificados > 0, "nenhum dos candidatos produziu uma rota valida para testar"
    # Registro informativo (nao falha o teste): quantos candidatos ainda sao
    # stub ou nao dependem de tenant/autenticacao, e por isso chegam a expor
    # PONTO-VAL-005 mesmo sem contexto de requisicao.
    print(f"\n[andaime] {formato_venceu}/{verificados} candidatos expuseram PONTO-VAL-005.")


def test_cabecalho_obrigatorio_ausente(cliente: TestClient) -> None:
    """POST sem `Idempotency-Key` falha antes de chegar ao handler.

    `PONTO-IDEM-001`, nao `PONTO-VAL-011`: `IdempotenciaRetrofitMiddleware`
    (F13, `app/comum/idempotencia_middleware.py`) recusa pela ausencia do
    cabecalho ANTES de resolver tenant/sessao -- so cai no `PONTO-VAL-011`
    de `obter_sessao` quando o `Idempotency-Key` esta presente mas o tenant
    nao resolve (ver comentario do proprio middleware). Achado real: a
    asercao original nao acompanhou a mudanca de precedencia quando o
    middleware entrou (2026-08-07)."""
    resposta = cliente.post("/v1/empresas", json={})
    assert resposta.status_code == 400
    assert resposta.json()["codigo"] == "PONTO-IDEM-001"


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
    caminho = _caminhos_get_sem_parametro()[0]
    resposta = cliente.get(caminho, headers={"X-Request-Id": enviado})
    assert resposta.headers["X-Request-Id"] == enviado
    # O corpo so carrega requestId no formato problem+json (erro). Numa
    # resposta de sucesso (200) o cabecalho ja e a prova suficiente.
    if resposta.headers["content-type"].startswith(MEDIA_TYPE):
        assert resposta.json()["requestId"] == enviado


def test_tenant_por_cabecalho_nao_quebra_o_roteamento(cliente: TestClient) -> None:
    """Enviar `X-Tenant` nunca produz erro nao tratado (500), stub ou nao.

    Na Fase 0 o `TenantMiddleware` era um stub que nao validava nada, entao
    qualquer slug batia num caminho ainda-stub e devolvia 501 -- por isso a
    primeira versao deste teste exigia esse formato exato. A partir da F1,
    o middleware passou a RESOLVER o tenant de verdade: um slug que nao existe
    no banco (como "seeg" contra um banco de teste vazio) e corretamente
    rejeitado ANTES de chegar no stub, com o codigo de tenant invalido -- isso
    e o comportamento certo, nao uma quebra. A invariante que continua valendo
    sempre, stub ou implementado, tenant valido ou invalido, e: nunca 500.
    """
    candidatos = _caminhos_get_sem_parametro()
    falhas = [
        c for c in candidatos if cliente.get(c, headers={"X-Tenant": "seeg"}).status_code == 500
    ]
    assert not falhas, f"operacoes que quebram com X-Tenant desconhecido: {falhas}"


def test_tempo_de_resposta_e_publicado(cliente: TestClient) -> None:
    resposta = cliente.get("/health")
    assert float(resposta.headers["X-Tempo-Resposta-Ms"]) >= 0


def test_uuid_aleatorio_nao_derruba_operacao_com_parametro(cliente: TestClient) -> None:
    """Sanidade extra (RFC-005): um UUID sintaticamente valido, mas de um
    recurso que nao existe, nunca pode produzir 500 -- stub ou implementado.
    """
    aleatorio = str(uuid.uuid4())
    falhas = []
    for caminho in _caminhos_get_com_um_parametro():
        alvo = caminho.split("{", 1)[0].rstrip("/") + "/" + aleatorio
        resposta = cliente.get(alvo)
        if resposta.status_code == 500:
            falhas.append(caminho)
    assert not falhas, f"operacoes que quebram com UUID inexistente: {falhas}"
