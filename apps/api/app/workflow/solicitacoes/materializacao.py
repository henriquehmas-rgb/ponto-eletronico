"""Despachante genérico de materialização (F10, T4, agente A1) -- PCF §2.1,
§2.2, §2.3, §4.

`materializar_solicitacao_aprovada` é chamada por
`app.workflow.aprovacoes.servico.decidirAprovacao` (T3) **só** quando a
ÚLTIMA etapa da cadeia de uma `Solicitacao` aprova. Resolve
`tipos_solicitacao.tipo_tratamento_id`:

* **Preenchido** -- cobre `ajuste_ponto`, `abono`, `justificativa`,
  `compensacao`, `afastamento` (retroativo) e qualquer categoria que o
  tenant configure com um tipo de tratamento próprio (`criarTipoSolicitacao`,
  T2): cria um `Tratamento` em `status='pendente'` referenciando
  `solicitacao_id` (via `app.apuracao.tratamento.servico.criar_tratamento`,
  F4) e aprova (via `app.apuracao.tratamento.decisao.decidir_tratamento`,
  F4) -- reaproveitamento integral, nenhuma linha de lógica de cálculo
  duplicada (PCF §2.1, proibição 4).
* **`ferias`/`folga`** -- despacha para
  `app.workflow.solicitacoes.afastamentos.materializar_ferias_ou_folga`
  (ownership exclusivo de A4, importado tardiamente -- ver a nota abaixo).
* **Nenhum dos dois** -- nenhum efeito automático (PCF §2.2): a solicitação
  só transiciona para `aprovada`, sem tocar tratamento/afastamento/banco de
  horas.

`reprovar_solicitacao` é o espelho para REPROVAÇÃO, chamada por
`decidirAprovacao` em qualquer etapa (não só a última) que decida reprovar.
Reprovação nunca materializa (nunca cria `Afastamento` nem consome banco de
horas -- "Pronto quando" de T3), mas para categorias com
`tipo_tratamento_id` configurado ainda cria+reprova um `Tratamento`,
reaproveitando o MESMO caminho de publicação de evento que a aprovação usa
(`decidir_tratamento` já publica `ajuste.reprovado` via
`app.apuracao.tratamento.eventos` quando `tratamento.solicitacao_id` não é
nulo -- ver `decisao.py::_reprovar`, que nunca toca a apuração). Para
`ferias`/`folga`/categorias sem tratamento, publica `ajuste.reprovado`
diretamente por este pacote (`app.workflow.solicitacoes.eventos`) --
`events.yaml` declara esse evento sem restringir por categoria ("Quando
qualquer etapa da cadeia decide por reprovar").

**Import tardio de `app.workflow.solicitacoes.afastamentos`.** Esse módulo é
ownership EXCLUSIVO de A4 (PCF §5) -- mesmo padrão que
`app.apuracao.tratamento.decisao`/`servico` (F4) já usam para uma
dependência de outro agente da mesma fase que roda em paralelo: o import
fica dentro da função, não no topo do módulo, para este arquivo compilar e
ser testável isoladamente mesmo que `afastamentos.py` ainda não exista no
momento em que é escrito.

**Um `Tratamento` só modela UM dia** (`tratamentos.data_referencia`, `NOT
NULL`, singular) -- ver `_dias_da_solicitacao` para a decisão de como uma
`Solicitacao` com intervalo (`dataInicio`/`dataFim`, usado por
`compensacao`/`afastamento` no formulário real de F8) vira um ou mais
`Tratamento`s.
"""

from __future__ import annotations

import datetime as dt
from typing import Any
from uuid import UUID

from ponto_contracts import Solicitacao, TipoSolicitacao
from sqlalchemy.ext.asyncio import AsyncSession

from app.apuracao.tratamento import eventos as eventos_tratamento
from app.apuracao.tratamento.decisao import decidir_tratamento
from app.apuracao.tratamento.servico import criar_tratamento
from app.core.erros import ErroDeAplicacao
from app.schemas import contrato as esquemas
from app.workflow.solicitacoes.eventos import publicar_ajuste_reprovado
from app.workflow.solicitacoes.tipos import obter_tipo_solicitacao

CODIGO_CORPO_INVALIDO = "PONTO-VAL-001"

#: Únicas duas categorias despachadas para A4 -- nenhuma outra combinação
#: existe (PCF §2.3, proibição 11: "não invente uma quarta forma de
#: materialização").
_CATEGORIAS_FERIAS_OU_FOLGA = frozenset({"ferias", "folga"})


