"""Testes do motor facial de verdade: deteccao, embedding, comparacao, liveness.

Diferente de `test_andaime_facial_svc.py`, que guarda o contrato e os codigos de
erro, este arquivo **roda o pipeline inteiro**: decodifica imagem, detecta rosto
com o `det_10g`, extrai embedding de 512 dimensoes com o `w600k_r50`, serializa
o template, compara por cosseno e julga prova de vida. Se o ONNX Runtime nao
estiver instalado ou os pesos nao estiverem disponiveis, a suite e **pulada**,
nunca silenciosamente aprovada.

De onde vem o rosto
-------------------

De `insightface.data.get_image("t1")`: uma foto de grupo que acompanha o proprio
pacote `insightface` (repositorio MIT) e que contem **seis pessoas distintas**.
A escolha resolve tres problemas de uma vez:

* nenhum rosto entra no repositorio da SEEG — a imagem vem da dependencia, em
  tempo de execucao, e nao de um arquivo versionado;
* nao ha duvida de licenca sobre uma foto que ja e distribuida com a biblioteca
  que estamos usando;
* seis identidades reais no mesmo quadro dao o teste que importa de verdade —
  **pessoas diferentes precisam reprovar**, e isso nao se prova com rosto
  sintetico, que nao se parece com ninguem por construcao.

De cada pessoa sao derivadas duas fotos diferentes: recortes com margens
diferentes, escalas diferentes e requantizacao JPEG em qualidades diferentes.
Nao sao duas copias do mesmo arquivo — sao duas imagens distintas do mesmo
rosto, que e exatamente o caso que o reconhecimento precisa acertar (o
colaborador cadastrado no RH em marco e marcando ponto em agosto).

O que se prova aqui
-------------------

* mesma pessoa -> `aprovado: true`, com o indice certo entre seis templates;
* pessoas diferentes -> `aprovado: false`, e `403 PONTO-SCORE-003` quando o
  chamador exige aprovacao;
* imagem sem rosto (chapada e ruido) -> `400 PONTO-VAL-001` tratado, em
  `problem+json`, sem stack trace;
* mais de um rosto no enroll -> recusa;
* limiar e similaridade **nunca** aparecem em nenhuma resposta.
"""

from __future__ import annotations

import base64
import json
from typing import Any

import numpy as np
import pytest
from fastapi.testclient import TestClient

from facial.config import obter_configuracao
from facial.erros import MEDIA_TYPE_PROBLEMA
from facial.main import app
from facial.motor import DIMENSAO_EMBEDDING

cv2 = pytest.importorskip("cv2", reason="opencv-python-headless nao instalado")
pytest.importorskip("onnxruntime", reason="onnxruntime nao instalado")
insightface_data = pytest.importorskip("insightface.data", reason="insightface nao instalado")

TotalPessoas = 6


# ---------------------------------------------------------------------------
# Fixtures: as fotos
# ---------------------------------------------------------------------------
def _para_jpeg_base64(matriz: Any, qualidade: int = 85) -> str:
    ok, buffer = cv2.imencode(".jpg", matriz, [cv2.IMWRITE_JPEG_QUALITY, qualidade])
    assert ok, "falha ao codificar JPEG na fixture"
    return base64.b64encode(buffer.tobytes()).decode("ascii")


def _recorte(
    imagem: Any,
    caixa: Any,
    *,
    margem: float,
    escala: float,
    deslocamento: tuple[int, int] = (0, 0),
) -> Any:
    """Recorta o rosto com margem relativa ao proprio `bbox` e reamostra.

    `deslocamento` move a janela alguns pixels — e o que gera **movimento** entre
    quadros na sequencia de prova de vida sem inventar pixel nenhum: e a mesma
    cena, enquadrada um pouco diferente, que e o que uma mao segurando um celular
    produz.
    """
    altura, largura = imagem.shape[:2]
    x1, y1, x2, y2 = (float(v) for v in caixa[:4])
    mx, my = (x2 - x1) * margem, (y2 - y1) * margem
    dx, dy = deslocamento
    a = max(0, int(x1 - mx) + dx)
    b = max(0, int(y1 - my) + dy)
    c = min(largura, int(x2 + mx) + dx)
    d = min(altura, int(y2 + my) + dy)
    return cv2.resize(imagem[b:d, a:c], None, fx=escala, fy=escala, interpolation=cv2.INTER_CUBIC)


