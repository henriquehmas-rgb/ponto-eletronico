"""Servico de dominio dos recursos `escalas` (+ `escala_ciclos`).

Uma escala e um padrao ciclico de trabalho e folga (5x2, 6x1, 4x2, **12x36**,
espanhola, rotativa de N dias) que se repete a partir de `data_referencia`,
resolvido por **aritmetica modular** -- nunca materialize um calendario de
anos de escala em linhas de banco (PCF da fase, secao 2 e secao 9,
proibicao 5).

Publica `posicao_do_ciclo`, a formula fixada no PCF, reaproveitada pela T4
(atribuicao) e pelo resolvedor (F3 / A3, T7) -- **A3 importa esta funcao,
nunca a duplica nem a reescreve**.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from ponto_contracts import Escala, EscalaAtribuicao, EscalaCiclo
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
CODIGO_REGISTRO_COM_DEPENDENTES = "PONTO-CONF-004"

_CAMPOS_ORDENACAO: dict[str, CampoOrdenacao] = {
    "codigo": CampoOrdenacao(Escala.codigo, str),
    "nome": CampoOrdenacao(Escala.nome, str),
    "criadoEm": CampoOrdenacao(Escala.criado_em, dt.datetime.fromisoformat),
}


def posicao_do_ciclo(escala: Escala, atribuicao: EscalaAtribuicao, data: dt.date) -> int:
    """Posicao (1-indexada) do ciclo da `escala` na `data`, para um vinculo
    com a `atribuicao` dada. Formula fixada no PCF da fase (secao 2):

        dias_desde_inicio = (data - atribuicao.vigencia_inicio).dias
        posicao = ((dias_desde_inicio + atribuicao.posicao_inicial - 1)
                   mod escala.dias_ciclo) + 1

    Em `data == atribuicao.vigencia_inicio`, `posicao == posicao_inicial`
    (verificacao de sanidade citada no PCF). Aritmetica inteira de datas: o
    modulo do Python ja devolve resultado nao negativo para modulo positivo
    mesmo com dividendo negativo -- nao ha tratamento especial para datas
    antes de `vigencia_inicio` (a consulta de vigencia do chamador ja
    exclui esse caso). Nao ha nada de especial em cruzar 31/01 -> 01/02: a
    aritmetica e sobre a diferenca de dias, nunca sobre dia-do-mes.
    """
    dias_desde_inicio = (data - atribuicao.vigencia_inicio).days
    return ((dias_desde_inicio + atribuicao.posicao_inicial - 1) % escala.dias_ciclo) + 1


def _validar_cobertura_ciclos(dias_ciclo: int, ciclos: list[dict[str, Any]]) -> None:
    """Toda posicao de 1 ate `dias_ciclo` precisa estar coberta em `ciclos`,
    sem posicao duplicada nem faltante (PCF T3)."""
    posicoes: list[int] = [int(c["posicao"]) for c in ciclos if c.get("posicao") is not None]
    if len(posicoes) != len(ciclos):
        raise ErroDeAplicacao(CODIGO_CORPO_INVALIDO, detalhe="Todo ciclo exige posicao.")
    if len(set(posicoes)) != len(posicoes):
        raise ErroDeAplicacao(
            CODIGO_CORPO_INVALIDO, detalhe="Posicao de ciclo duplicada em ciclos."
        )
    esperado = set(range(1, dias_ciclo + 1))
    if set(posicoes) != esperado:
        faltantes = sorted(esperado - set(posicoes))
        excedentes = sorted(set(posicoes) - esperado)
        raise ErroDeAplicacao(
            CODIGO_CORPO_INVALIDO,
            detalhe=(
                f"ciclos precisa cobrir exatamente as posicoes 1..{dias_ciclo}. "
                f"Faltando: {faltantes or 'nenhuma'}. Fora da faixa: {excedentes or 'nenhuma'}."
            ),
        )


def _extrair_ciclos(campos: dict[str, Any]) -> list[dict[str, Any]] | None:
    """`campos` ja veio de `EscalaCriar.model_dump()`, entao cada item de
    `ciclos` chega como `dict` (pydantic desce recursivamente por
    submodelo), nunca mais como `EscalaCiclo`."""
    ciclos: list[dict[str, Any]] | None = campos.pop("ciclos", None)
    return ciclos


async def _substituir_ciclos(
    sessao: AsyncSession,
    tenant_id: UUID,
    escala_id: UUID,
    dias_ciclo: int,
    ciclos: list[dict[str, Any]],
) -> None:
    _validar_cobertura_ciclos(dias_ciclo, ciclos)
    await sessao.execute(
        sa.delete(EscalaCiclo).where(
            EscalaCiclo.tenant_id == tenant_id, EscalaCiclo.escala_id == escala_id
        )
    )
    for ciclo in ciclos:
        campos_ciclo = {chave: valor for chave, valor in ciclo.items() if chave != "id"}
        if campos_ciclo.get("tipo_dia") is not None:
            campos_ciclo["tipo_dia"] = campos_ciclo["tipo_dia"].value
        sessao.add(EscalaCiclo(tenant_id=tenant_id, escala_id=escala_id, **campos_ciclo))


async def obter_escala(sessao: AsyncSession, escala_id: UUID) -> Escala:
    resultado = await sessao.execute(
        select(Escala).where(Escala.id == escala_id, Escala.excluido_em.is_(None))
    )
    escala = resultado.scalar_one_or_none()
    if escala is None:
        raise ErroDeAplicacao(CODIGO_RECURSO_NAO_ENCONTRADO, detalhe="Escala nao encontrada.")
    return escala


async def listar_ciclos_da_escala(sessao: AsyncSession, escala_id: UUID) -> Sequence[EscalaCiclo]:
    resultado = await sessao.execute(
        select(EscalaCiclo)
        .where(EscalaCiclo.escala_id == escala_id)
        .order_by(EscalaCiclo.posicao.asc())
    )
    return resultado.scalars().all()


async def criar_escala(
    sessao: AsyncSession, tenant_id: UUID, dados: esquemas.EscalaCriar
) -> Escala:
    campos: dict[str, Any] = dados.model_dump(exclude_unset=True)
    ciclos = _extrair_ciclos(campos)
    if "tipo" in campos and campos["tipo"] is not None:
        campos["tipo"] = campos["tipo"].value
    if ciclos:
        _validar_cobertura_ciclos(campos["dias_ciclo"], ciclos)

    escala = Escala(tenant_id=tenant_id, **campos)
    sessao.add(escala)
    try:
        await sessao.flush()
    except IntegrityError as exc:
        raise traduzir_integridade(exc, padrao=CODIGO_CORPO_INVALIDO) from exc

    if ciclos:
        await _substituir_ciclos(sessao, tenant_id, escala.id, escala.dias_ciclo, ciclos)
        try:
            await sessao.flush()
        except IntegrityError as exc:
            raise traduzir_integridade(exc, padrao=CODIGO_CORPO_INVALIDO) from exc
    return escala


async def atualizar_escala(
    sessao: AsyncSession, escala_id: UUID, dados: esquemas.EscalaAtualizar
) -> Escala:
    escala = await obter_escala(sessao, escala_id)
    campos: dict[str, Any] = dados.model_dump(exclude_unset=True)
    ciclos = _extrair_ciclos(campos)
    if "tipo" in campos and campos["tipo"] is not None:
        campos["tipo"] = campos["tipo"].value

    for campo, valor in campos.items():
        setattr(escala, campo, valor)
    try:
        await sessao.flush()
    except IntegrityError as exc:
        raise traduzir_integridade(exc, padrao=CODIGO_CORPO_INVALIDO) from exc

    if ciclos is not None:
        await _substituir_ciclos(sessao, escala.tenant_id, escala.id, escala.dias_ciclo, ciclos)
        try:
            await sessao.flush()
        except IntegrityError as exc:
            raise traduzir_integridade(exc, padrao=CODIGO_CORPO_INVALIDO) from exc
    return escala


async def _escala_em_uso(sessao: AsyncSession, tenant_id: UUID, escala_id: UUID) -> bool:
    """`PONTO-CONF-004` quando ha `escala_atribuicoes` vigente (vigencia
    aberta ou cobrindo hoje) apontando para esta escala."""
    hoje = dt.date.today()
    resultado = await sessao.execute(
        select(EscalaAtribuicao.id)
        .where(
            EscalaAtribuicao.tenant_id == tenant_id,
            EscalaAtribuicao.escala_id == escala_id,
            sa.or_(EscalaAtribuicao.vigencia_fim.is_(None), EscalaAtribuicao.vigencia_fim >= hoje),
        )
        .limit(1)
    )
    return resultado.scalar_one_or_none() is not None


async def excluir_escala(sessao: AsyncSession, tenant_id: UUID, escala_id: UUID) -> None:
    escala = await obter_escala(sessao, escala_id)
    if await _escala_em_uso(sessao, tenant_id, escala_id):
        raise ErroDeAplicacao(
            CODIGO_REGISTRO_COM_DEPENDENTES,
            detalhe="Escala com atribuicoes vigentes; nao pode ser excluida.",
        )
    escala.excluido_em = dt.datetime.now(dt.UTC)
    try:
        await sessao.flush()
    except IntegrityError as exc:
        raise traduzir_integridade(exc, padrao=CODIGO_CORPO_INVALIDO) from exc


async def listar_escalas(
    sessao: AsyncSession,
    tenant_id: UUID,
    *,
    empresa_id: UUID | None = None,
    tipo: str | None = None,
    ativo: bool | None = None,
    cursor: str | None = None,
    limite: int | None = None,
    ordenar: str | None = None,
) -> tuple[Sequence[Escala], esquemas.Paginacao]:
    ordenacao = interpretar_ordenar(
        ordenar, campos_aceitos=frozenset(_CAMPOS_ORDENACAO), padrao="criadoEm"
    )
    limite_efetivo = normalizar_limite(limite)

    consulta = select(Escala).where(Escala.tenant_id == tenant_id, Escala.excluido_em.is_(None))
    if empresa_id is not None:
        consulta = consulta.where(Escala.empresa_id == empresa_id)
    if tipo is not None:
        consulta = consulta.where(Escala.tipo == tipo)
    if ativo is not None:
        consulta = consulta.where(Escala.ativo == ativo)

    campo = _CAMPOS_ORDENACAO[ordenacao.campo]
    linhas, tem_mais = await executar_pagina(
        sessao,
        consulta,
        ordenacao=ordenacao,
        campo=campo,
        coluna_id=Escala.id,
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
