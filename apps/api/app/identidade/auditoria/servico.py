"""Regras de negocio de `listarAuditoria`, `obterRegistroAuditoria` e
`verificarCadeiaAuditoria` (T10)."""

from __future__ import annotations

import datetime as _dt
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.erros import ErroDeAplicacao
from app.identidade.rbac import paginacao
from app.identidade.rbac._contrato import contrato


async def listar_auditoria(
    sessao: AsyncSession,
    *,
    tenant_id: UUID,
    cursor: str | None,
    limite: int | None,
    entidade: str | None,
    entidade_id: UUID | None,
    usuario_id: UUID | None,
    acao: str | None,
    resultado: str | None,
    origem: str | None,
    de: _dt.datetime | None,
    ate: _dt.datetime | None,
) -> tuple[list[Any], dict[str, Any]]:
    consulta = sa.select(contrato.Auditoria).where(contrato.Auditoria.tenant_id == tenant_id)
    if entidade:
        consulta = consulta.where(contrato.Auditoria.entidade == entidade)
    if entidade_id is not None:
        consulta = consulta.where(contrato.Auditoria.entidade_id == entidade_id)
    if usuario_id is not None:
        consulta = consulta.where(contrato.Auditoria.usuario_id == usuario_id)
    if acao:
        consulta = consulta.where(contrato.Auditoria.acao == acao)
    if resultado:
        consulta = consulta.where(contrato.Auditoria.resultado == resultado)
    if origem:
        consulta = consulta.where(contrato.Auditoria.origem == origem)
    if de is not None:
        consulta = consulta.where(contrato.Auditoria.ocorrido_em >= de)
    if ate is not None:
        consulta = consulta.where(contrato.Auditoria.ocorrido_em <= ate)
    return await paginacao.paginar(
        sessao,
        consulta,
        coluna_criado_em=contrato.Auditoria.criado_em,
        coluna_id=contrato.Auditoria.id,
        cursor=cursor,
        limite=limite,
    )


async def obter_registro_auditoria(
    sessao: AsyncSession, *, tenant_id: UUID, registro_id: UUID
) -> Any:
    registro = await sessao.get(contrato.Auditoria, registro_id)
    if registro is None or registro.tenant_id != tenant_id:
        raise ErroDeAplicacao("PONTO-REC-001")
    return registro