@pytest.fixture(scope="module")
def motor_direto() -> Any:
    """Motor carregado fora do HTTP, so para preparar as fixtures."""
    from facial.motor import motor

    instancia = motor()
    try:
        instancia.carregar()
    except Exception as exc:  # pragma: no cover - ambiente sem pesos
        pytest.skip(f"motor facial indisponivel neste ambiente: {exc}")
    return instancia


@pytest.fixture(scope="module")
def cena(motor_direto: Any) -> Any:
    """A foto de grupo original, ja com os seis rostos localizados."""
    imagem = insightface_data.get_image("t1")
    rostos = motor_direto.detectar(imagem)
    if len(rostos) < TotalPessoas:  # pragma: no cover - troca de pacote de modelos
        pytest.skip(f"esperados {TotalPessoas} rostos em t1, detectados {len(rostos)}")
    # Ordem estavel por posicao horizontal: `detectar` ordena por area, que muda
    # se o detector for trocado, e o teste precisa de indices reproduziveis.
    rostos = sorted(rostos[:TotalPessoas], key=lambda r: r.bbox[0])
    return imagem, rostos


@pytest.fixture(scope="module")
def fotos_cadastro(cena: Any) -> list[str]:
    """Uma foto por pessoa, no enquadramento apertado do cadastro."""
    imagem, rostos = cena
    return [
        _para_jpeg_base64(_recorte(imagem, r.bbox, margem=0.25, escala=2.0), qualidade=90)
        for r in rostos
    ]


@pytest.fixture(scope="module")
def fotos_marcacao(cena: Any) -> list[str]:
    """Outra foto por pessoa: margem maior, escala menor, JPEG mais agressivo.

    E o par que interessa: mesma pessoa, imagem diferente. Se o teste usasse o
    mesmo arquivo dos dois lados, ele provaria apenas que a funcao e
    deterministica.
    """
    imagem, rostos = cena
    fotos = []
    for r in rostos:
        recorte = _recorte(imagem, r.bbox, margem=0.5, escala=1.6, deslocamento=(3, -2))
        # Leve variacao de exposicao, como a de uma camera com outro ganho.
        recorte = cv2.convertScaleAbs(recorte, alpha=1.08, beta=-6)
        fotos.append(_para_jpeg_base64(recorte, qualidade=70))
    return fotos


@pytest.fixture(scope="module")
def cliente() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(scope="module")
def templates(cliente: TestClient, fotos_cadastro: list[str]) -> list[str]:
    """Enrolla as seis pessoas e devolve os seis templates, na mesma ordem."""
    saida = []
    for foto in fotos_cadastro:
        resposta = cliente.post("/enroll", json={"imagemBase64": foto, "mimeType": "image/jpeg"})
        assert resposta.status_code == 200, resposta.text
        saida.append(resposta.json()["template"])
    return saida


def _versao() -> str:
    return obter_configuracao().facial_model_versao


# ---------------------------------------------------------------------------
# enroll
# ---------------------------------------------------------------------------
def test_enroll_devolve_template_de_512_float32(
    cliente: TestClient, fotos_cadastro: list[str]
) -> None:
    """O template e o vetor ArcFace serializado, e ele volta normalizado."""
    resposta = cliente.post(
        "/enroll",
        json={"imagemBase64": fotos_cadastro[0], "mimeType": "image/jpeg", "referencia": "op-1"},
    )
    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()

    assert corpo["dimensao"] == DIMENSAO_EMBEDDING == 512
    assert corpo["modeloVersao"] == _versao()
    assert corpo["duracaoMs"] >= 0

    crus = base64.b64decode(corpo["template"], validate=True)
    assert len(crus) == 512 * 4, "512 float32 little-endian"
    vetor = np.frombuffer(crus, dtype="<f4")
    assert np.isfinite(vetor).all()
    assert float(np.linalg.norm(vetor)) == pytest.approx(1.0, abs=1e-3)

    qualidade = corpo["qualidade"]
    assert set(qualidade) == {"nitidez", "iluminacao", "poseOk", "deteccao"}
    assert 0.0 <= qualidade["nitidez"] <= 1.0
    assert 0.0 <= qualidade["iluminacao"] <= 1.0
    assert isinstance(qualidade["poseOk"], bool)


