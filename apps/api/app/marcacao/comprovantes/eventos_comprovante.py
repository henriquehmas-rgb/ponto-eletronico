"""Publicacao do evento `comprovante.emitido` no barramento interno da fase.

Payload identico, campo a campo, ao declarado em `packages/contracts/events.yaml`
(evento `comprovante.emitido`, versao 1, `webhook_publico: false` -- e um
evento interno, redundante com `marcacao.criada` que ja traz
`comprovanteId`, usado pela interface e pela fila de notificacao push, nao
para integracao externa). A entrega por webhook real (assinatura HMAC,
retentativa, DLQ) e da F13; aqui so publicamos no barramento interno de
`app.marcacao.eventos` e provamos por teste que o payload bate com o
contrato.

Publicado pela pipeline de ingestao (`app.marcacao.pipeline.ingestao`, A2),
na MESMA transacao da marcacao, logo apos `emitir_comprovante` (T8) --
`emitir_comprovante` so grava a linha em `comprovantes`; quem publica o
evento e sempre o chamador, para nao publicar duas vezes quando o
comprovante e emitido por outro caminho no futuro (ex.: catch-up de F6).
"""

from __future__ import annotations

import datetime as dt
from typing import Any
from uuid import UUID

from app.marcacao.eventos import montar_envelope, publicar

NOME_COMPROVANTE_EMITIDO = "comprovante.emitido"
VERSAO_COMPROVANTE_EMITIDO = 1


def publicar_comprovante_emitido(
    *,
    tenant_id: UUID,
    comprovante_id: UUID,
    marcacao_id: UUID,
    colaborador_id: UUID,
    numero: str,
    nsr: int,
    emitido_em: dt.datetime,
    hash_sha256: str,
    canal_entrega: str | None = None,
) -> dict[str, Any]:
    """Publica `comprovante.emitido` com os `required` de `events.yaml`
    preenchidos: comprovanteId, marcacaoId, colaboradorId, numero, nsr,
    emitidoEm, hashSha256. `ocorridoEm` do envelope usa o proprio instante da
    emissao (nao ha um instante de "fato" separado, diferente de
    `marcacao.criada`)."""
    dados: dict[str, Any] = {
        "comprovanteId": str(comprovante_id),
        "marcacaoId": str(marcacao_id),
        "colaboradorId": str(colaborador_id),
        "numero": numero,
        "nsr": nsr,
        "emitidoEm": emitido_em.isoformat(),
        "hashSha256": hash_sha256,
    }
    if canal_entrega is not None:
        dados["canalEntrega"] = canal_entrega
    envelope = montar_envelope(
        tipo=NOME_COMPROVANTE_EMITIDO,
        versao=VERSAO_COMPROVANTE_EMITIDO,
        tenant_id=tenant_id,
        ocorrido_em=emitido_em,
        dados=dados,
    )
    publicar(envelope)
    return envelope