def _dias_da_solicitacao(solicitacao: Solicitacao) -> list[dt.date]:
    """Decisão de design registrada em `docs/backlog.md` (o PCF não resolve
    explicitamente este caso): quando a solicitação carrega um intervalo
    (`dataInicio`/`dataFim`, sem `dataReferencia`), materializa UM
    `Tratamento` POR DIA do intervalo, todos com a mesma `solicitacao_id` --
    nunca inventa uma tabela nova para "tratamento de intervalo"; apenas
    chama `criar_tratamento`/`decidir_tratamento` (F4) uma vez por dia."""
    if solicitacao.data_referencia is not None:
        return [solicitacao.data_referencia]
    if solicitacao.data_inicio is not None:
        fim = solicitacao.data_fim or solicitacao.data_inicio
        dias: list[dt.date] = []
        dia = solicitacao.data_inicio
        while dia <= fim:
            dias.append(dia)
            dia += dt.timedelta(days=1)
        return dias
    raise ErroDeAplicacao(
        CODIGO_CORPO_INVALIDO,
        detalhe="Solicitacao sem dataReferencia nem dataInicio/dataFim para materializar.",
    )


def _mapear_campos_tratamento(
    solicitacao: Solicitacao, tipo: TipoSolicitacao, dia: dt.date
) -> dict[str, Any]:
    """Mapeamento `Solicitacao` -> `TratamentoCriar`, documentado por
    categoria (PCF §2.1/T4, análogo ao `marcacoesPropostas` de
    `ajuste_ponto` citado no PCF). Comuns a todas: `colaboradorId`,
    `vinculoId` (já resolvido e gravado por `criarSolicitacao`, T2),
    `tipoTratamentoId`, `dataReferencia` (o dia desta iteração), `motivo`
    (a `descricao` do solicitante), `origem='sistema'` (o Tratamento nasce
    do workflow, não de um lançamento manual direto em `/v1/tratamentos`).

    Campos específicos, lidos de `solicitacao.payload` só quando presentes
    (nenhum é obrigatório aqui -- a única obrigatoriedade,
    `payload.tipoAfastamentoId` para `categoria='afastamento'`, já foi
    validada na criação, T2):

    * `ajuste_ponto` (`inclusao_manual`): `payload.marcacaoId`,
      `payload.datahoraProposta` (ISO-8601), `payload.sentido`.
    * `compensacao`: `payload.minutosAjuste` (inteiro).
    * `afastamento`: `payload.tipoAfastamentoId` (UUID).
    * `abono`/`justificativa`/demais: nenhum campo extra.
    """
    if solicitacao.vinculo_id is None:
        raise ErroDeAplicacao(
            CODIGO_CORPO_INVALIDO,
            detalhe="Solicitacao sem vinculoId resolvido; nao e possivel materializar tratamento.",
        )
    payload: dict[str, Any] = solicitacao.payload or {}
    campos: dict[str, Any] = {
        "colaborador_id": solicitacao.colaborador_id,
        "vinculo_id": solicitacao.vinculo_id,
        "tipo_tratamento_id": tipo.tipo_tratamento_id,
        "data_referencia": dia,
        "motivo": solicitacao.descricao,
        "origem": "sistema",
        "solicitacao_id": solicitacao.id,
    }
    if payload.get("marcacaoId"):
        campos["marcacao_id"] = payload["marcacaoId"]
    if payload.get("datahoraProposta"):
        campos["datahora_proposta"] = payload["datahoraProposta"]
    if payload.get("sentido"):
        campos["sentido"] = payload["sentido"]
    if payload.get("minutosAjuste") is not None:
        campos["minutos_ajuste"] = payload["minutosAjuste"]
    if tipo.categoria == "afastamento" and payload.get("tipoAfastamentoId"):
        campos["tipo_afastamento_id"] = payload["tipoAfastamentoId"]
    return campos


