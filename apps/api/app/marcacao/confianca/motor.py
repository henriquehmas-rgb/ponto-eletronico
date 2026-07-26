"""Motor de score de confianca do registro de ponto. CONTRATO ENTRE FASES.

A assinatura publica de `avaliar_confianca` esta fixada neste PCF (F5) e NAO
muda sem RFC. A implementacao real -- composicao ponderada de attestation,
RASP, modo desenvolvedor, mock location, coerencia geografica, velocidade
implicita e reputacao do dispositivo -- e da F14. Ate la, o corpo abaixo e
permissivo por design: NUNCA reprova, NUNCA pede revisao. Isso significa que
PONTO-SCORE-001..004, PONTO-GEO-003 e PONTO-DISP-003/004/005 ficam com o
codigo ligado (o chamador sabe levantar o erro) mas nunca sao alcancados na
pratica por esta fase -- comportamento esperado, nao lacuna.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class SinaisRegistro:
    """Sinais brutos coletados no momento do registro, tal como informados
    pelo cliente (nenhum e verificado criptograficamente nesta fase)."""

    dentro_geocerca: bool | None = None
    distancia_geocerca_metros: float | None = None
    precisao_insuficiente: bool = False
    score_facial: float | None = None
    liveness_aprovado: bool | None = None
    attestation_veredito: str = "indisponivel"
    root_detectado: bool | None = None
    emulador_detectado: bool | None = None
    modo_desenvolvedor: bool | None = None
    mock_location: bool | None = None
    camera_virtual: bool | None = None
    velocidade_desde_ultima_kmh: float | None = None
    flags_integridade: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ResultadoConfianca:
    """Resultado da avaliacao. `avisos` alimenta `MarcacaoCriada.avisos` e
    `marcacao.suspeita.sinais`."""

    score: int = 100
    classificacao: str = "alta"
    avisos: tuple[str, ...] = ()


def avaliar_confianca(
    sinais: SinaisRegistro,
    *,
    limiar_bloqueio: int,
    limiar_revisao: int,
) -> ResultadoConfianca:
    """STUB permissivo. A F14 substitui o corpo sem mudar a assinatura.

    `limiar_bloqueio`/`limiar_revisao` vem de `politicas_registro` e ja sao
    recebidos aqui para que a F14 nao precise mudar quem chama esta funcao --
    so o corpo, que hoje os ignora de proposito.
    """
    return ResultadoConfianca(score=100, classificacao="alta", avisos=())