def test_enroll_e_estavel_para_a_mesma_pessoa(
    cliente: TestClient, fotos_cadastro: list[str], fotos_marcacao: list[str]
) -> None:
    """Duas imagens distintas da mesma pessoa produzem vetores quase colineares.

    Este e o teste que mede o motor em si, sem passar pelo limiar: a similaridade
    entre o cadastro e a marcacao da mesma pessoa tem de ficar folgadamente acima
    da similaridade entre pessoas diferentes. Sem essa folga, nenhum limiar
    salvaria o sistema.
    """
    vetores_cadastro = []
    vetores_marcacao = []
    for cadastro, marcacao in zip(fotos_cadastro, fotos_marcacao, strict=True):
        for foto, destino in ((cadastro, vetores_cadastro), (marcacao, vetores_marcacao)):
            resposta = cliente.post(
                "/enroll", json={"imagemBase64": foto, "mimeType": "image/jpeg"}
            )
            assert resposta.status_code == 200, resposta.text
            destino.append(
                np.frombuffer(base64.b64decode(resposta.json()["template"]), dtype="<f4")
            )

    matriz = np.vstack(vetores_cadastro) @ np.vstack(vetores_marcacao).T
    proprios = np.diag(matriz)
    alheios = matriz[~np.eye(len(proprios), dtype=bool)]

    limiar = obter_configuracao().facial_limiar_similaridade
    assert proprios.min() > limiar, f"mesma pessoa caiu abaixo do limiar: {proprios.min():.3f}"
    assert alheios.max() < limiar, f"pessoas diferentes passaram do limiar: {alheios.max():.3f}"
    # A folga entre os dois grupos e o que da margem para calibrar o limiar por
    # cliente sem reescrever nada.
    assert proprios.min() - alheios.max() > 0.25


def test_enroll_recusa_imagem_com_mais_de_um_rosto(cliente: TestClient, cena: Any) -> None:
    """Cadastrar com o colega no enquadramento e o pior defeito possivel aqui."""
    imagem, _ = cena
    resposta = cliente.post(
        "/enroll",
        json={"imagemBase64": _para_jpeg_base64(imagem), "mimeType": "image/jpeg"},
    )
    assert resposta.status_code == 400
    assert resposta.headers["content-type"].startswith(MEDIA_TYPE_PROBLEMA)
    assert resposta.json()["codigo"] == "PONTO-VAL-001"
    assert "rostos" in resposta.json()["detail"]


# ---------------------------------------------------------------------------
# verificar
# ---------------------------------------------------------------------------
def test_mesma_pessoa_aprova_e_aponta_o_indice_certo(
    cliente: TestClient, templates: list[str], fotos_marcacao: list[str]
) -> None:
    """1:N contra os seis templates: cada pessoa bate com a propria, e so com ela."""
    for esperado, foto in enumerate(fotos_marcacao):
        resposta = cliente.post(
            "/verificar",
            json={
                "imagemBase64": foto,
                "mimeType": "image/jpeg",
                "templates": templates,
                "modeloVersao": _versao(),
                "referencia": f"op-{esperado}",
            },
        )
        assert resposta.status_code == 200, resposta.text
        corpo = resposta.json()
        assert corpo["aprovado"] is True, f"pessoa {esperado} nao foi reconhecida"
        assert (
            corpo["indice"] == esperado
        ), f"pessoa {esperado} casou com o template {corpo['indice']}"
        assert corpo["modeloVersao"] == _versao()


def test_pessoas_diferentes_reprovam(
    cliente: TestClient, templates: list[str], fotos_marcacao: list[str]
) -> None:
    """Sem o proprio template na lista, ninguem pode ser aprovado por semelhanca.

    Trinta comparacoes cruzadas (seis pessoas x cinco templates alheios). Uma
    unica aprovacao aqui e fraude trabalhista em producao, e o teste falha.
    """
    for pessoa, foto in enumerate(fotos_marcacao):
        alheios = [t for i, t in enumerate(templates) if i != pessoa]
        resposta = cliente.post(
            "/verificar",
            json={
                "imagemBase64": foto,
                "mimeType": "image/jpeg",
                "templates": alheios,
                "modeloVersao": _versao(),
            },
        )
        assert resposta.status_code == 200, resposta.text
        corpo = resposta.json()
        assert corpo["aprovado"] is False, f"pessoa {pessoa} foi aprovada contra rosto alheio"
        assert corpo["indice"] == -1


