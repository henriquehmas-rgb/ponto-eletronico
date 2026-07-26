"""Servico de dominio do recurso `jornadas` (+ `jornada_dias`).

`jornadas` e o conjunto de regras de calculo (tolerancia, noturno, limites de
extra, politica de intervalo) aplicado a um vinculo, **versionado por
vigencia** -- trocar a regra no meio do mes nao reescreve o passado apurado
(PCF da fase, secao 2). Cobre os tipos `fixa`, `flexivel`, `livre`, `parcial`,
`intermitente`, `teletrabalho`, `motorista`: todos usam `jornada_dias`: nenhum
deles precisa de logica de codigo alem de gravar o `tipo` certo -- a
diferenca de regra de calculo entre eles e configuracao que a F4 le, nao
logica desta fase.

So `listarJornadas`, `criarJornada`, `obterJornada`, `atualizarJornada` e
`excluirJornada` existem no contrato.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from ponto_contracts import Escala, Jornada, JornadaDia, VinculoJornada
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
    "codigo": CampoOrdenacao(Jornada.codigo, str),
    "vigenciaInicio": CampoOrdenacao(Jornada.vigencia_inicio, dt.date.fromisoformat),
}


def _extrair_dias(campos: dict[str, Any]) -> list[dict[str, Any]] | None:
    """Remove `dias` do dict de campos escalares (vira linhas de
    `jornada_dias`, gravadas a parte). `campos` ja veio de
    `JornadaCriar.model_dump()`, entao cada item de `dias` chega como
    `dict` (pydantic desce recursivamente por submodelo), nunca mais como
    `JornadaDia`."""
    dias: list[dict[str, Any]] | None = campos.pop("dias", None)
    return dias


async def _substituir_dias(
    sessao: AsyncSession,
    tenant_id: UUID,
    jornada_id: UUID,
    dias: list[dict[str, Any]],
) -> None:
    """Apaga o desdobramento anterior e grava o novo. `jornada_dias` nao tem
    soft delete (nao e cadastro de topo, e desdobramento) -- a propria
    jornada e versionada por vigencia, entao reescrever os dias de uma
    vigencia ainda aberta e seguro."""
    await sessao.execute(
        sa.delete(JornadaDia).where(
            JornadaDia.tenant_id == tenant_id, JornadaDia.jornada_id == jornada_id
        )
    )
    for dia in dias:
        campos_dia = {chave: valor for chave, valor in dia.items() if chave != "id"}
        if campos_dia.get("tipo_dia") is not None:
            campos_dia["tipo_dia"] = campos_dia["tipo_dia"].value
        sessao.add(JornadaDia(tenant_id=tenant_id, jornada_id=jornada_id, **campos_dia))


async def obter_jornada(sessao: AsyncSession, jornada_id: UUID) -> Jornada:
    resultado = await sessao.execute(
        select(Jornada).where(Jornada.id == jornada_id, Jornada.excluido_em.is_(None))
    )
    jornada = resultado.scalar_one_or_none()
    if jornada is None:
        raise ErroDeAplicacao(CODIGO_RECURSO_NAO_ENCONTRADO, detalhe="Jornada nao encontrada.")
    return jornada


async def listar_dias_da_jornada(sessao: AsyncSession, jornada_id: UUID) -> Sequence[JornadaDia]:
    resultado = await sessao.execute(
        select(JornadaDia)
        .where(JornadaDia.jornada_id == jornada_id)
        .order_by(JornadaDia.dia_semana.asc())
    )
    return resultado.scalars().all()


async def criar_jornada(
    sessao: AsyncSession, tenant_id: UUID, dados: esquemas.JornadaCriar
) -> Jornada:
    campos: dict[str, Any] = dados.model_dump(exclude_unset=True)
    dias = _extrair_dias(campos)
    if "tipo" in campos and campos["tipo"] is not None:
        campos["tipo"] = campos["tipo"].value
    jornada = Jornada(tenant_id=tenant_id, **campos)
    sessao.add(jornada)
    try:
        await sessao.flush()
    except IntegrityError as exc:
        raise traduzir_integridade(exc, padrao=CODIGO_CORPO_INVALIDO) from exc

    if dias:
        await _substituir_dias(sessao, tenant_id, jornada.id, dias)
        try:
            await sessao.flush()
        except IntegrityError as exc:
            raise traduzir_integridade(exc, padrao=CODIGO_CORPO_INVALIDO) from exc
    return jornada


async def atualizar_jornada(
    sessao: AsyncSession, jornada_id: UUID, dados: esquemas.JornadaAtualizar
) -> Jornada:
    jornada = await obter_jornada(sessao, jornada_id)
    campos: dict[str, Any] = dados.model_dump(exclude_unset=True)
    dias = _extrair_dias(campos)
    if "tipo" in campos and campos["tipo"] is not None:
        campos["tipo"] = campos["tipo"].value

    for campo, valor in campos.items():
        setattr(jornada, campo, valor)
    try:
        await sessao.flush()
    except IntegrityError as exc:
        raise traduzir_integridade(exc, padrao=CODIGO_CORPO_INVALIDO) from exc

    if dias is not None:
        await _substituir_dias(sessao, jornada.tenant_id, jornada.id, dias)
        try:
            await sessao.flush()
        except IntegrityError as exc:
            raise traduzir_integridade(exc, padrao=CODIGO_CORPO_INVALIDO) from exc
    return jornada


async def _jornada_em_uso(sessao: AsyncSession, tenant_id: UUID, jornada_id: UUID) -> bool:
    """`PONTO-CONF-004` quando a jornada e referenciada por uma atribuicao de
    vinculo ainda vigente (`vinculo_jornadas`, vigencia aberta ou cobrindo
    hoje) ou por uma escala ativa (`escalas.jornada_id`). Vigencias
    encerradas no passado nao contam como "em uso" -- o historico ja apurado
    fica preservado pelo soft delete, mas nao trava a exclusao de uma
    jornada que ninguem mais usa hoje. Escolha documentada aqui porque o PCF
    nao detalha o criterio de "em uso" para este caso (secao 6, T2)."""
    hoje = dt.date.today()
    em_vinculo = await sessao.execute(
        select(VinculoJornada.id)
        .where(
            VinculoJornada.tenant_id == tenant_id,
            VinculoJornada.jornada_id == jornada_id,
            sa.or_(VinculoJornada.vigencia_fim.is_(None), VinculoJornada.vigencia_fim >= hoje),
        )
        .limit(1)
    )
    if em_vinculo.scalar_one_or_none() is not None:
        return True
    em_escala = await sessao.execute(
        select(Escala.id)
        .where(
            Escala.tenant_id == tenant_id,
            Escala.jornada_id == jornada_id,
            Escala.excluido_em.is_(None),
        )
        .limit(1)
    )
    return em_escala.scalar_one_or_none() is not None


async def excluir_jornada(sessao: AsyncSession, tenant_id: UUID, jornada_id: UUID) -> None:
    jornada = await obter_jornada(sessao, jornada_id)
    if await _jornada_em_uso(sessao, tenant_id, jornada_id):
        raise ErroDeAplicacao(
            CODIGO_REGISTRO_COM_DEPENDENTES,
            detalhe="Jornada em uso por vinculo ou escala vigente; nao pode ser excluida.",
        )
    jornada.excluido_em = dt.datetime.now(dt.UTC)
    try:
        await sessao.flush()
    except IntegrityError as exc:
        raise traduzir_integridade(exc, padrao=CODIGO_CORPO_INVALIDO) from exc


async def listar_jornadas(
    sessao: AsyncSession,
    tenant_id: UUID,
    *,
    empresa_id: UUID | None = None,
    tipo: str | None = None,
    vigente_em: dt.date | None = None,
    ativo: bool | None = None,
    cursor: str | None = None,
    limite: int | None = None,
    ordenar: str | None = None,
) -> tuple[Sequence[Jornada], esquemas.Paginacao]:
    ordenacao = interpretar_ordenar(
        ordenar, campos_aceitos=frozenset(_CAMPOS_ORDENACAO), padrao="vigenciaInicio"
    )
    limite_efetivo = normalizar_limite(limite)

    consulta = select(Jornada).where(Jornada.tenant_id == tenant_id, Jornada.excluido_em.is_(None))
    if empresa_id is not None:
        consulta = consulta.where(Jornada.empresa_id == empresa_id)
    if tipo is not None:
        consulta = consulta.where(Jornada.tipo == tipo)
    if ativo is not None:
        consulta = consulta.where(Jornada.ativo == ativo)
    if vigente_em is not None:
        consulta = consulta.where(
            Jornada.vigencia_inicio <= vigente_em,
            sa.or_(Jornada.vigencia_fim.is_(None), Jornada.vigencia_fim >= vigente_em),
        )

    campo = _CAMPOS_ORDENACAO[ordenacao.campo]
    linhas, tem_mais = await executar_pagina(
        sessao,
        consulta,
        ordenacao=ordenacao,
        campo=campo,
        coluna_id=Jornada.id,
        cursor=cursor,
        limite=limite_efetivo,
    )
    atributo = "codigo" if ordenacao.campo == "codigo" else "vigencia_inicio"
    proximo_cursor = None
    if tem_mais and linhas:
        ultimo = linhas[-1]
        proximo_cursor = codificar_cursor(ordenacao, getattr(ultimo, atributo), ultimo.id)
    paginacao = montar_paginacao(
        proximo_cursor=proximo_cursor, tem_mais=tem_mais, limite=limite_efetivo
    )
    return linhas, paginacao
