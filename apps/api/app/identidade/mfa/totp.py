"""TOTP (RFC 6238) para segundo fator.

O segredo fica cifrado em repouso (`app.identidade.mfa.cifra`). O anti-replay
usa a coluna `mfa_dispositivos.contador` (pensada no contrato para o contador
do WebAuthn, mas documentada aqui para o mesmo papel generico de "marca d'agua
anti-reuso"): guarda o numero do PASSO de 30 segundos ja aceito, e nenhum
passo igual ou anterior a ele volta a ser aceito -- e o que impede que o
mesmo codigo TOTP sirva duas vezes mesmo dentro da janela de tolerancia.
"""

from __future__ import annotations

import datetime as _dt
import hmac
from typing import Final

import pyotp

JANELA_SEGUNDOS: Final[int] = 30
#: Tolerancia de relogio: aceita o passo anterior e o seguinte ao corrente.
JANELAS_TOLERANCIA: Final[int] = 1


def gerar_segredo() -> str:
    """Segredo TOTP em Base32, 160 bits (RFC 4226 recomenda >= 128 bits)."""
    return pyotp.random_base32(length=32)


def gerar_uri_provisionamento(
    segredo_base32: str, *, email: str, emissor: str = "Ponto Eletronico"
) -> str:
    """URI `otpauth://` para QR code no app autenticador."""
    return pyotp.TOTP(segredo_base32, interval=JANELA_SEGUNDOS).provisioning_uri(
        name=email, issuer_name=emissor
    )


def passo_atual(instante: _dt.datetime) -> int:
    return int(instante.timestamp() // JANELA_SEGUNDOS)


def verificar_codigo(
    segredo_base32: str,
    codigo: str,
    *,
    ultimo_passo_aceito: int | None,
    agora: _dt.datetime | None = None,
) -> int | None:
    """Verifica o codigo TOTP contra a janela corrente +/- tolerancia.

    Devolve o numero do passo aceito (para o chamador gravar em
    `mfa_dispositivos.contador`), ou `None` quando o codigo nao confere ou
    corresponde a um passo ja usado (`<= ultimo_passo_aceito`).
    """
    if not codigo:
        return None
    agora = agora or _dt.datetime.now(_dt.UTC)
    totp = pyotp.TOTP(segredo_base32, interval=JANELA_SEGUNDOS)
    passo = passo_atual(agora)
    candidatos = range(passo + JANELAS_TOLERANCIA, passo - JANELAS_TOLERANCIA - 1, -1)
    for candidato in candidatos:
        if ultimo_passo_aceito is not None and candidato <= ultimo_passo_aceito:
            continue
        offset = candidato - passo
        esperado = totp.at(agora, counter_offset=offset)
        if hmac.compare_digest(esperado, codigo.strip()):
            return candidato
    return None
