"""Carregamento do motor InsightFace/ArcFace sobre ONNX Runtime (CPU).

Qual modelo, e por que este
---------------------------

Pacote **`buffalo_l`** do InsightFace, rodando por ONNX Runtime no provedor
`CPUExecutionProvider`:

* deteccao: `det_10g.onnx` (RetinaFace ResNet50, ~17 MB);
* reconhecimento: `w600k_r50.onnx` (ArcFace ResNet50 treinado em WebFace600K,
  embedding de 512 dimensoes, ~174 MB).

Tres razoes praticas, na ordem em que pesaram:

1. **Roda em CPU.** A VPS nao tem GPU. Medido na propria VPS (8 vCPU, sob a
   carga normal dos outros servicos): **~0,7 s de ponta a ponta** por captura de
   640x480, do base64 ao template. Nao e tempo real, e e folgadamente suficiente
   para uma marcacao de ponto — a pessoa ja gastou mais que isso enquadrando o
   rosto. O primeiro request depois de subir paga ~2,8 s a mais, que e o
   carregamento dos pesos.
2. **Licenca aberta e uso consolidado.** Codigo MIT, pesos publicados pelo
   proprio projeto, base instalada grande. Motor biometrico e decisao que se
   revisita em anos, nao em meses.
3. **Nao inventa nada.** ArcFace com limiar de cosseno e o arranjo mais
   documentado que existe para 1:1, o que torna a calibragem do limiar um
   trabalho de engenharia normal em vez de pesquisa.

Alternativas descartadas: `antelopev2` (mesma familia, pesos com clausula de uso
nao-comercial), `face_recognition`/dlib (precisao materialmente inferior em
ArcFace-era benchmarks), e qualquer SaaS — este ultimo por decisao fundadora do
produto, nao por tecnica: **biometria nao sai da infraestrutura da SEEG**
(ADR-006, LGPD art. 5, II).

Modulos carregados, e os que **nao** sao
----------------------------------------

`allowed_modules=["detection", "recognition"]`. O pacote traz tambem
`genderage`, `2d106det` e `1k3d68` — juntos, mais de 140 MB de RAM e latencia
por chamada para produzir genero, idade e pose. Nada disso entra em decisao de
ponto eletronico, e **genero e idade inferidos sao dado pessoal que ninguem
pediu**: extrair o que nao se usa e criar passivo de LGPD de graca. A metrica de
pose que o bloco `qualidade` devolve sai da geometria dos 5 pontos-chave que o
proprio detector ja produz.

Carregamento preguicoso
-----------------------

O motor **nao** e carregado na subida do processo, de proposito: a `api` declara
`depends_on: facial-svc: condition: service_healthy`, e um processo que morre
por falta de peso `.onnx` prenderia a stack inteira. Ele sobe, responde
`/health`, reprova em `/ready` e diz que faltam os pesos. O carregamento
acontece na primeira captura, sob `threading.Lock` (o servidor tem varios
workers e o ONNX Runtime nao deve ser inicializado em corrida).
"""

from __future__ import annotations

import math
import pathlib
import threading
import time
from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np

from facial.config import Configuracao, obter_configuracao
from facial.erros import ErroDeAplicacao
from facial.log import obter_logger
from facial.motor.template import DIMENSAO_EMBEDDING

logger = obter_logger("motor.arcface")

CODIGO_MOTOR_INDISPONIVEL = "PONTO-INT-003"
CODIGO_ROSTO = "PONTO-VAL-001"


@dataclass(frozen=True, slots=True)
class RostoDetectado:
    """Um rosto detectado, ja com embedding normalizado e metricas de qualidade.

    `embedding` e biometria: nunca vai para log. `qualidade` e agregado
    (nitidez, iluminacao, pose) e pode ser devolvido ao chamador — e o que
    permite ao app dizer "chegue mais perto" em vez de "falhou".
    """

    embedding: np.ndarray[Any, np.dtype[np.float32]]
    bbox: tuple[float, float, float, float]
    pontos: np.ndarray[Any, np.dtype[np.float32]]
    escore_deteccao: float
    qualidade: dict[str, float | bool]
    recorte: np.ndarray[Any, np.dtype[np.uint8]]


