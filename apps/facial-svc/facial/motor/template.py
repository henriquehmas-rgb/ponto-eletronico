"""Serializacao do embedding e similaridade de cosseno.

Formato do template
-------------------

`base64( float32 little-endian x N )`, com `N = 512` para o reconhecedor
`w600k_r50` do pacote `buffalo_l`. Sao 2048 bytes crus, ~2732 caracteres em
base64.

A escolha e deliberada e vale explicar, porque quem recebe o template e
`apps/api`, que o cifra e grava em `biometria_templates.template_cifrado`
(`BYTEA`):

* **float32, e nao float64.** ArcFace nao produz precisao alem de float32; o
  dobro de bytes nao acrescenta um digito util de similaridade.
* **little-endian explicito** (`<f4`). O default do numpy e a ordem da maquina.
  Um template gravado num x86 e lido num ARM viraria ruido silencioso — o pior
  tipo de defeito possivel numa base biometrica.
* **base64, e nao JSON de numeros.** Uma lista JSON de 512 floats ocupa ~4x mais
  e depende de arredondamento de serializador para ida e volta exata.
* **sem cabecalho proprio.** A versao do modelo viaja no campo `modeloVersao` da
  resposta e e gravada em `biometria_templates.versao_modelo`. Duplicar o carimbo
  dentro do blob criaria duas fontes da verdade que podem divergir.

O vetor sai daqui apenas no corpo da resposta HTTP. **Nunca em log** (ADR-006).

Similaridade
------------

Os embeddings sao L2-normalizados, entao o produto interno **e** a similaridade
de cosseno, em [-1, 1]. Nao ha divisao por norma no caminho quente.
"""

from __future__ import annotations

import base64
import binascii
from typing import Any

import numpy as np

from facial.erros import ErroDeAplicacao

#: Dimensao do embedding do reconhecedor `w600k_r50` (ArcFace, ResNet50 @ WebFace600K).
DIMENSAO_EMBEDDING = 512

_DTYPE = np.dtype("<f4")


def serializar_template(embedding: np.ndarray[Any, np.dtype[np.floating[Any]]]) -> str:
    """Vetor normalizado -> string base64. Renormaliza por seguranca."""
    vetor = np.asarray(embedding, dtype=np.float32).ravel()
    norma = float(np.linalg.norm(vetor))
    if norma <= 0.0 or not np.isfinite(norma):
        raise ErroDeAplicacao(
            "PONTO-INT-001",
            contexto_log={"etapa": "serializacao", "motivo": "norma invalida"},
        )
    return base64.b64encode((vetor / norma).astype(_DTYPE).tobytes()).decode("ascii")


def desserializar_template(
    template: str, *, indice: int | None = None
) -> np.ndarray[Any, np.dtype[np.float32]]:
    """Base64 -> vetor normalizado `float32`.

    Template malformado e **erro do chamador** (`PONTO-VAL-001`), nao erro
    interno: quem manda template e a API, com um blob que ela mesma decifrou, e
    um blob de tamanho errado significa base corrompida ou versao trocada —
    situacao que precisa aparecer, nao ser tolerada.
    """
    onde = "templates[?]" if indice is None else f"templates[{indice}]"
    try:
        crus = base64.b64decode(template, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ErroDeAplicacao(
            "PONTO-VAL-001",
            detalhe=f"{onde} nao e base64 valido.",
            contexto_log={"etapa": "desserializacao"},
        ) from exc

    esperado = DIMENSAO_EMBEDDING * _DTYPE.itemsize
    if len(crus) != esperado:
        raise ErroDeAplicacao(
            "PONTO-VAL-001",
            detalhe=(
                f"{onde} tem {len(crus)} bytes; o esperado sao {esperado} "
                f"({DIMENSAO_EMBEDDING} float32). Confira `modeloVersao`."
            ),
            contexto_log={"etapa": "desserializacao"},
        )

    vetor = np.frombuffer(crus, dtype=_DTYPE).astype(np.float32)
    norma = float(np.linalg.norm(vetor))
    if not np.isfinite(norma) or norma <= 0.0:
        raise ErroDeAplicacao(
            "PONTO-VAL-001",
            detalhe=f"{onde} nao e um vetor valido.",
            contexto_log={"etapa": "desserializacao"},
        )
    return (vetor / norma).astype(np.float32)


def similaridade_cosseno(
    a: np.ndarray[Any, np.dtype[np.floating[Any]]],
    b: np.ndarray[Any, np.dtype[np.floating[Any]]],
) -> float:
    """Similaridade de cosseno entre dois vetores normalizados, em [-1, 1]."""
    return float(np.clip(np.dot(np.asarray(a, np.float32), np.asarray(b, np.float32)), -1.0, 1.0))


def melhor_correspondencia(
    candidato: np.ndarray[Any, np.dtype[np.floating[Any]]],
    referencias: list[np.ndarray[Any, np.dtype[np.float32]]],
) -> tuple[int, float]:
    """Devolve `(indice, similaridade)` da referencia mais parecida.

    Comparar contra **todos** os templates e devolver o melhor, em vez de parar
    no primeiro que passa, e o que evita o falso negativo mais comum do sistema:
    o colaborador com dois enrollments validos (recadastro apos mudanca de
    aparencia, cadastro pelo app e pelo terminal) cuja captura de hoje se parece
    mais com o segundo.
    """
    if not referencias:
        raise ErroDeAplicacao(
            "PONTO-VAL-001",
            detalhe="A lista `templates` esta vazia.",
            contexto_log={"etapa": "comparacao"},
        )
    matriz = np.vstack(referencias).astype(np.float32)
    escores = matriz @ np.asarray(candidato, np.float32)
    indice = int(np.argmax(escores))
    return indice, float(np.clip(escores[indice], -1.0, 1.0))
