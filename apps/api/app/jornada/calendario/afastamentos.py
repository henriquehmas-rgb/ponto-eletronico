"""Servicos de dominio de `tipos_afastamento` e `afastamentos`.

Afastamento e insumo da apuracao (F4), nunca marcacao: este modulo nunca
escreve em `marcacoes` nem em `tratamentos`. `afastamentos.cid` e dado de
saude -- a leitura passa por `Depends(exigir_permissao("afastamentos.ler"))`,
que ja grava `acessos_dados_sensiveis` sozinho porque a permissao esta
marcada `sensivel` no catalogo semeado pela F1 (`migrations/seed_dev.py`,
recurso `afastamentos`); este modulo nao redeclara nada disso.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from ponto_contracts import Afastamento, Colaborador, TipoAfastamento, Vinculo
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.erros import ErroDeAplicacao
from app.jornada.calendario.erros_bd import traduzir_integridade
from app.jornada.calendario.fechamento import verificar_periodo_aberto
from app.jornada.calendario.paginacao import (
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
CODIGO_INTERVALO_INVALIDO = "PONTO-VAL-007"
CODIGO_TRANSICAO_INVALIDA = "PONTO-CONF-003"

_CAMPOS_ORDENACAO_TIPO: dict[str, CampoOrdenacao] = {
    "criadoEm": CampoOrdenacao(TipoAfastamento.criado_em, dt.datetime.fromisoformat),
    "codigo": CampoOrdenacao(TipoAfastamento.codigo, str),
    "nome": CampoOrdenacao(TipoAfastamento.nome, str),
}
_CAMPOS_ORDENACAO_AFASTAMENTO: dict[str, CampoOrdenacao] = {
    "criadoEm": CampoOrdenacao(Afastamento.criado_em, dt.datetime.fromisoformat),
    "dataInicio": CampoOrdenacao(Afastamento.data_inicio, dt.date.fromisoformat),
}

#: Transicoes de `status` aceitas a partir do estado atual. Estado ausente do
#: mapa (terminal: reprovado/cancelado/encerrado) nao admite nenhuma
#: transicao de saida. Atualizar para o MESMO status corrente e sempre
#: aceito (no-op) e nao passa por este mapa.
_TRANSICOES_VALIDAS: dict[str, frozenset[str]] = {
    "solicitado": frozenset({"aprovado", "reprovado", "cancelado"}),
    "aprovado": frozenset({"cancelado", "encerrado"}),
}


def _hora_ou_none(valor: str | None) -> dt.time | None:
    """`AfastamentoCriar.hora_inicio`/`hora_fim` chegam como `str`
    (`^([01][0-9]|2[0-3]):[0-5][0-9]$`, sem JSON `time`); a coluna e `TIME`
    e o driver assincrono exige o tipo exato."""
    if valor is None:
        return None
    return dt.time.fromisoformat(valor)


def _validar_parcial(periodo_parcial: bool, hora_inicio: str | None, hora_fim: str | None) -> None:
    """Espelha `ck_afastamentos_parcial`."""
    if periodo_parcial and (hora_inicio is None or hora_fim is None):
        raise ErroDeAplicacao(
            CODIGO_CORPO_INVALIDO,
            detalhe="horaInicio e horaFim sao obrigatorios quando periodoParcial e verdadeiro.",
        )


def _validar_periodo(data_inicio: dt.date, data_fim: dt.date | None) -> None:
    """Espelha `ck_afastamentos_periodo`."""
    if data_fim is not None and data_fim < data_inicio:
        raise ErroDeAplicacao(
            CODIGO_INTERVALO_INVALIDO, detalhe="dataFim nao pode ser anterior a dataInicio."
        )


def _validar_transicao(status_atual: str, status_novo: str) -> None:
    if status_novo == status_atual:
        return
    permitidos = _TRANSICOES_VALIDAS.get(status_atual, frozenset())
    if status_novo not in permitidos:
        raise ErroDeAplicacao(
            CODIGO_TRANSICAO_INVALIDA,
            detalhe=f"Nao e possivel mudar de {status_atual!r} para {status_novo!r}.",
        )


async def _escopo_do_afastamento(
    sessao: AsyncSession, afastamento: Afastamento
) -> tuple[UUID, UUID | None]:
    """`(empresa_id, unidade_id)` efetivos do afastamento, para
    `PONTO-PER-001`. `empresa_id` vem sempre do colaborador (coluna
    obrigatoria); `unidade_id` so quando ha `vinculo_id` e o vinculo tem
    unidade (`vinculos.unidade_id` e opcional -- ver PCF, secao 2)."""
    colaborador = await sessao.get(Colaborador, afastamento.colaborador_id)
    if colaborador is None:
        raise ErroDeAplicacao(CODIGO_RECURSO_NAO_ENCONTRADO, detalhe="Colaborador nao encontrado.")
    unidade_id: UUID | None = None
    if afastamento.vinculo_id is not None:
        vinculo = await sessao.get(Vinculo, afastamento.vinculo_id)
        if vinculo is not None:
            unidade_id = vinculo.unidade_id
    return colaborador.empresa_id, unidade_id


# ---------------------------------------------------------------------------
# tipos_afastamento
# ---------------------------------------------------------------------------
async def listar_tipos_afastamento(
    sessao: AsyncSession,
    tenant_id: UUID,
    *,
    categoria: str | None = None,
    ativo: bool | None = None,
    cursor: str | None = None,
    limite: int | None = None,
    ordenar: str | None = None,
) -> tuple[Sequence[TipoAfastamento], esquemas.Paginacao]:
    ordenacao = interpretar_ordenar(
        ordenar, campos_aceitos=frozenset(_CAMPOS_ORDENACAO_TIPO), padrao="criadoEm"
    )
    limite_efetivo = normalizar_limite(limite)

    consulta = select(TipoAfastamento).where(
        TipoAfastamento.tenant_id == tenant_id, TipoAfastamento.excluido_em.is_(None)
    )
    if categoria is not None:
        consulta = consulta.where(TipoAfastamento.categoria == categoria)
    if ativo is not None:
        consulta = consulta.where(TipoAfastamento.ativo == ativo)

    campo = _CAMPOS_ORDENACAO_TIPO[ordenacao.campo]
    linhas, tem_mais = await executar_pagina(
        sessao,
        consulta,
        ordenacao=ordenacao,
        campo=campo,
        coluna_id=TipoAfastamento.id,
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


async def criar_tipo_afastamento(
    sessao: AsyncSession, tenant_id: UUID, dados: esquemas.TipoAfastamentoCriar
) -> TipoAfastamento:
    campos: dict[str, Any] = dados.model_dump(exclude_unset=True)
    if "categoria" in campos:
        campos["categoria"] = dados.categoria.value
    tipo = TipoAfastamento(tenant_id=tenant_id, **campos)
    sessao.add(tipo)
    try:
        await sessao.flush()
    except IntegrityError as exc:
        raise traduzir_integridade(exc, padrao=CODIGO_CORPO_INVALIDO) from exc
    return tipo


async def _obter_tipo_afastamento(
    sessao: AsyncSession, tenant_id: UUID, tipo_id: UUID
) -> TipoAfastamento:
    resultado = await sessao.execute(
        select(TipoAfastamento).where(
            TipoAfastamento.tenant_id == tenant_id,
            TipoAfastamento.id == tipo_id,
            TipoAfastamento.excluido_em.is_(None),
        )
    )
    tipo = resultado.scalar_one_or_none()
    if tipo is None:
        raise ErroDeAplicacao(
            CODIGO_RECURSO_NAO_ENCONTRADO, detalhe="Tipo de afastamento nao encontrado."
        )
    return tipo


async def atualizar_tipo_afastamento(
    sessao: AsyncSession,
    tenant_id: UUID,
    tipo_id: UUID,
    dados: esquemas.TipoAfastamentoAtualizar,
) -> TipoAfastamento:
    tipo = await _obter_tipo_afastamento(sessao, tenant_id, tipo_id)
    campos: dict[str, Any] = dados.model_dump(exclude_unset=True)
    if "categoria" in campos and dados.categoria is not None:
        campos["categoria"] = dados.categoria.value
    for campo, valor in campos.items():
        setattr(tipo, campo, valor)
    try:
        await sessao.flush()
    except IntegrityError as exc:
        raise traduzir_integridade(exc, padrao=CODIGO_CORPO_INVALIDO) from exc
    return tipo


# ---------------------------------------------------------------------------
# afastamentos
# ---------------------------------------------------------------------------
async def obter_afastamento(
    sessao: AsyncSession, tenant_id: UUID, afastamento_id: UUID
) -> Afastamento:
    resultado = await sessao.execute(
        select(Afastamento).where(
            Afastamento.tenant_id == tenant_id,
            Afastamento.id == afastamento_id,
            Afastamento.excluido_em.is_(None),
        )
    )
    afastamento = resultado.scalar_one_or_none()
    if afastamento is None:
        raise ErroDeAplicacao(CODIGO_RECURSO_NAO_ENCONTRADO, detalhe="Afastamento nao encontrado.")
    return afastamento


async def criar_afastamento(
    sessao: AsyncSession, tenant_id: UUID, dados: esquemas.AfastamentoCriar
) -> Afastamento:
    periodo_parcial = bool(dados.periodo_parcial)
    _validar_parcial(periodo_parcial, dados.hora_inicio, dados.hora_fim)
    _validar_periodo(dados.data_inicio, dados.data_fim)

    campos: dict[str, Any] = dados.model_dump(exclude_unset=True)
    if "origem" in campos and campos["origem"] is not None:
        campos["origem"] = dados.origem.value if dados.origem else None
    if "status" in campos and campos["status"] is not None:
        campos["status"] = dados.status.value if dados.status else None
    if "hora_inicio" in campos:
        campos["hora_inicio"] = _hora_ou_none(campos["hora_inicio"])
    if "hora_fim" in campos:
        campos["hora_fim"] = _hora_ou_none(campos["hora_fim"])

    afastamento = Afastamento(tenant_id=tenant_id, **campos)
    sessao.add(afastamento)
    try:
        await sessao.flush()
    except IntegrityError as exc:
        raise traduzir_integridade(exc, padrao=CODIGO_CORPO_INVALIDO) from exc
    return afastamento


async def atualizar_afastamento(
    sessao: AsyncSession,
    tenant_id: UUID,
    afastamento_id: UUID,
    dados: esquemas.AfastamentoAtualizar,
) -> Afastamento:
    afastamento = await obter_afastamento(sessao, tenant_id, afastamento_id)
    campos: dict[str, Any] = dados.model_dump(exclude_unset=True)

    periodo_parcial_efetivo = campos.get("periodo_parcial", afastamento.periodo_parcial)
    hora_inicio_efetiva = campos.get("hora_inicio", afastamento.hora_inicio)
    hora_fim_efetiva = campos.get("hora_fim", afastamento.hora_fim)
    _validar_parcial(bool(periodo_parcial_efetivo), hora_inicio_efetiva, hora_fim_efetiva)

    data_inicio_efetiva = campos.get("data_inicio", afastamento.data_inicio)
    data_fim_efetiva = campos.get("data_fim", afastamento.data_fim)
    _validar_periodo(data_inicio_efetiva, data_fim_efetiva)

    if "status" in campos and campos["status"] is not None:
        status_novo = dados.status.value if dados.status else campos["status"]
        _validar_transicao(afastamento.status, status_novo)
        campos["status"] = status_novo
    if "origem" in campos and campos["origem"] is not None:
        campos["origem"] = dados.origem.value if dados.origem else None
    if "hora_inicio" in campos:
        campos["hora_inicio"] = _hora_ou_none(campos["hora_inicio"])
    if "hora_fim" in campos:
        campos["hora_fim"] = _hora_ou_none(campos["hora_fim"])

    # PONTO-PER-001: so leitura de periodos/fechamentos (F10 ainda nao
    # existe -- nunca encontra nada hoje, mas o codigo precisa estar certo).
    empresa_id, unidade_id = await _escopo_do_afastamento(sessao, afastamento)
    await verificar_periodo_aberto(
        sessao, tenant_id, empresa_id=empresa_id, unidade_id=unidade_id, data=data_inicio_efetiva
    )

    for campo, valor in campos.items():
        setattr(afastamento, campo, valor)
    try:
        await sessao.flush()
    except IntegrityError as exc:
        raise traduzir_integridade(exc, padrao=CODIGO_CORPO_INVALIDO) from exc
    return afastamento


async def excluir_afastamento(sessao: AsyncSession, tenant_id: UUID, afastamento_id: UUID) -> None:
    """Exclusao logica. Nao agenda recalculo: nao existe evento nem fila
    para isso no catalogo desta fase (`events.yaml` nao tem `afastamento.*`
    nem `apuracao.*` -- lacuna do contrato registrada em `docs/backlog.md`,
    nao mecanismo novo inventado aqui)."""
    afastamento = await obter_afastamento(sessao, tenant_id, afastamento_id)
    afastamento.excluido_em = dt.datetime.now(tz=dt.UTC)
    await sessao.flush()


async def listar_afastamentos(
    sessao: AsyncSession,
    tenant_id: UUID,
    *,
    colaborador_id: UUID | None = None,
    vinculo_id: UUID | None = None,
    empresa_id: UUID | None = None,
    tipo_afastamento_id: UUID | None = None,
    status: str | None = None,
    de: dt.date | None = None,
    ate: dt.date | None = None,
    cursor: str | None = None,
    limite: int | None = None,
    ordenar: str | None = None,
) -> tuple[Sequence[Afastamento], esquemas.Paginacao]:
    ordenacao = interpretar_ordenar(
        ordenar, campos_aceitos=frozenset(_CAMPOS_ORDENACAO_AFASTAMENTO), padrao="criadoEm"
    )
    limite_efetivo = normalizar_limite(limite)

    consulta = select(Afastamento).where(
        Afastamento.tenant_id == tenant_id, Afastamento.excluido_em.is_(None)
    )
    if colaborador_id is not None:
        consulta = consulta.where(Afastamento.colaborador_id == colaborador_id)
    if vinculo_id is not None:
        consulta = consulta.where(Afastamento.vinculo_id == vinculo_id)
    if tipo_afastamento_id is not None:
        consulta = consulta.where(Afastamento.tipo_afastamento_id == tipo_afastamento_id)
    if status is not None:
        consulta = consulta.where(Afastamento.status == status)
    if empresa_id is not None:
        consulta = consulta.where(
            Afastamento.colaborador_id.in_(
                select(Colaborador.id).where(
                    Colaborador.tenant_id == tenant_id, Colaborador.empresa_id == empresa_id
                )
            )
        )
    if de is not None:
        consulta = consulta.where(
            sa.or_(Afastamento.data_fim.is_(None), Afastamento.data_fim >= de)
        )
    if ate is not None:
        consulta = consulta.where(Afastamento.data_inicio <= ate)

    campo = _CAMPOS_ORDENACAO_AFASTAMENTO[ordenacao.campo]
    linhas, tem_mais = await executar_pagina(
        sessao,
        consulta,
        ordenacao=ordenacao,
        campo=campo,
        coluna_id=Afastamento.id,
        cursor=cursor,
        limite=limite_efetivo,
    )
    atributo = "criado_em" if ordenacao.campo == "criadoEm" else "data_inicio"
    proximo_cursor = None
    if tem_mais and linhas:
        ultimo = linhas[-1]
        proximo_cursor = codificar_cursor(ordenacao, getattr(ultimo, atributo), ultimo.id)
    paginacao = montar_paginacao(
        proximo_cursor=proximo_cursor, tem_mais=tem_mais, limite=limite_efetivo
    )
    return linhas, paginacao
