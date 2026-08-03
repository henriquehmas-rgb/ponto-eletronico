"""Eventos de domínio `ajuste.solicitado`, `ajuste.aprovado` e
`ajuste.reprovado` publicados diretamente por este pacote (F10, T2/T3/T4,
agente A1) -- barramento interno do domínio `workflow.solicitacoes`, mesmo
padrão replicado por F2-F5/F4 (`app.pessoas.eventos`, `app.marcacao.eventos`,
`app.apuracao.tratamento.eventos`, ...): barramento em memória mais um
`logger.info`, nunca importado de outra fase -- cada domínio tem o seu
próprio (`app.apuracao.tratamento.eventos.BARRAMENTO_INTERNO` é F4, não é
reaproveitado aqui, nem o inverso).

Quando cada evento é publicado (PCF §2.1, §2.2, §2.3, §2.7, §4):

* `ajuste.solicitado` -- só em `criarSolicitacao` (T2), e só quando
  `tipos_solicitacao.categoria == 'ajuste_ponto'` (PCF §2.7 item 5, literal
  do contrato: "quando dispara: Na criação de uma solicitação cujo tipo
  pertence à categoria ajustePonto"). As demais categorias não publicam
  nada na criação.
* `ajuste.aprovado`/`ajuste.reprovado` -- para as categorias que mapeiam
  para `tipo_tratamento_id`, quem publica é `app.apuracao.tratamento.eventos`
  (F4), automaticamente dentro de `decidir_tratamento` (chamado pelo
  despachante deste pacote, `materializacao.py`) -- não duplicamos a
  publicação aqui para essas categorias. Este módulo só é usado quando a
  decisão (aprovar OU reprovar) **não passa** por `decidir_tratamento`:
  categorias `ferias`/`folga` (chamado por
  `app.workflow.solicitacoes.afastamentos`, ownership de A4) e qualquer
  categoria sem `tipo_tratamento_id` configurado (aprovação sem efeito
  automático, PCF §2.2; reprovação ainda publica `ajuste.reprovado`, porque
  `events.yaml` declara "quando dispara: Quando qualquer etapa da cadeia
  decide por reprovar", sem restringir por categoria).
* **Achado de contrato registrado em `docs/backlog.md`** (PCF §2.7 item 4):
  `ajuste.aprovado.payload.tratamentoId` é `required` em `events.yaml`, mas
  `ferias`/`folga` nunca produzem um `Tratamento`. `publicar_ajuste_aprovado`
  aqui aceita `tratamento_id=None` e, nesse caso, OMITE a chave do dicionário
  `dados` (o `BARRAMENTO_INTERNO` não valida contra o JSON Schema em tempo de
  execução -- confirmado lendo `app.apuracao.tratamento.eventos`, que já
  publica variações opcionais da mesma forma).
"""

from __future__ import annotations

import datetime as dt
from typing import Any
from uuid import UUID, uuid4

from app.core.log import obter_logger

logger = obter_logger("workflow.solicitacoes.eventos")

NOME_AJUSTE_SOLICITADO = "ajuste.solicitado"
NOME_AJUSTE_APROVADO = "ajuste.aprovado"
NOME_AJUSTE_REPROVADO = "ajuste.reprovado"

