"""Servico de dominio do recurso `horarios`.

`horarios` e o gabarito mais simples do motor de jornada: entrada, saida,
intervalo e carga -- um bloco de montagem usado por `jornada_dias` e por
`turnos` (PCF da fase, secao 2). So `listarHorarios`, `criarHorario` e
`atualizarHorario` existem no contrato -- **nao ha** `obterHorario` nem
`excluirHorario` (secao 3/9 do PCF); nao invente as duas ausentes.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from typing import Any
from uuid import UUID

from ponto_contracts import Horario
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.erros import ErroDeAplicacao
from app.jornada.modelagem.conversao import hora_ou_none
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
    "codigo": CampoOrdenacao(Horario.codigo, str),
    "nome": CampoOrdenacao(Horario.nome, str),
    "criadoEm": CampoOrdenacao(Horario.criado_em, dt.datetime.fromisoformat),
}

_CAMPOS_HORA = ("entrada", "saida", "intervalo_inicio", "intervalo_fim")


def _validar_cruza_meia_noite(
    entrada: dt.time | None, saida: dt.time | None, cruza_meia_noite: bool | None
) -> None:
    """`horarios.cruza_meia_noite` documenta que a saida e menor que a
    entrada (jornada noturna, 12x36 que vira o dia). Quando os dois horarios
    estao presentes e a saida e estritamente menor que a entrada, o chamador
    precisa marcar `cruzaMeiaNoite: true` explicitamente -- senao e provavel
    erro de digitacao, nao jornada noturna de proposito (PCF T2)."""
    if entrada is None or saida is None:
        return
    if saida < entrada and not cruza_meia_noite:
        raise ErroDeAplicacao(
            CODIGO_CORPO_INVALIDO,
            detalhe="saida anterior a entrada exige cruzaMeiaNoite=true "
            "(jornada noturna ou 12x36 que vira o dia).",
        )


def _converter_horas(campos: dict[str, Any]) -> None:
    for campo in _CAMPOS_HORA:
        if campo in campos:
            campos[campo] = hora_ou_none(campos[campo])


async def obter_horario(sessao: AsyncSession, horario_id: UUID) -> Horario:
    resultado = await sessao.execute(
        select(Horario).where(Horario.id == horario_id, Horario.excluido_em.is_(None))
    )
    horario = resultado.scalar_one_or_none()
    if horario is None:
        raise ErroDeAplicacao(CODIGO_RECURSO_NAO_ENCONTRADO, detalhe="Horario nao encontrado.")
    return horario


async def criar_horario(
    sessao: AsyncSession, tenant_id: UUID, dados: esquemas.HorarioCriar
) -> Horario:
    campos: dict[str, Any] = dados.model_dump(exclude_unset=True)
    _converter_horas(campos)
    _validar_cruza_meia_noite(
        campos.get("entrada"), campos.get("saida"), campos.get("cruza_meia_noite")
    )
    horario = Horario(tenant_id=tenant_id, **campos)
    sessao.add(horario)
    try:
        await sessao.flush()
    except IntegrityError as exc:
        raise traduzir_integridade(exc, padrao=CODIGO_CORPO_INVALIDO) from exc
    return horario


async def atualizar_horario(
    sessao: AsyncSession, horario_id: UUID, dados: esquemas.HorarioAtualizar
) -> Horario:
    horario = await obter_horario(sessao, horario_id)
    campos: dict[str, Any] = dados.model_dump(exclude_unset=True)
    _converter_horas(campos)

    entrada = campos.get("entrada", horario.entrada)
    saida = campos.get("saida", horario.saida)
    cruza_meia_noite = campos.get("cruza_meia_noite", horario.cruza_meia_noite)
    _validar_cruza_meia_noite(entrada, saida, cruza_meia_noite)

    for campo, valor in campos.items():
        setattr(horario, campo, valor)
    try:
        await sessao.flush()
    except IntegrityError as exc:
        raise traduzir_integridade(exc, padrao=CODIGO_CORPO_INVALIDO) from exc
    return horario


async def listar_horarios(
    sessao: AsyncSession,
    tenant_id: UUID,
    *,
    empresa_id: UUID | None = None,
    cruza_meia_noite: bool | None = None,
    ativo: bool | None = None,
    cursor: str | None = None,
    limite: int | None = None,
    ordenar: str | None = None,
) -> tuple[Sequence[Horario], esquemas.Paginacao]:
    ordenacao = interpretar_ordenar(
        ordenar, campos_aceitos=frozenset(_CAMPOS_ORDENACAO), padrao="criadoEm"
    )
    limite_efetivo = normalizar_limite(limite)

    consulta = select(Horario).where(Horario.tenant_id == tenant_id, Horario.excluido_em.is_(None))
    if empresa_id is not None:
        consulta = consulta.where(Horario.empresa_id == empresa_id)
    if cruza_meia_noite is not None:
        consulta = consulta.where(Horario.cruza_meia_noite == cruza_meia_noite)
    if ativo is not None:
        consulta = consulta.where(Horario.ativo == ativo)

    campo = _CAMPOS_ORDENACAO[ordenacao.campo]
    linhas, tem_mais = await executar_pagina(
        sessao,
        consulta,
        ordenacao=ordenacao,
        campo=campo,
        coluna_id=Horario.id,
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
