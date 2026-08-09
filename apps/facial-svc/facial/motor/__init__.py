"""Motor facial self-hosted: deteccao, embedding, comparacao e prova de vida.

Este subpacote e a **unica** parte do `facial-svc` que carrega peso ONNX. As
rotas (`facial/rotas/biometria.py`) nao sabem nada sobre InsightFace, numpy ou
OpenCV: elas validam envelope, chamam uma funcao daqui e traduzem o resultado
para o contrato HTTP. A separacao existe para que trocar o motor (decisao
prevista, e a razao de `modeloVersao` existir) seja mexer aqui dentro, e nao no
contrato.

O que roda aqui
---------------

``imagem``
    Decodifica base64 -> BGR (numpy), conferindo tipo e tamanho **antes** de
    decodificar. Decodificar imagem vinda de fora sem conferir antes e
    superficie de ataque classica.
``arcface``
    Carrega o pacote InsightFace (`buffalo_l`: detector RetinaFace `det_10g` +
    reconhecedor ArcFace `w600k_r50`, 512-d) sobre ONNX Runtime **CPU**, e
    entrega deteccao, alinhamento, embedding normalizado e metricas de
    qualidade.
``template``
    Serializa o embedding para transporte (base64 de float32 little-endian) e
    calcula similaridade de cosseno.
``liveness``
    Prova de vida **heuristica** multi-quadro. Ver a docstring do modulo: ela e
    explicitamente nao-normativa e o modulo diz o que ela nao cobre.

Tudo local, sem rede
--------------------

Nenhuma funcao daqui chama servico de terceiro. A unica rede possivel e o
download dos pesos na primeira execucao (`FACIAL_BAIXAR_MODELO`), que e
**desligado por padrao** e desligado sempre em producao — la os pesos chegam
pelo volume `facial-models`. Ver o README do app.
"""

from __future__ import annotations

from facial.motor.arcface import (
    MotorFacial,
    RostoDetectado,
    motor,
    reiniciar_motor,
)
from facial.motor.imagem import decodificar_imagem, validar_envelope
from facial.motor.liveness import LaudoLiveness, julgar_liveness
from facial.motor.template import (
    DIMENSAO_EMBEDDING,
    desserializar_template,
    melhor_correspondencia,
    serializar_template,
    similaridade_cosseno,
)

__all__ = [
    "DIMENSAO_EMBEDDING",
    "LaudoLiveness",
    "MotorFacial",
    "RostoDetectado",
    "decodificar_imagem",
    "desserializar_template",
    "julgar_liveness",
    "melhor_correspondencia",
    "motor",
    "reiniciar_motor",
    "serializar_template",
    "similaridade_cosseno",
    "validar_envelope",
]
