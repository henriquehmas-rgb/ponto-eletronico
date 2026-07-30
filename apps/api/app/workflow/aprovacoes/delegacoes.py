"""`listarDelegacoes`/`criarDelegacao` (F10, T3, agente A1) -- delegação
temporária de atribuições de aprovação (tipicamente férias do gestor).

A verificação de sobreposição (`inicioEm`/`fimEm` vigente contra outra
delegação ativa/agendada do MESMO `deleganteUsuarioId`) é inteiramente a
`EXCLUDE CONSTRAINT ex_delegacoes_sobreposicao` já existente no banco --
este módulo nunca faz `SELECT` prévio para "verificar" (livre de condição de
corrida), só captura a violação real via `IntegrityError` e traduz para
`PONTO-VAL-010` (mesmo padrão que
`app.workflow.solicitacoes.afastamentos._materializar_ferias`, A4, já usa
para `ex_afastamentos_sobreposicao`).
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from uuid import UUID

import sqlalchemy as sa
from ponto_contracts import Delegacao
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.erros import ErroDeAplicacao
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

CODIGO_CORPO_INVALIDO = "PONTO-VAL-001"

_CAMPOS_ORDENACAO: dict[str, CampoOrdenacao] = {
    "inicioEm": CampoOrdenacao(Delegacao.inicio_em, dt.datetime.fromisoformat),
    "fimEm": CampoOrdenacao(Delegacao.fim_em, dt.datetime.fromisoformat),
}


def _valor(bruto: object) -> object:
    return bruto.value if hasattr(bruto, "value") else bruto


async def criar_delegacao(
    sessao: AsyncSession,
    tenant_id: UUID,
    dados: esquemas.DelegacaoCriar,
    *,
    usuario_id: UUID | None,
) -> Delegacao:
    delegante_usuario_id = dados.delegante_usuario_id or usuario_id
    if delegante_usuario_id is None:
        raise ErroDeAplicacao(
            CODIGO_CORPO_INVALIDO,
            detalhe="deleganteUsuarioId e obrigatorio quando nao ha usuario autenticado.",
        )
    if delegante_usuario_id == dados.delegado_usuario_id:
        raise ErroDeAplicacao(
            CODIGO_CORPO_INVALIDO,
            detalhe="deleganteUsuarioId nao pode ser igual a delegadoUsuarioId.",
        )
    if dados.fim_em <= dados.inicio_em:
        raise ErroDeAplicacao(CODIGO_CORPO_INVALIDO, detalhe="fimEm deve ser posterior a inicioEm.")

    motivo = (dados.motivo or "").strip()
    if not motivo:
        raise ErroDeAplicacao(CODIGO_CORPO_INVALIDO, detalhe="motivo e obrigatorio.")

    delegacao = Delegacao(
        tenant_id=tenant_id,
        delegante_usuario_id=delegante_usuario_id,
        delegado_usuario_id=dados.delegado_usuario_id,
        perfil_id=dados.perfil_id,
        motivo=motivo,
        escopo=dados.escopo,
        inicio_em=dados.inicio_em,
        fim_em=dados.fim_em,
        status=_valor(dados.status) if dados.status is not None else "agendada",
        criado_por=usuario_id,
    )
    sessao.add(delegacao)
    try:
        await sessao.flush()
    except IntegrityError as exc:
        raise traduzir_integridade(exc, padrao=CODIGO_CORPO_INVALIDO) from exc
    return delegacao


async def listar_delegacoes(
    sessao: AsyncSession,
    tenant_id: UUID,
    *,
    delegante_usuario_id: UUID | None = None,
    delegado_usuario_id: UUID | None = None,
    status: str | None = None,
    vigente_em: dt.datetime | None = None,
    cursor: str | None = None,
    limite: int | None = None,
    ordenar: str | None = None,
) -> tuple[Sequence[Delegacao], esquemas.Paginacao]:
    ordenacao = interpretar_ordenar(
        ordenar, campos_aceitos=frozenset(_CAMPOS_ORDENACAO), padrao="inicioEm"
    )
    limite_efetivo = normalizar_limite(limite)

    consulta = sa.select(Delegacao).where(Delegacao.tenant_id == tenant_id)
    if delegante_usuario_id is not None:
        consulta = consulta.where(Delegacao.delegante_usuario_id == delegante_usuario_id)
    if delegado_usuario_id is not None:
        consulta = consulta.where(Delegacao.delegado_usuario_id == delegado_usuario_id)
    if status is not None:
        consulta = consulta.where(Delegacao.status == status)
    if vigente_em is not None:
        consulta = consulta.where(Delegacao.inicio_em <= vigente_em, Delegacao.fim_em >= vigente_em)

    campo = _CAMPOS_ORDENACAO[ordenacao.campo]
    linhas, tem_mais = await executar_pagina(
        sessao,
        consulta,
        ordenacao=ordenacao,
        campo=campo,
        coluna_id=Delegacao.id,
        cursor=cursor,
        limite=limite_efetivo,
    )
    atributo = "inicio_em" if ordenacao.campo == "inicioEm" else "fim_em"
    proximo_cursor = None
    if tem_mais and linhas:
        ultimo = linhas[-1]
        proximo_cursor = codificar_cursor(ordenacao, getattr(ultimo, atributo), ultimo.id)
    paginacao = montar_paginacao(
        proximo_cursor=proximo_cursor, tem_mais=tem_mais, limite=limite_efetivo
    )
    return linhas, paginacao


async def delegacao_vigente(
    sessao: AsyncSession,
    tenant_id: UUID,
    *,
    delegado_usuario_id: UUID,
    delegante_usuario_id: UUID,
    instante: dt.datetime,
) -> Delegacao | None:
    """Delegação `ativa`/`agendada` vigente no instante dado, entre o par
    delegado/delegante -- usado por `app.workflow.aprovacoes.servico` para
    resolver a fila de aprovação por delegação (T3)."""
    consulta = (
        sa.select(Delegacao)
        .where(
            Delegacao.tenant_id == tenant_id,
            Delegacao.delegado_usuario_id == delegado_usuario_id,
            Delegacao.delegante_usuario_id == delegante_usuario_id,
            Delegacao.status.in_(("agendada", "ativa")),
            Delegacao.inicio_em <= instante,
            Delegacao.fim_em >= instante,
        )
        .order_by(Delegacao.inicio_em.desc())
        .limit(1)
    )
    return (await sessao.execute(consulta)).scalars().first()
