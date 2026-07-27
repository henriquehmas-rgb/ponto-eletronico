"""Decisão de tratamento (aprovar/reprovar) e trava de período fechado (T9).

`decidirTratamento` é a aprovação **do tratamento**, nunca a aprovação da
`solicitacao_id` referenciada (o workflow de aprovação de solicitações em si
é da F10 -- PCF §2/§9, proibição 4). Aprovar marca `status='aprovado'` e
agenda o recálculo do dia afetado (T10), expandido em um dia para cada lado
por dependência de interjornada/jornada-que-cruza-meia-noite (ADR-004, ponto
5 -- ver docstring de `recalculo.py`). Reprovar marca `status='reprovado'`
e **nunca** toca a apuração.

`ajuste.aprovado`/`ajuste.reprovado` só são publicados quando
`tratamentos.solicitacao_id` não é nulo (o payload de `events.yaml` exige
`solicitacaoId`/`protocolo`) -- um tratamento criado diretamente por
RH/gestor sem solicitação de workflow associada nunca publica estes dois
eventos, só `apuracao.recalculada` quando o dia muda de fato (publicado por
`recalcular_periodo`, T10, não por este módulo).
"""

from __future__ import annotations

import datetime as dt
from uuid import UUID

from ponto_contracts import Solicitacao, Tratamento
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.apuracao.tratamento import eventos
from app.apuracao.tratamento.erros_bd import traduzir_integridade
from app.apuracao.tratamento.servico import (
    obter_tratamento,
    obter_vinculo,
    verificar_periodo_do_vinculo,
)
from app.core.erros import ErroDeAplicacao
from app.schemas import contrato as esquemas

CODIGO_CORPO_INVALIDO = "PONTO-VAL-001"
CODIGO_TRANSICAO_INVALIDA = "PONTO-CONF-003"

#: Único estágio a partir do qual uma decisão é aceita: o tratamento precisa
#: ter sido submetido (`pendente`, o padrão de criação). `rascunho` ainda não
#: foi submetido; `aprovado`/`reprovado`/`cancelado`/`aplicado` já foram
#: decididos ou encerrados.
_STATUS_DECIDIVEL = "pendente"


async def decidir_tratamento(
    sessao: AsyncSession,
    tenant_id: UUID,
    tratamento_id: UUID,
    dados: esquemas.DecisaoRequisicao,
    *,
    usuario_id: UUID | None,
) -> Tratamento:
    if dados.decisao is None:
        raise ErroDeAplicacao(CODIGO_CORPO_INVALIDO, detalhe="decisao e obrigatoria.")
    decisao = dados.decisao.value if hasattr(dados.decisao, "value") else dados.decisao

    tratamento = await obter_tratamento(sessao, tratamento_id)
    if tratamento.status != _STATUS_DECIDIVEL:
        raise ErroDeAplicacao(
            CODIGO_TRANSICAO_INVALIDA,
            detalhe=f"Tratamento em situacao '{tratamento.status}' nao esta pendente de decisao.",
        )

    if decisao == "reprovar":
        return await _reprovar(sessao, tenant_id, tratamento, dados, usuario_id=usuario_id)
    return await _aprovar(sessao, tenant_id, tratamento, dados, usuario_id=usuario_id)


async def _aprovar(
    sessao: AsyncSession,
    tenant_id: UUID,
    tratamento: Tratamento,
    dados: esquemas.DecisaoRequisicao,
    *,
    usuario_id: UUID | None,
) -> Tratamento:
    vinculo = await obter_vinculo(sessao, tratamento.vinculo_id)
    await verificar_periodo_do_vinculo(sessao, tenant_id, vinculo, tratamento.data_referencia)

    agora = dt.datetime.now(tz=dt.UTC)
    tratamento.status = "aprovado"
    tratamento.aprovado_por = usuario_id
    tratamento.aprovado_em = agora
    tratamento.atualizado_por = usuario_id
    try:
        await sessao.flush()
    except IntegrityError as exc:
        raise traduzir_integridade(exc, padrao=CODIGO_CORPO_INVALIDO) from exc

    if tratamento.solicitacao_id is not None:
        solicitacao = await sessao.get(Solicitacao, tratamento.solicitacao_id)
        if solicitacao is not None:
            eventos.publicar_ajuste_aprovado(
                tenant_id=tenant_id,
                solicitacao_id=solicitacao.id,
                protocolo=solicitacao.protocolo,
                colaborador_id=tratamento.colaborador_id,
                data_referencia=tratamento.data_referencia,
                tratamento_id=tratamento.id,
                decidido_em=agora,
                vinculo_id=tratamento.vinculo_id,
                aprovador_usuario_id=usuario_id,
                por_delegacao=dados.delegacao_id is not None,
                comentario=dados.comentario,
            )

    # Import tardio: `recalcular_periodo` depende de `apurar_dia` (A1) -- ver
    # docstring de `recalculo.py`.
    from app.apuracao.tratamento.recalculo import recalcular_periodo

    await recalcular_periodo(
        sessao,
        tenant_id,
        vinculo_id=tratamento.vinculo_id,
        inicio=tratamento.data_referencia - dt.timedelta(days=1),
        fim=tratamento.data_referencia + dt.timedelta(days=1),
        motivo="tratamento",
    )
    return tratamento


async def _reprovar(
    sessao: AsyncSession,
    tenant_id: UUID,
    tratamento: Tratamento,
    dados: esquemas.DecisaoRequisicao,
    *,
    usuario_id: UUID | None,
) -> Tratamento:
    comentario = (dados.comentario or "").strip()
    if not comentario:
        raise ErroDeAplicacao(
            CODIGO_CORPO_INVALIDO, detalhe="comentario e obrigatorio na reprovacao."
        )

    agora = dt.datetime.now(tz=dt.UTC)
    tratamento.status = "reprovado"
    tratamento.reprovado_motivo = comentario
    tratamento.atualizado_por = usuario_id
    try:
        await sessao.flush()
    except IntegrityError as exc:
        raise traduzir_integridade(exc, padrao=CODIGO_CORPO_INVALIDO) from exc

    if tratamento.solicitacao_id is not None:
        solicitacao = await sessao.get(Solicitacao, tratamento.solicitacao_id)
        if solicitacao is not None:
            eventos.publicar_ajuste_reprovado(
                tenant_id=tenant_id,
                solicitacao_id=solicitacao.id,
                protocolo=solicitacao.protocolo,
                colaborador_id=tratamento.colaborador_id,
                data_referencia=tratamento.data_referencia,
                decidido_em=agora,
                motivo=comentario,
                aprovador_usuario_id=usuario_id,
            )
    # Reprovar nunca toca a apuracao (T9): nenhum recalculo, nenhum evento
    # `apuracao.recalculada`.
    return tratamento
