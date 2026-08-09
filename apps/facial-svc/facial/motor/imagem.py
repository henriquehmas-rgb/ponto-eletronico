"""Entrada de imagem: valida o envelope e decodifica base64 -> BGR.

Ordem das conferencias, e por que ela e essa
--------------------------------------------

1. **Tipo declarado** (`mimeType`) contra `FACIAL_TIPOS_ACEITOS` -> `PONTO-VAL-009`.
2. **Tamanho**, estimado pelo comprimento do base64 e depois conferido nos bytes
   decodificados, contra `FACIAL_TAMANHO_MAXIMO_BYTES` -> `PONTO-VAL-008`.
3. **Decodificacao base64** -> `PONTO-VAL-001`.
4. **Decodificacao da imagem** (OpenCV) -> `PONTO-VAL-001`.

As duas primeiras acontecem **antes** de qualquer decodificacao: entregar bytes
arbitrarios de terceiro a um decodificador de imagem sem antes limitar tamanho e
tipo e a forma classica de transformar um endpoint de upload em consumo de
memoria. O teto de comprimento do base64 e conferido antes mesmo do
`b64decode` para que uma string de 400 MB nunca chegue a virar `bytes`.

Nada do conteudo entra em log nem em mensagem de erro (ADR-006): as mensagens
falam de tamanho, tipo e "nao foi possivel decodificar", nunca de pixels,
dimensoes ou recorte.
"""

from __future__ import annotations

import base64
import binascii
import math
from typing import Any

import cv2
import numpy as np

from facial.config import Configuracao
from facial.erros import ErroDeAplicacao
from facial.log import obter_logger

logger = obter_logger("motor.imagem")

CODIGO_TIPO_NAO_SUPORTADO = "PONTO-VAL-009"
CODIGO_TAMANHO_EXCEDIDO = "PONTO-VAL-008"
CODIGO_CORPO_INVALIDO = "PONTO-VAL-001"

#: Menor lado aceito. Abaixo disso o detector nao tem o que detectar e o embedding
#: sai de uma interpolacao, nao de um rosto.
LADO_MINIMO_PX = 32

#: Maior lado aceito antes do redimensionamento. Imagem de 8000 px nao melhora o
#: reconhecimento (o detector trabalha em 640) e multiplica o custo de CPU.
LADO_MAXIMO_PX = 4096


def _erro(codigo: str, detalhe: str) -> ErroDeAplicacao:
    return ErroDeAplicacao(codigo, detalhe=detalhe, contexto_log={"etapa": "entrada"})


def validar_envelope(mime_type: str, base64_len: int, config: Configuracao) -> None:
    """Confere tipo e teto de tamanho **sem decodificar nada**.

    `base64_len` e o comprimento da string base64. Cada 4 caracteres viram no
    maximo 3 bytes, entao `ceil(len/4)*3` e um teto seguro do tamanho decodificado
    — se ja esse teto estoura o limite, nao ha por que alocar os bytes.
    """
    if mime_type not in config.lista_tipos_aceitos:
        raise _erro(
            CODIGO_TIPO_NAO_SUPORTADO,
            f"Tipo '{mime_type}' nao aceito. Aceitos: {', '.join(config.lista_tipos_aceitos)}.",
        )
    teto_estimado = math.ceil(base64_len / 4) * 3
    if teto_estimado > config.facial_tamanho_maximo_bytes:
        raise _erro(
            CODIGO_TAMANHO_EXCEDIDO,
            f"Imagem acima de {config.facial_tamanho_maximo_bytes} bytes.",
        )


def decodificar_imagem(
    imagem_base64: str, mime_type: str, config: Configuracao
) -> np.ndarray[Any, np.dtype[np.uint8]]:
    """Devolve a imagem como matriz BGR `uint8`, ou levanta `ErroDeAplicacao`.

    A matriz devolvida vive em memoria pelo tempo da extracao e e descartada
    junto com o escopo da requisicao. **Nada e escrito em disco** — em servico
    biometrico, arquivo temporario e vazamento com data marcada (ADR-006).
    """
    validar_envelope(mime_type, len(imagem_base64), config)

    try:
        # `validate=True`: base64 com lixo no meio e requisicao malformada, nao
        # algo a "corrigir" silenciosamente descartando caracteres.
        crus = base64.b64decode(imagem_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise _erro(CODIGO_CORPO_INVALIDO, "Campo de imagem nao e base64 valido.") from exc

    if len(crus) > config.facial_tamanho_maximo_bytes:
        raise _erro(
            CODIGO_TAMANHO_EXCEDIDO,
            f"Imagem acima de {config.facial_tamanho_maximo_bytes} bytes.",
        )
    if not crus:
        raise _erro(CODIGO_CORPO_INVALIDO, "Campo de imagem vazio.")

    matriz = cv2.imdecode(np.frombuffer(crus, dtype=np.uint8), cv2.IMREAD_COLOR)
    if matriz is None:
        raise _erro(
            CODIGO_CORPO_INVALIDO,
            "Nao foi possivel decodificar a imagem. Confira se os bytes "
            "correspondem ao mimeType declarado.",
        )

    altura, largura = matriz.shape[:2]
    if min(altura, largura) < LADO_MINIMO_PX:
        raise _erro(
            CODIGO_CORPO_INVALIDO,
            f"Imagem menor que {LADO_MINIMO_PX} px no menor lado.",
        )

    maior = max(altura, largura)
    if maior > LADO_MAXIMO_PX:
        # Reducao proporcional: o detector trabalha em 640 px, e imagem de 8000 px
        # so multiplica o custo de CPU sem melhorar o reconhecimento.
        fator = LADO_MAXIMO_PX / maior
        matriz = cv2.resize(
            matriz,
            (max(1, int(largura * fator)), max(1, int(altura * fator))),
            interpolation=cv2.INTER_AREA,
        )

    # O log registra so a forma, nunca conteudo. Serve para responder "as capturas
    # estao chegando minusculas?" sem tocar em biometria.
    logger.debug("imagem decodificada", extra={"mimeType": mime_type})
    return np.ascontiguousarray(matriz, dtype=np.uint8)
