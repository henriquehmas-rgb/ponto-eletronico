"""Bloqueio progressivo de credencial apos falhas consecutivas.

Politica (documentada aqui porque o verificador e o gravador do bloqueio
precisam concordar para sempre, o mesmo motivo pelo qual a formula do hash de
auditoria e fixada em codigo):

* As primeiras `LIMITE_TENTATIVAS_LIVRES` falhas nao bloqueiam nada, apenas
  incrementam `credenciais.tentativas_falhas`.
* A partir da falha seguinte, o bloqueio dobra a cada nova falha:
  1, 2, 4, 8, 16, 32 minutos, com teto em `TETO_MINUTOS`.
* `credenciais.bloqueado_ate` guarda o instante de liberacao. Uma tentativa
  antes desse instante responde `PONTO-AUTH-009` (423) sem sequer olhar a
  senha -- inclusive para a senha correta, porque o bloqueio e por tempo, nao
  por acerto.
"""

from __future__ import annotations

import datetime as _dt

LIMITE_TENTATIVAS_LIVRES = 5
TETO_MINUTOS = 60


def calcular_bloqueado_ate(tentativas_falhas: int, agora: _dt.datetime) -> _dt.datetime | None:
    """Devolve o instante de liberacao do bloqueio, ou `None` se ainda nao bloqueou.

    `tentativas_falhas` e o contador JA incrementado com a falha corrente.
    """
    excedente = tentativas_falhas - LIMITE_TENTATIVAS_LIVRES
    if excedente <= 0:
        return None
    minutos = min(2 ** (excedente - 1), TETO_MINUTOS)
    return agora + _dt.timedelta(minutes=minutos)


def bloqueado(bloqueado_ate: _dt.datetime | None, agora: _dt.datetime) -> bool:
    """Verdadeiro se a credencial ainda esta dentro da janela de bloqueio."""
    return bloqueado_ate is not None and agora < bloqueado_ate