def test_reprovacao_com_exigir_aprovacao_vira_403_sem_detalhe(
    cliente: TestClient, templates: list[str], fotos_marcacao: list[str]
) -> None:
    """`PONTO-SCORE-003` tem `expoe_regra: false`: 403 seco, sem placar."""
    resposta = cliente.post(
        "/verificar",
        json={
            "imagemBase64": fotos_marcacao[0],
            "mimeType": "image/jpeg",
            "templates": [templates[1], templates[2]],
            "modeloVersao": _versao(),
            "exigirAprovacao": True,
        },
    )
    assert resposta.status_code == 403
    assert resposta.headers["content-type"].startswith(MEDIA_TYPE_PROBLEMA)
    corpo = resposta.json()
    assert corpo["codigo"] == "PONTO-SCORE-003"
    assert "detail" not in corpo, "o motivo da reprovacao nao pode voltar ao chamador"


def test_versao_de_modelo_divergente_e_erro(
    cliente: TestClient, templates: list[str], fotos_marcacao: list[str]
) -> None:
    """Comparar vetores de motores diferentes nao devolve numero, devolve erro."""
    resposta = cliente.post(
        "/verificar",
        json={
            "imagemBase64": fotos_marcacao[0],
            "mimeType": "image/jpeg",
            "templates": templates,
            "modeloVersao": "motor-de-outra-era-v9",
        },
    )
    assert resposta.status_code == 400
    corpo = resposta.json()
    assert corpo["codigo"] == "PONTO-VAL-001"
    assert "modeloVersao" in corpo["detail"]


def test_template_com_tamanho_errado_e_erro(cliente: TestClient, fotos_marcacao: list[str]) -> None:
    """Template de 128 dimensoes e base corrompida ou versao trocada: precisa aparecer."""
    curto = base64.b64encode(np.ones(128, dtype="<f4").tobytes()).decode("ascii")
    resposta = cliente.post(
        "/verificar",
        json={
            "imagemBase64": fotos_marcacao[0],
            "mimeType": "image/jpeg",
            "templates": [curto],
            "modeloVersao": _versao(),
        },
    )
    assert resposta.status_code == 400
    assert resposta.json()["codigo"] == "PONTO-VAL-001"


# ---------------------------------------------------------------------------
# Entrada invalida
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("caminho", ["/enroll", "/verificar"])
def test_imagem_sem_rosto_vira_erro_tratado(
    cliente: TestClient, templates: list[str], caminho: str
) -> None:
    """Parede chapada e ruido branco: sem rosto, erro do catalogo, nunca 500."""
    chapada = np.full((480, 640, 3), 130, dtype=np.uint8)
    ruido = np.random.default_rng(20260808).integers(0, 256, (480, 640, 3), dtype=np.uint8)

    for matriz, nome in ((chapada, "chapada"), (ruido, "ruido")):
        corpo: dict[str, Any] = {
            "imagemBase64": _para_jpeg_base64(matriz),
            "mimeType": "image/jpeg",
        }
        if caminho == "/verificar":
            corpo |= {"templates": templates, "modeloVersao": _versao()}
        resposta = cliente.post(caminho, json=corpo)
        assert resposta.status_code == 400, f"{caminho}/{nome}: {resposta.text}"
        assert resposta.headers["content-type"].startswith(MEDIA_TYPE_PROBLEMA)
        problema = resposta.json()
        assert problema["codigo"] == "PONTO-VAL-001"
        assert "Nenhum rosto detectado" in problema["detail"]


def test_mime_type_fora_da_lista_e_415(cliente: TestClient, fotos_cadastro: list[str]) -> None:
    resposta = cliente.post(
        "/enroll", json={"imagemBase64": fotos_cadastro[0], "mimeType": "image/gif"}
    )
    assert resposta.status_code == 415
    assert resposta.json()["codigo"] == "PONTO-VAL-009"


def test_base64_invalido_e_400(cliente: TestClient) -> None:
    resposta = cliente.post(
        "/enroll", json={"imagemBase64": "nao!!!e!!!base64!!!" * 4, "mimeType": "image/jpeg"}
    )
    assert resposta.status_code == 400
    assert resposta.json()["codigo"] == "PONTO-VAL-001"


def test_bytes_que_nao_sao_imagem_e_400(cliente: TestClient) -> None:
    """Base64 valido de conteudo que nao e imagem nenhuma."""
    lixo = base64.b64encode(b"isto nao e um JPEG, e apenas texto" * 8).decode("ascii")
    resposta = cliente.post("/enroll", json={"imagemBase64": lixo, "mimeType": "image/jpeg"})
    assert resposta.status_code == 400
    assert resposta.json()["codigo"] == "PONTO-VAL-001"