def _raiz_insightface(config: Configuracao) -> str:
    """Converte `FACIAL_MODEL_DIR` na `root` que o InsightFace espera.

    O InsightFace resolve os pesos em `{root}/models/{pacote}`. O nosso volume e
    montado direto em `/models` (`FACIAL_MODEL_DIR`), entao a `root` equivalente
    e o **pai** desse diretorio — com `/models`, `root="/"` e os pesos caem em
    `/models/buffalo_l/*.onnx`, que e exatamente onde `/ready` procura
    (`Configuracao.modelos_presentes` faz glob `**/*.onnx`).

    Se alguem apontar `FACIAL_MODEL_DIR` para um diretorio com outro nome, a
    convencao do InsightFace vale sem traducao e os pesos vao para
    `{dir}/models/{pacote}` — continua dentro do volume, continua encontrado
    pelo glob.
    """
    caminho = pathlib.Path(config.facial_model_dir)
    if caminho.name == "models":
        return str(caminho.parent)
    return str(caminho)


class MotorFacial:
    """Fachada do InsightFace. Uma instancia por processo, carregada sob demanda."""

    def __init__(self, config: Configuracao | None = None) -> None:
        self._config = config or obter_configuracao()
        self._app: Any = None
        self._trava = threading.Lock()

    # -- carregamento -------------------------------------------------------
    @property
    def carregado(self) -> bool:
        return self._app is not None

    @property
    def versao_modelo(self) -> str:
        return self._config.facial_model_versao

    def carregar(self) -> Any:
        """Carrega os pesos uma unica vez. Reentrante e seguro entre threads."""
        aplicacao = self._app
        if aplicacao is not None:
            return aplicacao
        with self._trava:
            aplicacao = self._app  # outra thread pode ter ganho a corrida
            if aplicacao is None:
                aplicacao = self._construir()
                self._app = aplicacao
            return aplicacao

    def _construir(self) -> Any:
        config = self._config
        if not config.modelos_presentes and not config.facial_baixar_modelo:
            # Falha fechada e explicita: e melhor 503 dizendo "faltam os pesos"
            # do que um download de 300 MB disparado por uma marcacao de ponto.
            raise ErroDeAplicacao(
                CODIGO_MOTOR_INDISPONIVEL,
                detalhe=(
                    "Pesos do motor facial ausentes e download automatico desligado. "
                    "Popule o volume `facial-models` (FACIAL_MODEL_DIR) ou ligue "
                    "FACIAL_BAIXAR_MODELO fora de producao."
                ),
                tentar_novamente_em=30,
                contexto_log={"etapa": "carregamento"},
            )

        inicio = time.perf_counter()
        try:
            # Import tardio: manter `insightface`/`onnxruntime` fora do caminho de
            # import do modulo deixa `/health` respondendo mesmo com o pacote
            # quebrado, que e o comportamento que o `depends_on` da api exige.
            from insightface.app import FaceAnalysis
        except ImportError as exc:  # pragma: no cover - defeito de instalacao
            raise ErroDeAplicacao(
                CODIGO_MOTOR_INDISPONIVEL,
                detalhe="Dependencia do motor facial ausente na imagem.",
                contexto_log={"etapa": "import", "tipo": type(exc).__name__},
            ) from exc

        try:
            aplicacao = FaceAnalysis(
                name=config.facial_modelo_pacote,
                root=_raiz_insightface(config),
                allowed_modules=["detection", "recognition"],
                providers=["CPUExecutionProvider"],
            )
            aplicacao.prepare(
                ctx_id=-1,  # -1 = CPU. Nao ha, e nao pode haver, dependencia de CUDA.
                det_thresh=config.facial_det_thresh,
                det_size=(config.facial_det_size, config.facial_det_size),
            )
        except Exception as exc:
            logger.error(
                "falha ao carregar o motor facial",
                extra={"tipo": type(exc).__name__, "pacote": config.facial_modelo_pacote},
            )
            raise ErroDeAplicacao(
                CODIGO_MOTOR_INDISPONIVEL,
                detalhe="Nao foi possivel carregar os pesos do motor facial.",
                tentar_novamente_em=30,
                contexto_log={"etapa": "carregamento", "tipo": type(exc).__name__},
            ) from exc

        logger.info(
            "motor facial carregado",
            extra={
                "pacote": config.facial_modelo_pacote,
                "modeloVersao": config.facial_model_versao,
                "provedor": "CPUExecutionProvider",
                "detSize": config.facial_det_size,
                "duracaoMs": round((time.perf_counter() - inicio) * 1000),
            },
        )
        return aplicacao

    # -- inferencia ---------------------------------------------------------
    def detectar(
        self, imagem: np.ndarray[Any, np.dtype[np.uint8]], *, maximo: int = 0
    ) -> list[RostoDetectado]:
        """Detecta, alinha e extrai o embedding de cada rosto da imagem.

        Devolve em ordem decrescente de area do `bbox`: quando ha mais de um
        rosto no quadro, o que interessa a uma marcacao de ponto e o que esta na
        frente da camera, e nao o transeunte ao fundo.
        """
        aplicacao = self.carregar()
        try:
            rostos = aplicacao.get(imagem, max_num=maximo)
        except Exception as exc:  # pragma: no cover - falha de runtime do ONNX
            logger.error("falha na inferencia", extra={"tipo": type(exc).__name__})
            raise ErroDeAplicacao(
                "PONTO-INT-001",
                contexto_log={"etapa": "inferencia", "tipo": type(exc).__name__},
            ) from exc

        detectados = [self._montar(imagem, rosto) for rosto in rostos]
        detectados.sort(
            key=lambda r: (r.bbox[2] - r.bbox[0]) * (r.bbox[3] - r.bbox[1]),
            reverse=True,
        )
        return detectados

    def rosto_unico(
        self,
        imagem: np.ndarray[Any, np.dtype[np.uint8]],
        *,
        exigir_unico: bool = True,
    ) -> RostoDetectado:
        """Um rosto, e so um. Zero ou muitos sao erro tratado, nao excecao crua.

        `exigir_unico=True` no enrollment e a regra que evita o pior defeito
        possivel nesta base: cadastrar em nome de um colaborador o rosto do
        colega que apareceu atras dele. Na verificacao a exigencia e relaxada —
        um terceiro passando ao fundo do terminal nao pode reprovar quem esta
        marcando ponto —, e vale o rosto de maior area.
        """
        rostos = self.detectar(imagem)
        if not rostos:
            raise ErroDeAplicacao(
                CODIGO_ROSTO,
                detalhe=(
                    "Nenhum rosto detectado na imagem. Enquadre o rosto, aproxime-se "
                    "da camera e verifique a iluminacao."
                ),
                contexto_log={"etapa": "deteccao", "rostos": 0},
            )
        if exigir_unico and len(rostos) > 1:
            raise ErroDeAplicacao(
                CODIGO_ROSTO,
                detalhe=(
                    f"{len(rostos)} rostos detectados na imagem. O cadastro exige "
                    "exatamente um rosto no enquadramento."
                ),
                contexto_log={"etapa": "deteccao", "rostos": len(rostos)},
            )
        return rostos[0]

    # -- qualidade ----------------------------------------------------------
    def _montar(self, imagem: np.ndarray[Any, np.dtype[np.uint8]], rosto: Any) -> RostoDetectado:
        bbox = tuple(float(v) for v in rosto.bbox[:4])
        pontos = np.asarray(rosto.kps, dtype=np.float32)
        recorte = _recortar(imagem, bbox)
        embedding = np.asarray(rosto.normed_embedding, dtype=np.float32)
        if embedding.shape != (DIMENSAO_EMBEDDING,):  # pragma: no cover - troca de pacote
            raise ErroDeAplicacao(
                "PONTO-INT-001",
                contexto_log={
                    "etapa": "embedding",
                    "motivo": "dimensao inesperada",
                    "dimensao": int(embedding.size),
                },
            )
        return RostoDetectado(
            embedding=embedding,
            bbox=(bbox[0], bbox[1], bbox[2], bbox[3]),
            pontos=pontos,
            escore_deteccao=float(rosto.det_score),
            qualidade=_qualidade(recorte, pontos, float(rosto.det_score)),
            recorte=recorte,
        )