VERSAO_AJUSTE_SOLICITADO = 1
VERSAO_AJUSTE_APROVADO = 1
VERSAO_AJUSTE_REPROVADO = 1

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
    `publicadoEm` e `empresaId`. Idêntico, campo a campo, ao de
    `app.apuracao.tratamento.eventos.montar_envelope` (F4) -- não é
    importado de lá por ownership congelado, é a mesma fórmula fixa do
    contrato replicada aqui (mesmo precedente de `app.marcacao.eventos` e
    afins)."""
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


def publicar_ajuste_solicitado(
    *,
    tenant_id: UUID,
    solicitacao_id: UUID,
    protocolo: str,
    colaborador_id: UUID,
    tipo_solicitacao_codigo: str,
    data_referencia: dt.date,
    vinculo_id: UUID | None = None,
    solicitante_usuario_id: UUID | None = None,
    descricao: str | None = None,
    possui_anexo: bool | None = None,
    prazo_em: dt.datetime | None = None,
    etapa_atual: int | None = None,
) -> dict[str, Any]:
    """Publica `ajuste.solicitado`. Só chamado por `criarSolicitacao` quando
    `tipos_solicitacao.categoria == 'ajuste_ponto'` (PCF §2.7 item 5)."""
    dados: dict[str, Any] = {
        "solicitacaoId": str(solicitacao_id),
        "protocolo": protocolo,
        "colaboradorId": str(colaborador_id),
        "tipoSolicitacaoCodigo": tipo_solicitacao_codigo,
        "dataReferencia": data_referencia.isoformat(),
    }
    if vinculo_id is not None:
        dados["vinculoId"] = str(vinculo_id)
    if solicitante_usuario_id is not None:
        dados["solicitanteUsuarioId"] = str(solicitante_usuario_id)
    if descricao is not None:
        dados["descricao"] = descricao
    if possui_anexo is not None:
        dados["possuiAnexo"] = possui_anexo
    if prazo_em is not None:
        dados["prazoEm"] = prazo_em.isoformat()
    if etapa_atual is not None:
        dados["etapaAtual"] = etapa_atual
    envelope = montar_envelope(
        tipo=NOME_AJUSTE_SOLICITADO,
        versao=VERSAO_AJUSTE_SOLICITADO,
        tenant_id=tenant_id,
        dados=dados,
    )
    publicar(envelope)
    return envelope


def publicar_ajuste_aprovado(
    *,
    tenant_id: UUID,
    solicitacao_id: UUID,
    protocolo: str,
    colaborador_id: UUID,
    data_referencia: dt.date | None,
    decidido_em: dt.datetime,
    vinculo_id: UUID | None = None,
    aprovador_usuario_id: UUID | None = None,
    por_delegacao: bool | None = None,
    comentario: str | None = None,
    tratamento_id: UUID | None = None,
) -> dict[str, Any]:
    """Publica `ajuste.aprovado` para decisões que não passam por
    `decidir_tratamento` (F4) -- `ferias`/`folga` (via
    `app.workflow.solicitacoes.afastamentos`, A4) e qualquer categoria com
    `tipo_tratamento_id` configurado que, mesmo assim, chegue aqui por um
    caminho que não seja o despachante padrão (não deveria acontecer, mas a
    assinatura aceita `tratamento_id=None` sem quebrar).

    `tratamento_id=None` OMITE a chave `tratamentoId` do payload -- achado
    de contrato registrado em `docs/backlog.md` (PCF §2.7 item 4:
    `tratamentoId` é `required` em `events.yaml`, mas `ferias`/`folga` nunca
    produzem um `Tratamento`)."""
    dados: dict[str, Any] = {
        "solicitacaoId": str(solicitacao_id),
        "protocolo": protocolo,
        "colaboradorId": str(colaborador_id),
        "decididoEm": decidido_em.isoformat(),
    }
    if data_referencia is not None:
        dados["dataReferencia"] = data_referencia.isoformat()
    if tratamento_id is not None:
        dados["tratamentoId"] = str(tratamento_id)
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
    data_referencia: dt.date | None,
    decidido_em: dt.datetime,
    motivo: str,
    etapa: int | None = None,
    aprovador_usuario_id: UUID | None = None,
) -> dict[str, Any]:
    """Publica `ajuste.reprovado` para decisões que não passam por
    `decidir_tratamento` (F4): `ferias`/`folga` e qualquer categoria sem
    `tipo_tratamento_id` configurado. `events.yaml` declara este evento sem
    restringir por categoria ("Quando qualquer etapa da cadeia decide por
    reprovar") -- diferente de `ajuste.solicitado`, que é exclusivo de
    `ajuste_ponto`."""
    dados: dict[str, Any] = {
        "solicitacaoId": str(solicitacao_id),
        "protocolo": protocolo,
        "colaboradorId": str(colaborador_id),
        "decididoEm": decidido_em.isoformat(),
        "motivo": motivo,
    }
    if data_referencia is not None:
        dados["dataReferencia"] = data_referencia.isoformat()
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
