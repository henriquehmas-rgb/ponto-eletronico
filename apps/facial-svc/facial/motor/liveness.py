"""Prova de vida multi-quadro **heuristica**. Leia a limitacao antes de usar.

O que esta implementado aqui NAO e um classificador de anti-spoofing treinado
--------------------------------------------------------------------------------

Isto e importante o bastante para abrir o modulo. O estado da arte para prova de
vida passiva de quadro unico e um classificador dedicado (a familia
`MiniFASNet` do *Silent-Face-Anti-Spoofing*, por exemplo). Ele **nao** foi
integrado nesta entrega, por uma razao concreta: o projeto original publica
pesos PyTorch, e as conversoes para ONNX que circulam sao espelhos de terceiros
sem cadeia de custodia — baixar peso biometrico de repositorio nao oficial para
dentro de uma imagem de producao troca um risco tecnico por um risco de cadeia
de suprimentos pior.

O que esta implementado e um conjunto de **heuristicas classicas** sobre
multiplos quadros. Elas pegam o ataque preguicoso (foto impressa parada, quadro
repetido, tela com moire visivel) e **nao substituem** um classificador
treinado contra ataque de apresentacao com mascara, papel fosco de alta
qualidade ou tela OLED de alta densidade.

Consequencia pratica, e ela e normativa: enquanto este modulo for a unica prova
de vida do sistema, o resultado de `/liveness` e **sinal de confianca**
(alimenta o peso `peso_biometria` do score do ADR-008), e nao um portao
suficiente sozinho para uma marcacao sem qualquer outra evidencia. A troca por
um classificador dedicado esta prevista e cabe atras desta mesma funcao:
`julgar_liveness` e a fronteira, e o contrato de `/liveness` nao muda.

Os quatro sinais
----------------

``rostoEmTodos``
    Ha exatamente um rosto plausivel em cada quadro. Ataque que troca de cena no
    meio da sequencia cai aqui.
``desafioCumprido``
    Movimento **entre** quadros, medido no deslocamento dos 5 pontos-chave
    normalizado pela distancia interocular. Uma foto impressa parada da ~0. O
    limite superior tambem importa: deslocamento gigante e outra pessoa/cena, e
    nao "cumpriu o desafio".
``texturaOk``
    Energia de alta frequencia do recorte do rosto (variancia do laplaciano).
    Papel e tela reproduzida perdem microtextura de pele.
``moireDetectado``
    Pico periodico no espectro de Fourier do recorte, sinal caracteristico da
    grade de pixels de uma tela sendo fotografada.

Veredito: ``rostoEmTodos and desafioCumprido and texturaOk and not moireDetectado``.

O que sai daqui e o que fica
----------------------------

O laudo completo (`sinais`) fica no servidor, para auditoria e para o score. Os
**valores numericos** nao saem nem no laudo: `PONTO-SCORE-002` tem
`expoe_regra: false`, e dizer *qual* sinal reprovou — pior ainda, por quanto —
ensina o fraudador a corrigir exatamente aquele.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import Any

import cv2
import numpy as np

from facial.config import Configuracao
from facial.log import obter_logger
from facial.motor.arcface import MotorFacial, RostoDetectado

logger = obter_logger("motor.liveness")

#: Deslocamento minimo dos pontos-chave entre quadros, em fracao da distancia
#: interocular. Abaixo disso a cena esta parada: nem microtremor de mao humana.
MOVIMENTO_MINIMO = 0.010

#: Teto do deslocamento. Acima disso nao houve "desafio cumprido", houve troca
#: de cena — o quadro seguinte nao e a continuacao do anterior.
MOVIMENTO_MAXIMO = 1.20

#: Piso de variancia do laplaciano do recorte padronizado em 160x160.
#:
#: Medido em `tests/test_motor_facial.py` sobre seis rostos reais e sobre a
#: simulacao de foto impressa (desfoque + perda de contraste + JPEG agressivo):
#: rostos reais ficaram entre 59 e 164; a simulacao de papel, entre 24 e 49.
#: 55 fica no meio da unica folga que existe — e ela e **estreita**, que e o
#: motivo pratico de este modulo se declarar nao-normativo. Papel fotografico
#: bom, fotografado de perto, sobe acima deste piso.
TEXTURA_MINIMA = 55.0

#: Razao entre o pico do espectro na banda alta e a mediana da banda. A grade de
#: pixels de uma tela fotografada produz pico isolado muito acima do fundo.
#:
#: Na mesma medicao: rostos reais entre 14 e 42; simulacao de tela (batimento
#: senoidal de periodo 3 px) entre 207 e 356. 100 fica com folga larga dos dois
#: lados — este e o sinal mais confiavel dos tres.
MOIRE_RAZAO_MINIMA = 100.0


@dataclass(frozen=True, slots=True)
class LaudoLiveness:
    """Veredito e sinais. Os sinais ficam no servidor (auditoria e score)."""

    aprovado: bool
    sinais: dict[str, bool] = field(default_factory=dict)
    quadros_analisados: int = 0
    motivo_interno: str = ""


def julgar_liveness(
    quadros: list[np.ndarray[Any, np.dtype[np.uint8]]],
    motor: MotorFacial,
    config: Configuracao,
) -> LaudoLiveness:
    """Julga a sequencia de quadros. Nunca levanta por reprovacao — reprovar e resultado.

    Levanta `ErroDeAplicacao` apenas para condicao de entrada (imagem invalida) e
    de motor (pesos ausentes), que sobem de `MotorFacial.detectar`.
    """
    minimo = config.facial_liveness_min_quadros
    if len(quadros) < minimo:
        # Prova de vida sobre imagem estatica unica e ilusao de seguranca: nao ha
        # "quase" aqui, e reprovacao direta.
        return LaudoLiveness(
            aprovado=False,
            sinais={
                "rostoEmTodos": False,
                "desafioCumprido": False,
                "texturaOk": False,
                "moireDetectado": False,
            },
            quadros_analisados=len(quadros),
            motivo_interno=f"quadros insuficientes ({len(quadros)} < {minimo})",
        )

    principais: list[RostoDetectado] = []
    rosto_em_todos = True
    for quadro in quadros:
        detectados = motor.detectar(quadro)
        if not detectados:
            rosto_em_todos = False
            continue
        principais.append(detectados[0])

    if not rosto_em_todos or len(principais) < minimo:
        return LaudoLiveness(
            aprovado=False,
            sinais={
                "rostoEmTodos": False,
                "desafioCumprido": False,
                "texturaOk": False,
                "moireDetectado": False,
            },
            quadros_analisados=len(quadros),
            motivo_interno="rosto ausente em ao menos um quadro",
        )

    movimento = _movimento_entre_quadros(principais)
    desafio_cumprido = MOVIMENTO_MINIMO <= movimento <= MOVIMENTO_MAXIMO

    texturas = [_textura(rosto.recorte) for rosto in principais]
    textura_ok = float(np.median(texturas)) >= TEXTURA_MINIMA

    moires = [_razao_moire(rosto.recorte) for rosto in principais]
    moire_detectado = float(np.median(moires)) >= MOIRE_RAZAO_MINIMA

    aprovado = desafio_cumprido and textura_ok and not moire_detectado

    # Log sem numero: o valor de cada sinal e exatamente o que nao pode circular.
    logger.info(
        "prova de vida julgada",
        extra={
            "aprovado": aprovado,
            "quadros": len(quadros),
            "desafioCumprido": desafio_cumprido,
            "texturaOk": textura_ok,
            "moireDetectado": moire_detectado,
        },
    )
    return LaudoLiveness(
        aprovado=aprovado,
        sinais={
            "rostoEmTodos": True,
            "desafioCumprido": desafio_cumprido,
            "texturaOk": textura_ok,
            "moireDetectado": moire_detectado,
        },
        quadros_analisados=len(quadros),
        motivo_interno="" if aprovado else "sinais passivos insuficientes",
    )


def _movimento_entre_quadros(rostos: list[RostoDetectado]) -> float:
    """Deslocamento medio dos pontos-chave, normalizado pela distancia interocular.

    A normalizacao e o que torna o numero comparavel entre uma captura de perto e
    uma de longe: sem ela, "movimento" seria so uma medida de quao grande o rosto
    aparece no quadro.
    """
    if len(rostos) < 2:  # pragma: no cover - chamada sempre com >= minimo
        return 0.0
    deslocamentos: list[float] = []
    for anterior, atual in itertools.pairwise(rostos):
        interocular = float(np.linalg.norm(anterior.pontos[1] - anterior.pontos[0]))
        if interocular < 1e-6:  # pragma: no cover
            continue
        passo = float(np.mean(np.linalg.norm(atual.pontos - anterior.pontos, axis=1)))
        deslocamentos.append(passo / interocular)
    return float(np.mean(deslocamentos)) if deslocamentos else 0.0


def _textura(recorte: np.ndarray[Any, np.dtype[np.uint8]]) -> float:
    """Energia de alta frequencia do recorte, em escala padronizada de 160 px."""
    cinza = cv2.cvtColor(_padronizar(recorte), cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(cinza, cv2.CV_64F).var())


def _razao_moire(recorte: np.ndarray[Any, np.dtype[np.uint8]]) -> float:
    """Razao pico/mediana do espectro na banda alta — assinatura de grade de tela.

    Uma tela fotografada por outra camera produz batimento entre duas grades
    regulares, e batimento regular vira **pico isolado** no espectro. Pele nao
    tem periodicidade: seu espectro alto e ruido de fundo, sem pico destacado.
    """
    cinza = cv2.cvtColor(_padronizar(recorte), cv2.COLOR_BGR2GRAY).astype(np.float32)
    # Janela de Hanning: sem ela, a descontinuidade da borda do recorte vira ela
    # propria um "pico" espectral e todo rosto pareceria uma tela.
    janela = np.outer(np.hanning(cinza.shape[0]), np.hanning(cinza.shape[1]))
    espectro = np.abs(np.fft.fftshift(np.fft.fft2(cinza * janela)))

    altura, largura = espectro.shape
    cy, cx = altura // 2, largura // 2
    ys, xs = np.ogrid[:altura, :largura]
    raio = np.sqrt((ys - cy) ** 2 + (xs - cx) ** 2)
    limite = min(cy, cx)
    # Banda alta: de 45% a 95% do raio de Nyquist. Abaixo disso mora a estrutura
    # do rosto; na borda extrema, o ruido do sensor.
    banda = (raio >= 0.45 * limite) & (raio <= 0.95 * limite)
    valores = espectro[banda]
    if valores.size == 0:  # pragma: no cover
        return 0.0
    mediana = float(np.median(valores))
    if mediana <= 1e-9:  # pragma: no cover
        return 0.0
    return float(np.max(valores) / mediana)


def _padronizar(
    recorte: np.ndarray[Any, np.dtype[np.uint8]],
) -> np.ndarray[Any, np.dtype[np.uint8]]:
    """Reamostra o recorte para 160x160 — sem isso, os limiares dependeriam da
    distancia entre a pessoa e a camera, o que os tornaria inuteis."""
    return np.asarray(cv2.resize(recorte, (160, 160), interpolation=cv2.INTER_AREA), np.uint8)