def _recortar(
    imagem: np.ndarray[Any, np.dtype[np.uint8]], bbox: tuple[float, ...]
) -> np.ndarray[Any, np.dtype[np.uint8]]:
    """Recorte do rosto com margem de 10%, preso aos limites da imagem."""
    altura, largura = imagem.shape[:2]
    x1, y1, x2, y2 = bbox
    mx, my = (x2 - x1) * 0.1, (y2 - y1) * 0.1
    a = max(0, int(x1 - mx))
    b = max(0, int(y1 - my))
    c = min(largura, int(x2 + mx))
    d = min(altura, int(y2 + my))
    if c - a < 2 or d - b < 2:  # pragma: no cover - bbox degenerado
        return imagem
    return np.ascontiguousarray(imagem[b:d, a:c])


def _qualidade(
    recorte: np.ndarray[Any, np.dtype[np.uint8]],
    pontos: np.ndarray[Any, np.dtype[np.float32]],
    escore_deteccao: float,
) -> dict[str, float | bool]:
    """Metricas de captura, todas em [0, 1] (ou booleanas).

    Elas nao julgam identidade — julgam se a **foto** presta. Recusar uma captura
    ruim no momento em que ela e tirada custa dois segundos; descobrir meses
    depois, quando o reconhecimento falha todos os dias com um colaborador
    especifico, custa a confianca no sistema inteiro.
    """
    cinza = cv2.cvtColor(recorte, cv2.COLOR_BGR2GRAY)

    # Nitidez: variancia do laplaciano. ~300 e o piso pratico de "foto nitida" em
    # recorte de rosto; acima disso a diferenca deixa de importar, dai o teto.
    nitidez = float(np.clip(cv2.Laplacian(cinza, cv2.CV_64F).var() / 300.0, 0.0, 1.0))

    # Iluminacao: distancia do brilho medio ao meio da escala. Penaliza tanto
    # rosto estourado por contraluz quanto rosto na sombra.
    media = float(cinza.mean())
    iluminacao = float(np.clip(1.0 - abs(media - 128.0) / 128.0, 0.0, 1.0))

    return {
        "nitidez": round(nitidez, 3),
        "iluminacao": round(iluminacao, 3),
        "poseOk": _pose_ok(pontos),
        "deteccao": round(float(np.clip(escore_deteccao, 0.0, 1.0)), 3),
    }