# ---------------------------------------------------------------------------
# liveness
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def sequencia_viva(cena: Any) -> list[str]:
    """Tres quadros da mesma pessoa, com a janela deslocando alguns pixels.

    E a assinatura de uma mao humana segurando um celular: a cena e a mesma, o
    enquadramento nao para quieto.
    """
    imagem, rostos = cena
    return [
        _para_jpeg_base64(
            _recorte(imagem, rostos[0].bbox, margem=0.4, escala=2.0, deslocamento=(dx, dy)),
            qualidade=92,
        )
        for dx, dy in ((0, 0), (4, -3), (-3, 4))
    ]


def test_liveness_recusa_quadro_unico(cliente: TestClient, sequencia_viva: list[str]) -> None:
    """Prova de vida sobre imagem estatica unica e ilusao de seguranca."""
    resposta = cliente.post(
        "/liveness", json={"quadrosBase64": sequencia_viva[:1], "mimeType": "image/jpeg"}
    )
    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()
    assert corpo["aprovado"] is False
    assert corpo["quadrosAnalisados"] == 1


def test_liveness_reprova_quadro_repetido(cliente: TestClient, sequencia_viva: list[str]) -> None:
    """Foto impressa parada / quadro congelado: nenhum movimento entre quadros."""
    congelado = [sequencia_viva[0]] * 3
    resposta = cliente.post(
        "/liveness", json={"quadrosBase64": congelado, "mimeType": "image/jpeg"}
    )
    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()
    assert corpo["aprovado"] is False
    assert corpo["sinais"]["rostoEmTodos"] is True
    assert corpo["sinais"]["desafioCumprido"] is False


def test_liveness_reprova_sequencia_sem_rosto(cliente: TestClient) -> None:
    """Sem rosto em algum quadro nao ha prova de vida a fazer."""
    chapada = _para_jpeg_base64(np.full((480, 640, 3), 130, dtype=np.uint8))
    resposta = cliente.post(
        "/liveness", json={"quadrosBase64": [chapada, chapada], "mimeType": "image/jpeg"}
    )
    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()
    assert corpo["aprovado"] is False
    assert corpo["sinais"]["rostoEmTodos"] is False


def test_liveness_reprovado_com_exigir_aprovacao_vira_403(
    cliente: TestClient, sequencia_viva: list[str]
) -> None:
    """`PONTO-SCORE-002` tambem e `expoe_regra: false`: 403 sem dizer qual sinal caiu."""
    resposta = cliente.post(
        "/liveness",
        json={
            "quadrosBase64": [sequencia_viva[0]] * 2,
            "mimeType": "image/jpeg",
            "exigirAprovacao": True,
        },
    )
    assert resposta.status_code == 403
    corpo = resposta.json()
    assert corpo["codigo"] == "PONTO-SCORE-002"
    assert "detail" not in corpo


def test_liveness_sinais_sao_apenas_booleanos(
    cliente: TestClient, sequencia_viva: list[str]
) -> None:
    """Nenhum escore no laudo: dizer *por quanto* um sinal caiu ensina a corrigi-lo."""
    resposta = cliente.post(
        "/liveness", json={"quadrosBase64": sequencia_viva, "mimeType": "image/jpeg"}
    )
    assert resposta.status_code == 200, resposta.text
    sinais = resposta.json()["sinais"]
    assert set(sinais) == {"rostoEmTodos", "desafioCumprido", "texturaOk", "moireDetectado"}
    assert all(isinstance(v, bool) for v in sinais.values())


def test_liveness_aprova_sequencia_com_movimento(
    cliente: TestClient, sequencia_viva: list[str]
) -> None:
    """A sequencia com deslocamento passa nos tres sinais passivos.

    Sem este teste, a heuristica poderia estar reprovando tudo — e uma prova de
    vida que reprova todo mundo passaria em todos os testes negativos acima sem
    servir para nada.
    """
    resposta = cliente.post(
        "/liveness",
        json={"quadrosBase64": sequencia_viva, "mimeType": "image/jpeg", "referencia": "op-live"},
    )
    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()
    assert corpo["sinais"] == {
        "rostoEmTodos": True,
        "desafioCumprido": True,
        "texturaOk": True,
        "moireDetectado": False,
    }
    assert corpo["aprovado"] is True
    assert corpo["quadrosAnalisados"] == 3


