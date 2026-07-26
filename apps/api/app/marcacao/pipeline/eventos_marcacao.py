"""Publicacao dos eventos de dominio do pipeline de ingestao (F5, A2).

Usa `app.marcacao.eventos.montar_envelope`/`publicar` (criado por A1 na T1;
ninguem acrescenta funcao naquele arquivo). Os tres eventos daqui --
``marcacao.criada``, ``marcacao.suspeita`` e ``marcacao.sincronizada_offline``
-- tem *payload* fixado por `packages/contracts/events.yaml`; os campos
`required` de cada um estao sempre presentes, os opcionais so quando o
chamador informa um valor.

``comprovante.emitido`` NAO mora aqui: e publicado por
`app.marcacao.comprovantes.eventos_comprovante` (A3, T8). O pipeline de
ingestao (`ingestao.py`) chama a funcao publica de A3 depois de emitir o
comprovante, mas nao duplica a definicao do evento neste modulo.
"""

from __future__ import annotations

import datetime as dt
from typing import Any
from uuid import UUID

from app.marcacao.eventos import montar_envelope, publicar

NOME_MARCACAO_CRIADA = "marcacao.criada"
NOME_MARCACAO_SUSPEITA = "marcacao.suspeita"
NOME_MARCACAO_SINCRONIZADA_OFFLINE = "marcacao.sincronizada_offline"

VERSAO_MARCACAO_CRIADA = 1
VERSAO_MARCACAO_SUSPEITA = 1
VERSAO_MARCACAO_SINCRONIZADA_OFFLINE = 1


def publicar_marcacao_criada(
    *,
    tenant_id: UUID,
    marcacao_id: UUID,
    colaborador_id: UUID,
    cpf: str,
    nsr: int,
    datahora_marcacao: dt.datetime,
    canal: str,
    rep_p_id: UUID,
    empresa_id: UUID | None = None,
    vinculo_id: UUID | None = None,
    matricula: str | None = None,
    unidade_id: UUID | None = None,
    datahora_gravacao: dt.datetime | None = None,
    coletada_offline: bool | None = None,
    comprovante_id: UUID | None = None,
    hash_registro: str | None = None,
) -> dict[str, Any]:
    """Publica `marcacao.criada` com os `required` de `events.yaml`
    preenchidos: marcacaoId, colaboradorId, cpf, nsr, datahoraMarcacao, canal,
    repPId."""
    dados: dict[str, Any] = {
        "marcacaoId": str(marcacao_id),
        "colaboradorId": str(colaborador_id),
        "cpf": cpf,
        "nsr": nsr,
        "datahoraMarcacao": datahora_marcacao.isoformat(),
        "canal": canal,
        "repPId": str(rep_p_id),
    }
    if vinculo_id is not None:
        dados["vinculoId"] = str(vinculo_id)
    if matricula is not None:
        dados["matricula"] = matricula
    if unidade_id is not None:
        dados["unidadeId"] = str(unidade_id)
    if datahora_gravacao is not None:
        dados["datahoraGravacao"] = datahora_gravacao.isoformat()
    if coletada_offline is not None:
        dados["coletadaOffline"] = coletada_offline
    if comprovante_id is not None:
        dados["comprovanteId"] = str(comprovante_id)
    if hash_registro is not None:
        dados["hashRegistro"] = hash_registro
    envelope = montar_envelope(
        tipo=NOME_MARCACAO_CRIADA,
        versao=VERSAO_MARCACAO_CRIADA,
        tenant_id=tenant_id,
        empresa_id=empresa_id,
        ocorrido_em=datahora_marcacao,
        dados=dados,
    )
    publicar(envelope)
    return envelope


def publicar_marcacao_suspeita(
    *,
    tenant_id: UUID,
    marcacao_id: UUID,
    colaborador_id: UUID,
    score_confianca: int,
    classificacao: str,
    sinais: list[str],
    empresa_id: UUID | None = None,
    nsr: int | None = None,
    canal: str | None = None,
    revisao_status: str | None = None,
) -> dict[str, Any]:
    """Publica `marcacao.suspeita` com os `required` de `events.yaml`
    preenchidos: marcacaoId, colaboradorId, scoreConfianca, classificacao,
    sinais. Com o motor de confianca stub desta fase (sempre `score=100`,
    `classificacao="alta"`), esta funcao esta conectada mas NUNCA e chamada na
    pratica -- ver `app.marcacao.confianca.motor`."""
    dados: dict[str, Any] = {
        "marcacaoId": str(marcacao_id),
        "colaboradorId": str(colaborador_id),
        "scoreConfianca": score_confianca,
        "classificacao": classificacao,
        "sinais": list(sinais),
    }
    if nsr is not None:
        dados["nsr"] = nsr
    if canal is not None:
        dados["canal"] = canal
    if revisao_status is not None:
        dados["revisaoStatus"] = revisao_status
    envelope = montar_envelope(
        tipo=NOME_MARCACAO_SUSPEITA,
        versao=VERSAO_MARCACAO_SUSPEITA,
        tenant_id=tenant_id,
        empresa_id=empresa_id,
        dados=dados,
    )
    publicar(envelope)
    return envelope


def publicar_marcacao_sincronizada_offline(
    *,
    tenant_id: UUID,
    marcacao_id: UUID,
    fila_offline_id: UUID,
    colaborador_id: UUID,
    datahora_marcacao: dt.datetime,
    atraso_minutos: int,
    empresa_id: UUID | None = None,
    dispositivo_id: UUID | None = None,
    datahora_dispositivo: dt.datetime | None = None,
    recebido_em: dt.datetime | None = None,
    confianca_temporal: str | None = None,
) -> dict[str, Any]:
    """Publica `marcacao.sincronizada_offline` com os `required` de
    `events.yaml` preenchidos: marcacaoId, filaOfflineId, colaboradorId,
    datahoraMarcacao, atrasoMinutos."""
    dados: dict[str, Any] = {
        "marcacaoId": str(marcacao_id),
        "filaOfflineId": str(fila_offline_id),
        "colaboradorId": str(colaborador_id),
        "datahoraMarcacao": datahora_marcacao.isoformat(),
        "atrasoMinutos": atraso_minutos,
    }
    if dispositivo_id is not None:
        dados["dispositivoId"] = str(dispositivo_id)
    if datahora_dispositivo is not None:
        dados["datahoraDispositivo"] = datahora_dispositivo.isoformat()
    if recebido_em is not None:
        dados["recebidoEm"] = recebido_em.isoformat()
    if confianca_temporal is not None:
        dados["confiancaTemporal"] = confianca_temporal
    envelope = montar_envelope(
        tipo=NOME_MARCACAO_SINCRONIZADA_OFFLINE,
        versao=VERSAO_MARCACAO_SINCRONIZADA_OFFLINE,
        tenant_id=tenant_id,
        empresa_id=empresa_id,
        ocorrido_em=recebido_em,
        dados=dados,
    )
    publicar(envelope)
    return envelope
