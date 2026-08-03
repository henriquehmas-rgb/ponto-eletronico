"""Eventos de dominio `banco_horas.quitado` (`origem: api`, events.yaml).

Envelope e payload identicos, campo a campo, ao declarado em
`packages/contracts/events.yaml`. A entrega por webhook -- assinatura HMAC,
retentativa exponencial, dead letter queue, painel -- e da F13; este modulo
so publica no barramento interno e prova por teste que o corpo bate com o
contrato (mesmo padrao replicado por F2/F3/F5, nunca importado de outra
fase -- `app/apuracao/eventos.py` compartilhado dentro da fase seria o
lugar natural, mas cada agente desta fase mantem sua propria copia por
ownership de arquivo, ver PCF secao 5).

`banco_horas.vencendo` (`origem: scheduler`, events.yaml) NAO e publicado
por este modulo: quem publica e `apps/worker/worker/banco_horas_vencimento.py`
(propria copia, mesmo motivo -- o worker e um processo separado, sem acesso
a sessao HTTP desta API). Este modulo publicaria o evento errado se
tentasse: `events.yaml` fixa a origem de cada evento, e "confirme que
nenhum outro evento tem origem nesta fase" (PCF §3) vale tambem para NAO
publicar um evento pela origem errada.

O "barramento interno" desta fase e deliberadamente simples: uma lista em
memoria mais um `logger.info`. Ate a F13 criar a fila real de eventos de
dominio, este modulo e o unico produtor e o unico consumidor: publica,
guarda para o teste inspecionar, e loga a correlacao.
"""

from __future__ import annotations

import datetime as dt
from typing import Any
from uuid import UUID, uuid4

from app.core.log import obter_logger

logger = obter_logger("apuracao.banco_horas.eventos")

NOME_BANCO_HORAS_QUITADO = "banco_horas.quitado"
VERSAO_BANCO_HORAS_QUITADO = 1

#: Barramento interno da fase: cada envelope publicado fica aqui, na ordem
#: de publicacao. So para prova por teste e depuracao local.
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


#: `bh_quitacoes.tipo` e `snake_case` no banco; `events.yaml` declara o
#: payload `tipo` em `camelCase` para `compensacao_programada`. Os demais
#: valores (folha, folga, rescisao, expiracao) sao identicos nos dois lados.
_CAMEL_TIPO_QUITACAO: dict[str, str] = {"compensacao_programada": "compensacaoProgramada"}


def publicar_banco_horas_quitado(
    *,
    tenant_id: UUID,
    quitacao_id: UUID,
    conta_id: UUID,
    colaborador_id: UUID,
    tipo: str,
    minutos: int,
    data_efetivacao: dt.date,
    saldo_apos_minutos: int,
    lancamento_id: UUID | None = None,
    valor: float | None = None,
    competencia_folha: str | None = None,
) -> dict[str, Any]:
    """Publica `banco_horas.quitado` com os `required` de `events.yaml`
    preenchidos: quitacaoId, contaId, colaboradorId, tipo, minutos,
    dataEfetivacao, saldoAposMinutos."""
    dados: dict[str, Any] = {
        "quitacaoId": str(quitacao_id),
        "contaId": str(conta_id),
        "colaboradorId": str(colaborador_id),
        "tipo": _CAMEL_TIPO_QUITACAO.get(tipo, tipo),
        "minutos": minutos,
        "dataEfetivacao": data_efetivacao.isoformat(),
        "saldoAposMinutos": saldo_apos_minutos,
    }
    if lancamento_id is not None:
        dados["lancamentoId"] = str(lancamento_id)
    if valor is not None:
        dados["valor"] = valor
    if competencia_folha is not None:
        dados["competenciaFolha"] = competencia_folha
    envelope = montar_envelope(
        tipo=NOME_BANCO_HORAS_QUITADO,
        versao=VERSAO_BANCO_HORAS_QUITADO,
        tenant_id=tenant_id,
        dados=dados,
    )
    publicar(envelope)
    return envelope
