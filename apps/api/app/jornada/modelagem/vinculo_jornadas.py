"""Servico de dominio de `vinculo_jornadas`: a atribuicao datada de jornada a
um vinculo (`listarJornadasVinculo`, `atribuirJornadaVinculo`).

A constraint `EXCLUDE` (`ex_vinculo_jornadas_sobreposicao`) garante que a
consulta `WHERE vinculo_id = :v AND vigencia_inicio <= :data AND
(vigencia_fim IS NULL OR vigencia_fim >= :data)` devolve no maximo uma linha
(PCF da fase, secao 2) -- e o que permite ao resolvedor (F3 / A3) achar a
jornada vigente de um dia sem ambiguidade.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from uuid import UUID

import sqlalchemy as sa
from ponto_contracts import Vinculo, VinculoJornada
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.erros import ErroDeAplicacao
from app.jornada.modelagem.erros_bd import traduzir_integridade
from app.jornada.modelagem.fechamento import verificar_periodo_aberto
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
    "vigenciaInicio": CampoOrdenacao(VinculoJornada.vigencia_inicio, dt.date.fromisoformat),
}


async def obter_vinculo(sessao: AsyncSession, vinculo_id: UUID) -> Vinculo:
    """Le `vinculos` (F2, ownership alheio) so para resolver empresa/unidade
    do alvo -- nunca escreve nesta tabela (PCF secao 4)."""
    resultado = await sessao.execute(
        select(Vinculo).where(Vinculo.id == vinculo_id, Vinculo.excluido_em.is_(None))
    )
    vinculo = resultado.scalar_one_or_none()
    if vinculo is None:
        raise ErroDeAplicacao(CODIGO_RECURSO_NAO_ENCONTRADO, detalhe="Vinculo nao encontrado.")
    return vinculo


async def listar_jornadas_vinculo(
    sessao: AsyncSession,
    tenant_id: UUID,
    vinculo_id: UUID,
    *,
    vigente_em: dt.date | None = None,
    cursor: str | None = None,
    limite: int | None = None,
    ordenar: str | None = None,
) -> tuple[Sequence[VinculoJornada], esquemas.Paginacao]:
    await obter_vinculo(sessao, vinculo_id)

    ordenacao = interpretar_ordenar(
        ordenar, campos_aceitos=frozenset(_CAMPOS_ORDENACAO), padrao="vigenciaInicio"
    )
    limite_efetivo = normalizar_limite(limite)

    consulta = select(VinculoJornada).where(
        VinculoJornada.tenant_id == tenant_id, VinculoJornada.vinculo_id == vinculo_id
    )
    if vigente_em is not None:
        consulta = consulta.where(
            VinculoJornada.vigencia_inicio <= vigente_em,
            sa.or_(
                VinculoJornada.vigencia_fim.is_(None), VinculoJornada.vigencia_fim >= vigente_em
            ),
        )

    campo = _CAMPOS_ORDENACAO[ordenacao.campo]
    linhas, tem_mais = await executar_pagina(
        sessao,
        consulta,
        ordenacao=ordenacao,
        campo=campo,
        coluna_id=VinculoJornada.id,
        cursor=cursor,
        limite=limite_efetivo,
    )
    proximo_cursor = None
    if tem_mais and linhas:
        ultimo = linhas[-1]
        proximo_cursor = codificar_cursor(ordenacao, ultimo.vigencia_inicio, ultimo.id)
    paginacao = montar_paginacao(
        proximo_cursor=proximo_cursor, tem_mais=tem_mais, limite=limite_efetivo
    )
    return linhas, paginacao


async def atribuir_jornada_vinculo(
    sessao: AsyncSession,
    tenant_id: UUID,
    vinculo_id: UUID,
    dados: esquemas.VinculoJornadaCriar,
) -> VinculoJornada:
    vinculo = await obter_vinculo(sessao, vinculo_id)

    await verificar_periodo_aberto(
        sessao,
        tenant_id,
        empresa_id=vinculo.empresa_id,
        data=dados.vigencia_inicio,
        unidade_id=vinculo.unidade_id,
        departamento_id=vinculo.departamento_id,
    )

    campos = dados.model_dump(exclude_unset=True, exclude={"vinculo_id"})
    atribuicao = VinculoJornada(tenant_id=tenant_id, vinculo_id=vinculo_id, **campos)
    sessao.add(atribuicao)
    try:
        await sessao.flush()
    except IntegrityError as exc:
        raise traduzir_integridade(exc, padrao=CODIGO_CORPO_INVALIDO) from exc
    return atribuicao
