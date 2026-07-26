"""Servico de dominio do recurso `turnos`.

Um turno e um horario nomeado e, quando ha revezamento, sequenciado
(manha/tarde/noite) -- PCF da fase, secao 2. So `listarTurnos`, `criarTurno`
e `atualizarTurno` existem no contrato -- **nao ha** `obterTurno` nem
`excluirTurno`.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from typing import Any
from uuid import UUID

from ponto_contracts import Turno
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.erros import ErroDeAplicacao
from app.jornada.modelagem.erros_bd import traduzir_integridade
from app.jornada.modelagem.paginacao import (
    CampoOrdenacao,
    codificar_cursor,
    executar_pagina,
    interpretar_ordenar,
    montar_paginacao,
    normalizar_limite,
)
from app.schemas import contrato as esquemas

CODIGO_RECURSO_NAO_ENCONTRADO = "PONTO-REC-001"
CODIGO_CORPO_INVALIDO = "PONTO-VAL-001"

_CAMPOS_ORDENACAO: dict[str, CampoOrdenacao] = {
    "codigo": CampoOrdenacao(Turno.codigo, str),
    "nome": CampoOrdenacao(Turno.nome, str),
    "criadoEm": CampoOrdenacao(Turno.criado_em, dt.datetime.fromisoformat),
}


async def obter_turno(sessao: AsyncSession, turno_id: UUID) -> Turno:
    resultado = await sessao.execute(
        select(Turno).where(Turno.id == turno_id, Turno.excluido_em.is_(None))
    )
    turno = resultado.scalar_one_or_none()
    if turno is None:
        raise ErroDeAplicacao(CODIGO_RECURSO_NAO_ENCONTRADO, detalhe="Turno nao encontrado.")
    return turno


async def criar_turno(sessao: AsyncSession, tenant_id: UUID, dados: esquemas.TurnoCriar) -> Turno:
    campos: dict[str, Any] = dados.model_dump(exclude_unset=True)
    if "tipo" in campos and campos["tipo"] is not None:
        campos["tipo"] = campos["tipo"].value
    turno = Turno(tenant_id=tenant_id, **campos)
    sessao.add(turno)
    try:
        await sessao.flush()
    except IntegrityError as exc:
        raise traduzir_integridade(exc, padrao=CODIGO_CORPO_INVALIDO) from exc
    return turno


async def atualizar_turno(
    sessao: AsyncSession, turno_id: UUID, dados: esquemas.TurnoAtualizar
) -> Turno:
    turno = await obter_turno(sessao, turno_id)
    campos: dict[str, Any] = dados.model_dump(exclude_unset=True)
    if "tipo" in campos and campos["tipo"] is not None:
        campos["tipo"] = campos["tipo"].value
    for campo, valor in campos.items():
        setattr(turno, campo, valor)
    try:
        await sessao.flush()
    except IntegrityError as exc:
        raise traduzir_integridade(exc, padrao=CODIGO_CORPO_INVALIDO) from exc
    return turno


async def listar_turnos(
    sessao: AsyncSession,
    tenant_id: UUID,
    *,
    empresa_id: UUID | None = None,
    tipo: str | None = None,
    ativo: bool | None = None,
    cursor: str | None = None,
    limite: int | None = None,
    ordenar: str | None = None,
) -> tuple[Sequence[Turno], esquemas.Paginacao]:
    ordenacao = interpretar_ordenar(
        ordenar, campos_aceitos=frozenset(_CAMPOS_ORDENACAO), padrao="criadoEm"
    )
    limite_efetivo = normalizar_limite(limite)

    consulta = select(Turno).where(Turno.tenant_id == tenant_id, Turno.excluido_em.is_(None))
    if empresa_id is not None:
        consulta = consulta.where(Turno.empresa_id == empresa_id)
    if tipo is not None:
        consulta = consulta.where(Turno.tipo == tipo)
    if ativo is not None:
        consulta = consulta.where(Turno.ativo == ativo)

    campo = _CAMPOS_ORDENACAO[ordenacao.campo]
    linhas, tem_mais = await executar_pagina(
        sessao,
        consulta,
        ordenacao=ordenacao,
        campo=campo,
        coluna_id=Turno.id,
        cursor=cursor,
        limite=limite_efetivo,
    )
    atributo = {"codigo": "codigo", "nome": "nome", "criadoEm": "criado_em"}[ordenacao.campo]
    proximo_cursor = None
    if tem_mais and linhas:
        ultimo = linhas[-1]
        proximo_cursor = codificar_cursor(ordenacao, getattr(ultimo, atributo), ultimo.id)
    paginacao = montar_paginacao(
        proximo_cursor=proximo_cursor, tem_mais=tem_mais, limite=limite_efetivo
    )
    return linhas, paginacao
