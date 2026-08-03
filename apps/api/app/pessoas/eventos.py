"""Eventos de dominio `colaborador.admitido` e `colaborador.demitido`.

Envelope e *payload* identicos, campo a campo, ao declarado em
`packages/contracts/events.yaml`. A entrega por webhook -- assinatura HMAC,
retentativa exponencial, *dead letter queue*, painel -- e da F13; esta fase
so publica no barramento interno e prova por teste que o corpo bate com o
contrato.

O "barramento interno" desta fase e deliberadamente simples: uma lista em
memoria mais um `logger.info`. Nao existe ainda, no andaime, nenhuma fila real
de eventos de dominio (o worker so conhece filas de *tarefa* ARQ, um conceito
diferente) -- criar essa infraestrutura definitiva e do escopo da F13
(entrega de webhook). Ate la, este modulo e o unico produtor e o unico
consumidor: publica, guarda para o teste inspecionar, e loga a correlacao.
"""

from __future__ import annotations

import datetime as dt
from typing import Any
from uuid import UUID, uuid4

from app.core.log import obter_logger

logger = obter_logger("pessoas.eventos")

NOME_COLABORADOR_ADMITIDO = "colaborador.admitido"
NOME_COLABORADOR_DEMITIDO = "colaborador.demitido"

VERSAO_COLABORADOR_ADMITIDO = 1
VERSAO_COLABORADOR_DEMITIDO = 1

#: Barramento interno da fase: cada envelope publicado fica aqui, na ordem de
#: publicacao. So para prova por teste e depuracao local -- a F13 substitui
#: por fila de verdade sem mudar a assinatura de `publicar`.
BARRAMENTO_INTERNO: list[dict[str, Any]] = []


def limpar_barramento() -> None:
    """Esvazia o barramento interno. Uso exclusivo de teste, entre casos."""
    BARRAMENTO_INTERNO.clear()


def montar_envelope(
    *,
    tipo: str,
    versao: int,
    tenant_id: UUID,
    dados: dict[str, Any],
    empresa_id: UUID | None = None,
    ocorrido_em: dt.datetime | None = None,
) -> dict[str, Any]:
    """Monta o envelope exato de `events.yaml`: id, tipo, versao, ocorridoEm,
    tenantId, dados -- os cinco campos `required`, mais os opcionais
    `publicadoEm` e `empresaId`."""
    agora = dt.datetime.now(tz=dt.UTC)
    envelope: dict[str, Any] = {
        "id": str(uuid4()),
        "tipo": tipo,
        "versao": versao,
        "ocorridoEm": (ocorrido_em or agora).isoformat(),
        "publicadoEm": agora.isoformat(),
        "tenantId": str(tenant_id),
        "dados": dados,
    }
    if empresa_id is not None:
        envelope["empresaId"] = str(empresa_id)
    return envelope


def publicar(envelope: dict[str, Any]) -> None:
    """Publica um envelope no barramento interno.

    F13/A3, T11 -- aditivo, corpo desta funcao e o UNICO ponto que A3 toca
    neste arquivo (PCF F13 secao 5.2/5.4): alem do `BARRAMENTO_INTERNO.
    append` acima (nome/assinatura/comportamento inalterados -- os testes
    desta fase dependem disso), registra o envelope para fan-out
    transacionalmente seguro em `webhook_entregas`. `registrar_pendente`
    NUNCA levanta excecao e so grava a linha durável depois que a
    transacao corrente (que chamou `publicar`) commitar de verdade -- ver
    `app.integracoes.webhooks.fan_out` para a costura completa."""
    BARRAMENTO_INTERNO.append(envelope)
    logger.info(
        "evento de dominio publicado",
        extra={"tipo": envelope["tipo"], "id": envelope["id"], "tenantId": envelope["tenantId"]},
    )
    from app.integracoes.webhooks.fan_out import registrar_pendente

    registrar_pendente(envelope)


def publicar_colaborador_admitido(
    *,
    tenant_id: UUID,
    colaborador_id: UUID,
    vinculo_id: UUID,
    empresa_id: UUID,
    matricula: str,
    cpf: str,
    data_inicio: dt.date,
    unidade_id: UUID | None = None,
    matricula_esocial: str | None = None,
    nome_completo: str | None = None,
    cargo_id: UUID | None = None,
    apura_ponto: bool | None = None,
) -> dict[str, Any]:
    """Publica `colaborador.admitido` com os `required` de `events.yaml`
    preenchidos: colaboradorId, vinculoId, empresaId, matricula, cpf,
    dataInicio."""
    dados: dict[str, Any] = {
        "colaboradorId": str(colaborador_id),
        "vinculoId": str(vinculo_id),
        "empresaId": str(empresa_id),
        "matricula": matricula,
        "cpf": cpf,
        "dataInicio": data_inicio.isoformat(),
    }
    if unidade_id is not None:
        dados["unidadeId"] = str(unidade_id)
    if matricula_esocial is not None:
        dados["matriculaEsocial"] = matricula_esocial
    if nome_completo is not None:
        dados["nomeCompleto"] = nome_completo
    if cargo_id is not None:
        dados["cargoId"] = str(cargo_id)
    if apura_ponto is not None:
        dados["apuraPonto"] = apura_ponto
    envelope = montar_envelope(
        tipo=NOME_COLABORADOR_ADMITIDO,
        versao=VERSAO_COLABORADOR_ADMITIDO,
        tenant_id=tenant_id,
        empresa_id=empresa_id,
        dados=dados,
    )
    publicar(envelope)
    return envelope


def publicar_colaborador_demitido(
    *,
    tenant_id: UUID,
    colaborador_id: UUID,
    vinculo_id: UUID,
    empresa_id: UUID,
    data_fim: dt.date,
    matricula: str | None = None,
    motivo_desligamento: str | None = None,
    saldo_banco_minutos: int | None = None,
    possui_pendencias: bool | None = None,
) -> dict[str, Any]:
    """Publica `colaborador.demitido` com os `required` de `events.yaml`
    preenchidos: colaboradorId, vinculoId, empresaId, dataFim."""
    dados: dict[str, Any] = {
        "colaboradorId": str(colaborador_id),
        "vinculoId": str(vinculo_id),
        "empresaId": str(empresa_id),
        "dataFim": data_fim.isoformat(),
    }
    if matricula is not None:
        dados["matricula"] = matricula
    if motivo_desligamento is not None:
        dados["motivoDesligamento"] = motivo_desligamento
    if saldo_banco_minutos is not None:
        dados["saldoBancoMinutos"] = saldo_banco_minutos
    if possui_pendencias is not None:
        dados["possuiPendencias"] = possui_pendencias
    envelope = montar_envelope(
        tipo=NOME_COLABORADOR_DEMITIDO,
        versao=VERSAO_COLABORADOR_DEMITIDO,
        tenant_id=tenant_id,
        empresa_id=empresa_id,
        dados=dados,
    )
    publicar(envelope)
    return envelope