async def _materializar_via_tratamento(
    sessao: AsyncSession,
    tenant_id: UUID,
    solicitacao: Solicitacao,
    tipo: TipoSolicitacao,
    *,
    decisao: str,
    aprovador_usuario_id: UUID | None,
    comentario: str | None,
) -> None:
    """Um `Tratamento` por dia (`_dias_da_solicitacao`), cada um criado
    `pendente` e imediatamente decidido (`aprovar`/`reprovar`) -- nunca
    `INSERT`/`UPDATE` direto (PCF §9, proibições 4/5)."""
    # Import tardio: `app.notificacao` e ownership de A3 -- mesmo padrao de
    # import tardio cross-agente ja usado neste modulo para `afastamentos`
    # (A4). Achado de integracao consertado ao fechar a fase (T15/T16): ver
    # nota identica em `app/workflow/solicitacoes/servico.py::
    # criar_solicitacao`.
    from app.notificacao.motor import processar_evento

    comentario_efetivo = comentario or (
        f"Materializado a partir da solicitacao {solicitacao.protocolo}."
    )
    for dia in _dias_da_solicitacao(solicitacao):
        campos = _mapear_campos_tratamento(solicitacao, tipo, dia)
        dados_criar = esquemas.TratamentoCriar.model_validate(campos)
        tratamento = await criar_tratamento(
            sessao, tenant_id, dados_criar, usuario_id=aprovador_usuario_id
        )
        dados_decisao = esquemas.DecisaoRequisicao.model_validate(
            {"decisao": decisao, "comentario": comentario_efetivo}
        )
        # `decidir_tratamento` (F4, congelado) ja publica `ajuste.aprovado`/
        # `ajuste.reprovado` sozinho quando `tratamento.solicitacao_id` nao
        # e nulo (sempre o caso aqui) -- ver `app.apuracao.tratamento.
        # eventos.publicar_ajuste_aprovado/reprovado`, chamado de dentro de
        # `decisao.py::_aprovar/_reprovar`. Em vez de reconstruir esse
        # envelope aqui (duplicaria a montagem de payload que F4 ja faz e
        # ja testa), lemos o ultimo envelope que a propria chamada acabou
        # de anexar ao barramento interno de F4 -- unico, sequencial, mesmo
        # loop -- e o encaminhamos ao motor de notificacoes desta fase.
        indice_antes = len(eventos_tratamento.BARRAMENTO_INTERNO)
        await decidir_tratamento(
            sessao, tenant_id, tratamento.id, dados_decisao, usuario_id=aprovador_usuario_id
        )
        for envelope in eventos_tratamento.BARRAMENTO_INTERNO[indice_antes:]:
            if envelope["tipo"] in ("ajuste.aprovado", "ajuste.reprovado"):
                await processar_evento(sessao, tenant_id, envelope)


async def materializar_solicitacao_aprovada(
    sessao: AsyncSession,
    tenant_id: UUID,
    solicitacao: Solicitacao,
    *,
    aprovador_usuario_id: UUID | None,
) -> None:
    """Assinatura fixada pelo PCF (§4). Só chamada quando a ÚLTIMA etapa da
    cadeia aprova (T3) -- nunca em etapa intermediária."""
    tipo = await obter_tipo_solicitacao(sessao, solicitacao.tipo_solicitacao_id)
    if tipo.tipo_tratamento_id is not None:
        await _materializar_via_tratamento(
            sessao,
            tenant_id,
            solicitacao,
            tipo,
            decisao="aprovar",
            aprovador_usuario_id=aprovador_usuario_id,
            comentario=None,
        )
        return
    if tipo.categoria in _CATEGORIAS_FERIAS_OU_FOLGA:
        # Import tardio: `app.workflow.solicitacoes.afastamentos` e
        # ownership exclusivo de A4 -- ver docstring do modulo.
        from app.workflow.solicitacoes.afastamentos import materializar_ferias_ou_folga

        await materializar_ferias_ou_folga(
            sessao, tenant_id, solicitacao, aprovador_usuario_id=aprovador_usuario_id
        )
        return
    # Categoria sem tipo_tratamento_id e fora de ferias/folga: nenhum efeito
    # automatico (PCF §2.2, decisao fixada) -- a solicitacao so fica
    # 'aprovada', sem tocar tratamento/afastamento/banco de horas.
    return


async def reprovar_solicitacao(
    sessao: AsyncSession,
    tenant_id: UUID,
    solicitacao: Solicitacao,
    *,
    motivo: str,
    etapa: int,
    aprovador_usuario_id: UUID | None,
) -> None:
    """Chamada por `decidirAprovacao` (T3) em QUALQUER etapa que decida
    reprovar -- reprovação nunca materializa (nunca cria `Afastamento` nem
    consome banco de horas), mas ver docstring do módulo para o porquê de
    ainda criar+reprovar um `Tratamento` quando a categoria tem
    `tipo_tratamento_id`: é o mesmo caminho de publicação de evento que a
    aprovação usa, sem duplicar a lógica de publicação em dois lugares."""
    tipo = await obter_tipo_solicitacao(sessao, solicitacao.tipo_solicitacao_id)
    if tipo.tipo_tratamento_id is not None:
        await _materializar_via_tratamento(
            sessao,
            tenant_id,
            solicitacao,
            tipo,
            decisao="reprovar",
            aprovador_usuario_id=aprovador_usuario_id,
            comentario=motivo,
        )
        return

    agora = dt.datetime.now(tz=dt.UTC)
    envelope = publicar_ajuste_reprovado(
        tenant_id=tenant_id,
        solicitacao_id=solicitacao.id,
        protocolo=solicitacao.protocolo,
        colaborador_id=solicitacao.colaborador_id,
        data_referencia=solicitacao.data_referencia or solicitacao.data_inicio,
        decidido_em=agora,
        motivo=motivo,
        etapa=etapa,
        aprovador_usuario_id=aprovador_usuario_id,
    )
    # Mesmo achado de integracao consertado em `criar_solicitacao`/
    # `_materializar_via_tratamento` -- import tardio, ownership de A3.
    from app.notificacao.motor import processar_evento

    await processar_evento(sessao, tenant_id, envelope)
