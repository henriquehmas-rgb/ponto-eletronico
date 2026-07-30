"""Eventos de domínio `periodo.fechado`, `periodo.reaberto` e
`espelho.assinado` -- barramento interno do domínio `fechamento` (F10/A2).

Envelope e *payload* idênticos, campo a campo, ao declarado em
`packages/contracts/events.yaml`. A entrega por webhook é da F13; esta fase
só publica no barramento interno e prova por teste que o corpo bate com o
contrato. Mesmo padrão replicado por F2-F5/F4 (`app.pessoas.eventos`,
`app.marcacao.eventos`, `app.apuracao.tratamento.eventos`, ...): barramento
em memória mais um `logger.info`, nunca importado de outra fase -- cada
domínio tem o seu próprio (PCF F10 §4: "crie seu próprio módulo
`app/workflow/fechamento/eventos.py`").
"""

from __future__ import annotations

import datetime as dt
from typing import Any
from uuid import UUID, uuid4

from app.core.log import obter_logger

logger = obter_logger("workflow.fechamento.eventos")

NOME_PERIODO_FECHADO = "periodo.fechado"
NOME_PERIODO_REABERTO = "periodo.reaberto"
NOME_ESPELHO_ASSINADO = "espelho.assinado"

VERSAO_PERIODO_FECHADO = 1
VERSAO_PERIODO_REABERTO = 1
VERSAO_ESPELHO_ASSINADO = 1

#: `assinaturas_espelho.metodo` (banco, snake_case) -> `espelho.assinado.
#: payload.metodo` (contrato, camelCase) -- divergência literal do próprio
#: `events.yaml` (enum `[aceiteEletronico, icpBrasil, biometria, senha,
#: tokenEmail]`), não um erro deste módulo.
_METODO_PARA_EVENTO: dict[str, str] = {
    "aceite_eletronico": "aceiteEletronico",
    "icp_brasil": "icpBrasil",
    "biometria": "biometria",
    "senha": "senha",
    "token_email": "tokenEmail",
}

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
    `publicadoEm` e `empresaId`. Mesma forma que `app.apuracao.tratamento.
    eventos.montar_envelope`, cópia própria (nunca importada de outra fase)."""
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
    """Publica um envelope no barramento interno."""
    BARRAMENTO_INTERNO.append(envelope)
    logger.info(
        "evento de dominio publicado",
        extra={"tipo": envelope["tipo"], "id": envelope["id"], "tenantId": envelope["tenantId"]},
    )


def publicar_periodo_fechado(
    *,
    tenant_id: UUID,
    fechamento_id: UUID,
    periodo_id: UUID,
    empresa_id: UUID,
    escopo: str,
    data_inicio: dt.date,
    data_fim: dt.date,
    fechado_em: dt.datetime,
    competencia_folha: str | None = None,
    total_colaboradores: int | None = None,
    total_pendencias: int | None = None,
    fechado_por: UUID | None = None,
    hash_conteudo: str | None = None,
) -> dict[str, Any]:
    """Publica `periodo.fechado`. Disparado na conclusão do fechamento
    (`events.yaml`: "depois de gerados os espelhos do escopo") -- ou seja,
    pela tarefa assíncrona `processar_fechamento` (T9), nunca por
    `criarFechamento` em si, que só enfileira."""
    dados: dict[str, Any] = {
        "fechamentoId": str(fechamento_id),
        "periodoId": str(periodo_id),
        "empresaId": str(empresa_id),
        "escopo": escopo,
        "dataInicio": data_inicio.isoformat(),
        "dataFim": data_fim.isoformat(),
        "fechadoEm": fechado_em.isoformat(),
    }
    if competencia_folha is not None:
        dados["competenciaFolha"] = competencia_folha
    if total_colaboradores is not None:
        dados["totalColaboradores"] = total_colaboradores
    if total_pendencias is not None:
        dados["totalPendencias"] = total_pendencias
    if fechado_por is not None:
        dados["fechadoPor"] = str(fechado_por)
    if hash_conteudo is not None:
        dados["hashConteudo"] = hash_conteudo
    envelope = montar_envelope(
        tipo=NOME_PERIODO_FECHADO,
        versao=VERSAO_PERIODO_FECHADO,
        tenant_id=tenant_id,
        dados=dados,
        empresa_id=empresa_id,
    )
    publicar(envelope)
    return envelope


def publicar_periodo_reaberto(
    *,
    tenant_id: UUID,
    fechamento_id: UUID,
    periodo_id: UUID,
    empresa_id: UUID,
    reaberto_por: UUID,
    reaberto_em: dt.datetime,
    motivo: str,
    data_inicio: dt.date | None = None,
    data_fim: dt.date | None = None,
    espelhos_invalidados: int | None = None,
) -> dict[str, Any]:
    """Publica `periodo.reaberto`, na reabertura autorizada de um
    fechamento (`reabrirFechamento`, T5)."""
    dados: dict[str, Any] = {
        "fechamentoId": str(fechamento_id),
        "periodoId": str(periodo_id),
        "empresaId": str(empresa_id),
        "reabertoPor": str(reaberto_por),
        "reabertoEm": reaberto_em.isoformat(),
        "motivo": motivo,
    }
    if data_inicio is not None:
        dados["dataInicio"] = data_inicio.isoformat()
    if data_fim is not None:
        dados["dataFim"] = data_fim.isoformat()
    if espelhos_invalidados is not None:
        dados["espelhosInvalidados"] = espelhos_invalidados
    envelope = montar_envelope(
        tipo=NOME_PERIODO_REABERTO,
        versao=VERSAO_PERIODO_REABERTO,
        tenant_id=tenant_id,
        dados=dados,
        empresa_id=empresa_id,
    )
    publicar(envelope)
    return envelope


def publicar_espelho_assinado(
    *,
    tenant_id: UUID,
    espelho_id: UUID,
    colaborador_id: UUID,
    vinculo_id: UUID,
    periodo_id: UUID,
    signatario_tipo: str,
    metodo: str,
    carimbo_tempo: dt.datetime,
    hash_assinado: str,
    assinatura_id: UUID | None = None,
    versao_espelho: int | None = None,
) -> dict[str, Any]:
    """Publica `espelho.assinado`. Só chamado quando `aceite=true` (PCF
    §4) -- recusa nunca publica este evento."""
    dados: dict[str, Any] = {
        "espelhoId": str(espelho_id),
        "colaboradorId": str(colaborador_id),
        "vinculoId": str(vinculo_id),
        "periodoId": str(periodo_id),
        "signatarioTipo": signatario_tipo,
        "metodo": _METODO_PARA_EVENTO.get(metodo, metodo),
        "carimboTempo": carimbo_tempo.isoformat(),
        "hashAssinado": hash_assinado,
    }
    if assinatura_id is not None:
        dados["assinaturaId"] = str(assinatura_id)
    if versao_espelho is not None:
        dados["versaoEspelho"] = versao_espelho
    envelope = montar_envelope(
        tipo=NOME_ESPELHO_ASSINADO,
        versao=VERSAO_ESPELHO_ASSINADO,
        tenant_id=tenant_id,
        dados=dados,
    )
    publicar(envelope)
    return envelope
