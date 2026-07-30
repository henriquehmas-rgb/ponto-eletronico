"""Fila de aprovação e decisão de etapa (F10, T3, agente A1):
`listarAprovacoesPendentes`, `decidirAprovacao`.

**Reconciliação de contrato, documentada aqui por não haver um lugar melhor
(decisão de lógica de aplicação, não redecisão do PCF).** O schema gerado
descreve `Aprovacao.aprovadorUsuarioId` como "Usuario que decidiu" -- leitura
natural: só populado NO MOMENTO da decisão. Mas o PCF (T3) pede que
`listarAprovacoesPendentes` (a fila de itens PENDENTES, ainda não decididos)
filtre justamente por `Aprovacao.aprovador_usuario_id = sujeito.usuario_id`
-- coluna nula em toda etapa nunca decidida tornaria essa fila sempre vazia,
o que não faz sentido para "a caixa de entrada do gestor" (descrição da
operação em `openapi.yaml`). A única leitura que reconcilia as duas coisas:
`aprovador_usuario_id` é PRÉ-ATRIBUÍDO no momento em que a etapa é CRIADA
(`app.workflow.solicitacoes.servico.criar_solicitacao`, T2, e este módulo
ao avançar para a próxima etapa) via
`app.workflow.aprovacoes.resolucao.resolver_aprovador_papel` -- representa
"quem é responsável por esta etapa", e coincide com "quem decidiu" no caso
comum (sem delegação). Quando a etapa não tem um titular único resolvível
(papéis `diretoria`/`sistema`, ou `colaborador_gestores` sem linha vigente),
a coluna fica `NULL` na criação e `listarAprovacoesPendentes` enxerga essas
etapas pelo casamento de `papel` contra os perfis RBAC do próprio sujeito
(`Sujeito.perfis`, já resolvido por F1) -- nunca por uma segunda consulta a
`app.identidade.rbac` (fora do "Consome" desta fase).

`decidirAprovacao` (§2.1, §2.3 do PCF): aprovar a ÚLTIMA etapa da cadeia
despacha para
`app.workflow.solicitacoes.materializacao.materializar_solicitacao_aprovada`;
aprovar uma etapa intermediária cria a próxima `Aprovacao` (papel seguinte
da cadeia, aprovador pré-atribuído do mesmo jeito); reprovar em QUALQUER
etapa despacha para
`app.workflow.solicitacoes.materializacao.reprovar_solicitacao` e encerra a
solicitação sem tocar as etapas seguintes (nenhuma é criada). Toda decisão
grava `gravar_auditoria` (F1, `entidade="aprovacoes"`), inclusive quando
exercida por delegação (`delegacao_id` no `metadados`, PCF §2.6/critério de
aceite 8).
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from uuid import UUID

import sqlalchemy as sa
from ponto_contracts import Aprovacao, Delegacao, Solicitacao
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.erros import ErroDeAplicacao
from app.identidade.auditoria.hash_chain import gravar_auditoria
from app.schemas import contrato as esquemas
from app.workflow.aprovacoes.erros_bd import traduzir_integridade
from app.workflow.aprovacoes.paginacao import (
    CampoOrdenacao,
    codificar_cursor,
    executar_pagina,
    interpretar_ordenar,
    montar_paginacao,
    normalizar_limite,
)
from app.workflow.aprovacoes.resolucao import resolver_aprovador_papel
from app.workflow.solicitacoes.materializacao import (
    materializar_solicitacao_aprovada,
    reprovar_solicitacao,
)
from app.workflow.solicitacoes.tipos import obter_tipo_solicitacao, papeis_da_cadeia

CODIGO_CORPO_INVALIDO = "PONTO-VAL-001"
CODIGO_RECURSO_NAO_ENCONTRADO = "PONTO-REC-001"
CODIGO_TRANSICAO_INVALIDA = "PONTO-CONF-003"
CODIGO_FORA_DO_ALCANCE = "PONTO-PERM-002"
CODIGO_DELEGACAO_INVALIDA = "PONTO-PERM-005"

_CAMPOS_ORDENACAO: dict[str, CampoOrdenacao] = {
    "prazoEm": CampoOrdenacao(Aprovacao.prazo_em, dt.datetime.fromisoformat),
    "criadoEm": CampoOrdenacao(Aprovacao.criado_em, dt.datetime.fromisoformat),
}


def _valor(bruto: object) -> object:
    return bruto.value if hasattr(bruto, "value") else bruto


async def obter_aprovacao(sessao: AsyncSession, tenant_id: UUID, aprovacao_id: UUID) -> Aprovacao:
    aprovacao = await sessao.get(Aprovacao, aprovacao_id)
    if aprovacao is None or aprovacao.tenant_id != tenant_id:
        raise ErroDeAplicacao(
            CODIGO_RECURSO_NAO_ENCONTRADO, detalhe="Etapa de aprovacao nao encontrada."
        )
    return aprovacao


async def listar_aprovacoes_pendentes(
    sessao: AsyncSession,
    tenant_id: UUID,
    *,
    sujeito_usuario_id: UUID | None,
    sujeito_perfis: frozenset[str] = frozenset(),
    decisao: str | None = None,
    papel: str | None = None,
    solicitacao_id: UUID | None = None,
    atrasadas: bool | None = None,
    incluir_delegadas: bool | None = None,
    cursor: str | None = None,
    limite: int | None = None,
    ordenar: str | None = None,
) -> tuple[Sequence[Aprovacao], esquemas.Paginacao]:
    ordenacao = interpretar_ordenar(
        ordenar, campos_aceitos=frozenset(_CAMPOS_ORDENACAO), padrao="prazoEm"
    )
    limite_efetivo = normalizar_limite(limite)

    condicoes_visibilidade: list[sa.ColumnElement[bool]] = []
    if sujeito_usuario_id is not None:
        condicoes_visibilidade.append(Aprovacao.aprovador_usuario_id == sujeito_usuario_id)
    if sujeito_perfis:
        condicoes_visibilidade.append(
            sa.and_(Aprovacao.aprovador_usuario_id.is_(None), Aprovacao.papel.in_(sujeito_perfis))
        )
    incluir_delegadas_efetivo = incluir_delegadas is not False
    if incluir_delegadas_efetivo and sujeito_usuario_id is not None:
        agora = dt.datetime.now(tz=dt.UTC)
        delegantes = sa.select(Delegacao.delegante_usuario_id).where(
            Delegacao.tenant_id == tenant_id,
            Delegacao.delegado_usuario_id == sujeito_usuario_id,
            Delegacao.status.in_(("agendada", "ativa")),
            Delegacao.inicio_em <= agora,
            Delegacao.fim_em >= agora,
        )
        condicoes_visibilidade.append(Aprovacao.aprovador_usuario_id.in_(delegantes))

    consulta = sa.select(Aprovacao).where(Aprovacao.tenant_id == tenant_id)
    if condicoes_visibilidade:
        consulta = consulta.where(sa.or_(*condicoes_visibilidade))

    consulta = consulta.where(Aprovacao.decisao == (decisao or "pendente"))
    if papel is not None:
        consulta = consulta.where(Aprovacao.papel == papel)
    if solicitacao_id is not None:
        consulta = consulta.where(Aprovacao.solicitacao_id == solicitacao_id)
    if atrasadas:
        consulta = consulta.where(
            Aprovacao.prazo_em.is_not(None), Aprovacao.prazo_em < dt.datetime.now(tz=dt.UTC)
        )

    campo = _CAMPOS_ORDENACAO[ordenacao.campo]
    linhas, tem_mais = await executar_pagina(
        sessao,
        consulta,
        ordenacao=ordenacao,
        campo=campo,
        coluna_id=Aprovacao.id,
        cursor=cursor,
        limite=limite_efetivo,
    )
    atributo = "prazo_em" if ordenacao.campo == "prazoEm" else "criado_em"
    proximo_cursor = None
    if tem_mais and linhas:
        ultimo = linhas[-1]
        proximo_cursor = codificar_cursor(ordenacao, getattr(ultimo, atributo), ultimo.id)
    paginacao = montar_paginacao(
        proximo_cursor=proximo_cursor, tem_mais=tem_mais, limite=limite_efetivo
    )
    return linhas, paginacao


async def _validar_delegacao(
    sessao: AsyncSession,
    tenant_id: UUID,
    *,
    delegacao_id: UUID,
    sujeito_usuario_id: UUID | None,
    aprovador_pre_atribuido: UUID | None,
) -> Delegacao:
    delegacao = await sessao.get(Delegacao, delegacao_id)
    agora = dt.datetime.now(tz=dt.UTC)
    valido = (
        delegacao is not None
        and delegacao.tenant_id == tenant_id
        and delegacao.delegado_usuario_id == sujeito_usuario_id
        and delegacao.status in ("agendada", "ativa")
        and delegacao.inicio_em <= agora <= delegacao.fim_em
        and (
            aprovador_pre_atribuido is None
            or delegacao.delegante_usuario_id == aprovador_pre_atribuido
        )
    )
    if not valido or delegacao is None:
        raise ErroDeAplicacao(
            CODIGO_DELEGACAO_INVALIDA,
            detalhe="Delegacao informada nao esta vigente para este par de usuarios/etapa.",
        )
    return delegacao


async def decidir_aprovacao(
    sessao: AsyncSession,
    tenant_id: UUID,
    aprovacao_id: UUID,
    dados: esquemas.DecisaoRequisicao,
    *,
    usuario_id: UUID | None,
    ip: str | None = None,
    user_agent: str | None = None,
) -> Aprovacao:
    aprovacao = await obter_aprovacao(sessao, tenant_id, aprovacao_id)
    if aprovacao.decisao != "pendente":
        raise ErroDeAplicacao(
            CODIGO_TRANSICAO_INVALIDA,
            detalhe=f"Etapa em situacao '{aprovacao.decisao}' nao esta pendente de decisao.",
        )

    decisao_valor = _valor(dados.decisao)
    if decisao_valor not in ("aprovar", "reprovar"):
        raise ErroDeAplicacao(CODIGO_CORPO_INVALIDO, detalhe="decisao e obrigatoria.")

    comentario = (dados.comentario or "").strip() or None
    if decisao_valor == "reprovar" and not comentario:
        raise ErroDeAplicacao(
            CODIGO_CORPO_INVALIDO, detalhe="comentario e obrigatorio na reprovacao."
        )

    por_delegacao = False
    if dados.delegacao_id is not None:
        await _validar_delegacao(
            sessao,
            tenant_id,
            delegacao_id=dados.delegacao_id,
            sujeito_usuario_id=usuario_id,
            aprovador_pre_atribuido=aprovacao.aprovador_usuario_id,
        )
        por_delegacao = True
    elif (
        aprovacao.aprovador_usuario_id is not None
        and usuario_id is not None
        and aprovacao.aprovador_usuario_id != usuario_id
    ):
        raise ErroDeAplicacao(
            CODIGO_FORA_DO_ALCANCE,
            detalhe="Esta etapa esta atribuida a outro aprovador; decida por delegacao.",
        )

    solicitacao = await sessao.get(Solicitacao, aprovacao.solicitacao_id)
    if solicitacao is None:
        raise ErroDeAplicacao(CODIGO_RECURSO_NAO_ENCONTRADO, detalhe="Solicitacao nao encontrada.")

    agora = dt.datetime.now(tz=dt.UTC)
    decisao_anterior = aprovacao.decisao
    aprovacao.comentario = comentario
    aprovacao.decidido_em = agora
    aprovacao.aprovador_delegacao_id = dados.delegacao_id if por_delegacao else None
    if not por_delegacao and aprovacao.aprovador_usuario_id is None:
        aprovacao.aprovador_usuario_id = usuario_id
    if ip is not None:
        aprovacao.ip = ip
    aprovacao.atualizado_por = usuario_id

    tipo = await obter_tipo_solicitacao(sessao, solicitacao.tipo_solicitacao_id)
    papeis = papeis_da_cadeia(tipo.etapas)

    if decisao_valor == "aprovar":
        aprovacao.decisao = "aprovada"
        try:
            await sessao.flush()
        except IntegrityError as exc:
            raise traduzir_integridade(exc, padrao=CODIGO_CORPO_INVALIDO) from exc

        if aprovacao.etapa < len(papeis):
            proximo_papel = papeis[aprovacao.etapa]
            proximo_aprovador = await resolver_aprovador_papel(
                sessao,
                tenant_id,
                colaborador_id=solicitacao.colaborador_id,
                papel=proximo_papel,
                data_referencia=solicitacao.data_referencia
                or solicitacao.data_inicio
                or dt.date.today(),
            )
            prazo_em = None
            if tipo.prazo_resposta_horas is not None:
                prazo_em = agora + dt.timedelta(hours=tipo.prazo_resposta_horas)
            proxima_etapa = Aprovacao(
                tenant_id=tenant_id,
                solicitacao_id=solicitacao.id,
                etapa=aprovacao.etapa + 1,
                papel=proximo_papel,
                aprovador_usuario_id=proximo_aprovador,
                decisao="pendente",
                prazo_em=prazo_em,
                criado_por=usuario_id,
            )
            sessao.add(proxima_etapa)
            solicitacao.etapa_atual = aprovacao.etapa + 1
            solicitacao.prazo_em = prazo_em
            solicitacao.atualizado_por = usuario_id
        else:
            await materializar_solicitacao_aprovada(
                sessao, tenant_id, solicitacao, aprovador_usuario_id=usuario_id
            )
            solicitacao.status = "aprovada"
            solicitacao.concluida_em = agora
            solicitacao.resultado = comentario or "Aprovada."
            solicitacao.atualizado_por = usuario_id
    else:
        aprovacao.decisao = "reprovada"
        if comentario is None:  # defensivo -- ja validado acima, nunca deveria disparar
            raise ErroDeAplicacao(
                CODIGO_CORPO_INVALIDO, detalhe="comentario e obrigatorio na reprovacao."
            )
        await reprovar_solicitacao(
            sessao,
            tenant_id,
            solicitacao,
            motivo=comentario,
            etapa=aprovacao.etapa,
            aprovador_usuario_id=usuario_id,
        )
        solicitacao.status = "reprovada"
        solicitacao.concluida_em = agora
        solicitacao.resultado = comentario
        solicitacao.atualizado_por = usuario_id

    try:
        await sessao.flush()
    except IntegrityError as exc:
        raise traduzir_integridade(exc, padrao=CODIGO_CORPO_INVALIDO) from exc

    await gravar_auditoria(
        sessao,
        tenant_id=tenant_id,
        evento="aprovacao.decidida",
        entidade="aprovacoes",
        acao="aprovar" if decisao_valor == "aprovar" else "reprovar",
        entidade_id=aprovacao.id,
        usuario_id=usuario_id,
        delegacao_id=dados.delegacao_id if por_delegacao else None,
        ip=ip,
        user_agent=user_agent,
        valor_anterior={"decisao": decisao_anterior},
        valor_novo={"decisao": aprovacao.decisao},
        metadados={
            "solicitacaoId": str(solicitacao.id),
            "etapa": aprovacao.etapa,
            "porDelegacao": por_delegacao,
        },
    )

    return aprovacao