def test_liveness_reprova_simulacao_de_tela(cliente: TestClient, cena: Any) -> None:
    """Batimento periodico sobre a imagem — a assinatura de uma tela fotografada.

    **Isto e uma simulacao, nao um ataque real.** A grade senoidal de periodo
    3 px reproduz o efeito que a grade de subpixels de um monitor produz quando
    fotografada por outra camera; ela nao substitui um teste com celular de
    verdade apontado para um monitor de verdade, que so pode ser feito com
    hardware na mao (F8). O que este teste garante e que o sinal `moireDetectado`
    **funciona** e nao esta ali de enfeite.
    """
    imagem, rostos = cena
    quadros = []
    for dx, dy in ((0, 0), (4, -3), (-3, 4)):
        base = _recorte(imagem, rostos[0].bbox, margem=0.4, escala=2.0, deslocamento=(dx, dy))
        altura, largura = base.shape[:2]
        ys, xs = np.mgrid[0:altura, 0:largura]
        grade = 12 * np.sin(2 * np.pi * xs / 3.0) + 12 * np.sin(2 * np.pi * ys / 3.0)
        tela = np.clip(
            cv2.GaussianBlur(base.astype(np.float32), (3, 3), 0.8) + grade[..., None], 0, 255
        ).astype(np.uint8)
        quadros.append(_para_jpeg_base64(tela, qualidade=88))

    resposta = cliente.post("/liveness", json={"quadrosBase64": quadros, "mimeType": "image/jpeg"})
    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()
    assert corpo["sinais"]["moireDetectado"] is True
    assert corpo["aprovado"] is False


def test_liveness_reprova_simulacao_de_foto_impressa(cliente: TestClient, cena: Any) -> None:
    """Perda de microtextura: desfoque, contraste achatado e JPEG agressivo.

    Tambem e simulacao (ver o teste acima). Ela reproduz o que papel fosco faz
    com a pele — some a microtextura que a camera captura de um rosto vivo —, e
    a folga entre o rosto real e este ataque simulado e pequena de proposito no
    limiar: e o sinal mais fraco dos tres, e o codigo diz isso.
    """
    imagem, rostos = cena
    quadros = []
    for dx, dy in ((0, 0), (4, -3), (-3, 4)):
        base = _recorte(imagem, rostos[1].bbox, margem=0.4, escala=2.0, deslocamento=(dx, dy))
        papel = cv2.GaussianBlur(base, (5, 5), 1.6)
        papel = cv2.convertScaleAbs(papel, alpha=0.85, beta=18)
        quadros.append(_para_jpeg_base64(papel, qualidade=60))

    resposta = cliente.post("/liveness", json={"quadrosBase64": quadros, "mimeType": "image/jpeg"})
    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()
    assert corpo["sinais"]["texturaOk"] is False
    assert corpo["aprovado"] is False


# ---------------------------------------------------------------------------
# ADR-006: o placar nao sai daqui
# ---------------------------------------------------------------------------
def test_nenhuma_resposta_traz_limiar_nem_similaridade(
    cliente: TestClient, templates: list[str], fotos_marcacao: list[str], sequencia_viva: list[str]
) -> None:
    """Varre as respostas reais das tres operacoes atras de placar vazado.

    O teste do andaime cobre `/health` e `/ready`; este cobre o caminho que
    agora produz numero de verdade, que e onde o vazamento passaria a ser
    possivel.
    """
    limiar = obter_configuracao().facial_limiar_similaridade
    corpos = [
        cliente.post(
            "/enroll", json={"imagemBase64": fotos_marcacao[0], "mimeType": "image/jpeg"}
        ).json(),
        cliente.post(
            "/verificar",
            json={
                "imagemBase64": fotos_marcacao[0],
                "mimeType": "image/jpeg",
                "templates": templates,
                "modeloVersao": _versao(),
            },
        ).json(),
        cliente.post(
            "/liveness", json={"quadrosBase64": sequencia_viva, "mimeType": "image/jpeg"}
        ).json(),
    ]
    for corpo in corpos:
        texto = json.dumps(corpo, ensure_ascii=False).lower()
        assert str(limiar) not in texto
        assert "limiar" not in texto
        assert "similaridade" not in texto
        assert "score" not in texto
