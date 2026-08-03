"""Eventos de domínio `ajuste.aprovado`, `ajuste.reprovado` e
`apuracao.recalculada` -- barramento interno do domínio `tratamento`.

Envelope e *payload* idênticos, campo a campo, ao declarado em
`packages/contracts/events.yaml`. A entrega por webhook é da F13; esta fase
só publica no barramento interno e prova por teste que o corpo bate com o
contrato. Mesmo padrão replicado por F2/F3/F5 (`app.pessoas.eventos`,
`app.marcacao.eventos`, ...): barramento em memória mais um `logger.info`,
nunca importado de outra fase -- cada domínio tem o seu próprio.
"""

from __future__ import annotations

import datetime as dt
from typing import Any
from uuid import UUID, uuid4

from app.core.log import obter_logger

logger = obter_logger("apuracao.tratamento.eventos")

NOME_AJUSTE_APROVADO = "ajuste.aprovado"
NOME_AJUSTE_REPROVADO = "ajuste.reprovado"
NOME_APURACAO_RECALCULADA = "apuracao.recalculada"

VERSAO_AJUSTE_APROVADO = 1
VERSAO_AJUSTE_REPROVADO = 1
VERSAO_APURACAO_RECALCULADA = 1

#: Barramento interno do domínio: cada envelope publicado fica aqui, na
#: ordem de publicação. Só para prova por teste e depuração local -- a F13
#: substitui por fila de verdade sem mudar a assinatura de `publicar`.
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


def publicar_ajuste_aprovado(
    *,
    tenant_id: UUID,
    solicitacao_id: UUID,
    protocolo: str,
    colaborador_id: UUID,
    data_referencia: dt.date,
    tratamento_id: UUID,
    decidido_em: dt.datetime,
    vinculo_id: UUID | None = None,
    aprovador_usuario_id: UUID | None = None,
    por_delegacao: bool | None = None,
    comentario: str | None = None,
) -> dict[str, Any]:
    """Publica `ajuste.aprovado`. Só chamado quando `tratamentos.solicitacao_id`
    não é nulo (payload exige `solicitacaoId`/`protocolo`, ambos vindos da
    `solicitacoes` de workflow referenciada, F10 -- FK apenas)."""
    dados: dict[str, Any] = {
        "solicitacaoId": str(solicitacao_id),
        "protocolo": protocolo,
        "colaboradorId": str(colaborador_id),
        "dataReferencia": data_referencia.isoformat(),
        "tratamentoId": str(tratamento_id),
        "decididoEm": decidido_em.isoformat(),
    }
    if vinculo_id is not None:
        dados["vinculoId"] = str(vinculo_id)
    if aprovador_usuario_id is not None:
        dados["aprovadorUsuarioId"] = str(aprovador_usuario_id)
    if por_delegacao is not None:
        dados["porDelegacao"] = por_delegacao
    if comentario is not None:
        dados["comentario"] = comentario
    envelope = montar_envelope(
        tipo=NOME_AJUSTE_APROVADO,
        versao=VERSAO_AJUSTE_APROVADO,
        tenant_id=tenant_id,
        dados=dados,
    )
    publicar(envelope)
    return envelope


def publicar_ajuste_reprovado(
    *,
    tenant_id: UUID,
    solicitacao_id: UUID,
    protocolo: str,
    colaborador_id: UUID,
    data_referencia: dt.date,
    decidido_em: dt.datetime,
    motivo: str,
    etapa: int | None = None,
    aprovador_usuario_id: UUID | None = None,
) -> dict[str, Any]:
    """Publica `ajuste.reprovado`. Só chamado quando `tratamentos.solicitacao_id`
    não é nulo."""
    dados: dict[str, Any] = {
        "solicitacaoId": str(solicitacao_id),
        "protocolo": protocolo,
        "colaboradorId": str(colaborador_id),
        "dataReferencia": data_referencia.isoformat(),
        "decididoEm": decidido_em.isoformat(),
        "motivo": motivo,
    }
    if etapa is not None:
        dados["etapa"] = etapa
    if aprovador_usuario_id is not None:
        dados["aprovadorUsuarioId"] = str(aprovador_usuario_id)
    envelope = montar_envelope(
        tipo=NOME_AJUSTE_REPROVADO,
        versao=VERSAO_AJUSTE_REPROVADO,
        tenant_id=tenant_id,
        dados=dados,
    )
    publicar(envelope)
    return envelope


def publicar_apuracao_recalculada(
    *,
    tenant_id: UUID,
    vinculo_id: UUID,
    colaborador_id: UUID,
    data_inicio: dt.date,
    data_fim: dt.date,
    dias_alterados: int,
    motivo: str,
    recalculo_id: UUID | None = None,
    saldo_anterior_minutos: int | None = None,
    saldo_novo_minutos: int | None = None,
) -> dict[str, Any]:
    """Publica `apuracao.recalculada`. Só chamado quando `diasAlterados > 0`
    (recálculo sem mudança efetiva NAO dispara evento -- `events.yaml`)."""
    dados: dict[str, Any] = {
        "vinculoId": str(vinculo_id),
        "colaboradorId": str(colaborador_id),
        "dataInicio": data_inicio.isoformat(),
        "dataFim": data_fim.isoformat(),
        "diasAlterados": dias_alterados,
        "motivo": motivo,
    }
    if recalculo_id is not None:
        dados["recalculoId"] = str(recalculo_id)
    if saldo_anterior_minutos is not None:
        dados["saldoAnteriorMinutos"] = saldo_anterior_minutos
    if saldo_novo_minutos is not None:
        dados["saldoNovoMinutos"] = saldo_novo_minutos
    envelope = montar_envelope(
        tipo=NOME_APURACAO_RECALCULADA,
        versao=VERSAO_APURACAO_RECALCULADA,
        tenant_id=tenant_id,
        dados=dados,
    )
    publicar(envelope)
    return envelope