def _pose_ok(pontos: np.ndarray[Any, np.dtype[np.float32]]) -> bool:
    """Pose aceitavel a partir dos 5 pontos-chave do detector.

    Nao carregamos o modelo de pose 3D (`1k3d68`, ~143 MB) so para isto. Os 5
    pontos que o detector ja devolve — olho esquerdo, olho direito, nariz, canto
    esquerdo e canto direito da boca — dao dois sinais suficientes para um
    aviso de captura:

    * **rolagem**: inclinacao da linha dos olhos;
    * **guinada** (aproximada): o quanto o nariz esta deslocado do meio da linha
      dos olhos, em fracao da distancia interocular. Rosto de perfil desloca o
      nariz para uma das pontas.

    E um aviso de enquadramento, nao um portao: `poseOk: false` nao reprova a
    captura sozinho, informa o app.
    """
    if pontos.shape[0] < 3:  # pragma: no cover - detector sempre devolve 5
        return False
    olho_e, olho_d, nariz = pontos[0], pontos[1], pontos[2]
    dx = float(olho_d[0] - olho_e[0])
    dy = float(olho_d[1] - olho_e[1])
    interocular = math.hypot(dx, dy)
    if interocular < 1e-6:  # pragma: no cover
        return False
    rolagem_graus = abs(math.degrees(math.atan2(dy, dx)))
    meio_x = (olho_e[0] + olho_d[0]) / 2.0
    guinada = abs(float(nariz[0]) - float(meio_x)) / interocular
    return rolagem_graus <= 25.0 and guinada <= 0.35


# --------------------------------------------------------------------------
# Instancia de processo
# --------------------------------------------------------------------------
_motor: MotorFacial | None = None
_trava_global = threading.Lock()


def motor() -> MotorFacial:
    """Instancia unica do motor neste processo (nao carrega os pesos ainda)."""
    global _motor
    if _motor is None:
        with _trava_global:
            if _motor is None:
                _motor = MotorFacial()
    return _motor


def reiniciar_motor() -> None:
    """Descarta a instancia. Existe para o teste poder trocar a configuracao."""
    global _motor
    with _trava_global:
        _motor = None
