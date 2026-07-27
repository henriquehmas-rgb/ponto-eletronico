"""Lado de leitura da tag `apuracoes`: `listarApuracoes`, `obterApuracao`,
`listarOcorrencias` (as 3 operacoes desta tag que sao ownership de A1 --
`recalcularApuracoes`/`atualizarOcorrencia` sao de A3).

Nunca escreve. `listarApuracoes`/`listarOcorrencias` usam a paginacao por
cursor propria deste dominio (`app.apuracao.dominio.paginacao`).
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from uuid import UUID

import sqlalchemy as sa
from ponto_contracts import ApuracaoComponente as ApuracaoComponenteOrm
from ponto_contracts import ApuracaoDia as ApuracaoDiaOrm
from ponto_contracts import EquipeMembro, Vinculo
from ponto_contracts import Ocorrencia as OcorrenciaOrm
from sqlalchemy.ext.asyncio import AsyncSession

from app.apuracao.dominio.paginacao import (
    CampoOrdenacao,
    codificar_cursor,
    executar_pagina,
    interpretar_ordenar,
    montar_paginacao,
    normalizar_limite,
)
from app.core.erros import ErroDeAplicacao
from app.schemas import contrato as esquemas

CODIGO_RECURSO_NAO_ENCONTRADO = "PONTO-REC-001"
CODIGO_INTERVALO_INVALIDO = "PONTO-VAL-007"

#: `status` que contam como "inconsistente" para `somenteInconsistentes`
#: (descricao do parametro no contrato: "marcacao impar, ocorrencia aberta
#: ou apuracao pendente" -- `com_ocorrencia` e como este modulo grava toda
#: apuracao que abriu ocorrencia, ver `servico.py`).
_STATUS_INCONSISTENTE = ("pendente", "com_ocorrencia")

_CAMPOS_ORDENACAO_APURACAO: dict[str, CampoOrdenacao] = {
    "data": CampoOrdenacao(ApuracaoDiaOrm.data, dt.date.fromisoformat),
    "colaboradorId": CampoOrdenacao(ApuracaoDiaOrm.colaborador_id, UUID),
}
_CAMPOS_ORDENACAO_OCORRENCIA: dict[str, CampoOrdenacao] = {
    "data": CampoOrdenacao(OcorrenciaOrm.data, dt.date.fromisoformat),
    "severidade": CampoOrdenacao(OcorrenciaOrm.severidade, str),
}


async def _montar_apuracao_schema(
    sessao: AsyncSession, linha: ApuracaoDiaOrm, *, incluir_componentes: bool
) -> esquemas.ApuracaoDia:
    dados = esquemas.ApuracaoDia.model_validate(linha, from_attributes=True)
    if not incluir_componentes:
        return dados
    componentes_orm = list(
        (
            await sessao.execute(
                sa.select(ApuracaoComponenteOrm).where(
                    ApuracaoComponenteOrm.apuracao_dia_id == linha.id
                )
            )
        )
        .scalars()
        .all()
    )
    componentes = [
        esquemas.ApuracaoComponente.model_validate(c, from_attributes=True) for c in componentes_orm
    ]
    return dados.model_copy(update={"componentes": componentes})


async def listar_apuracoes(
    sessao: AsyncSession,
    tenant_id: UUID,
    *,
    de: dt.date,
    ate: dt.date,
    empresa_id: UUID | None = None,
    unidade_id: UUID | None = None,
    departamento_id: UUID | None = None,
    equipe_id: UUID | None = None,
    colaborador_id: UUID | None = None,
    vinculo_id: UUID | None = None,
    status: str | None = None,
    somente_inconsistentes: bool | None = None,
    incluir_componentes: bool | None = None,
    cursor: str | None = None,
    limite: int | None = None,
    ordenar: str | None = None,
) -> tuple[Sequence[esquemas.ApuracaoDia], esquemas.Paginacao]:
    if ate < de:
        raise ErroDeAplicacao(CODIGO_INTERVALO_INVALIDO, detalhe="ate nao pode ser anterior a de.")
    ordenacao = interpretar_ordenar(
        ordenar, campos_aceitos=frozenset(_CAMPOS_ORDENACAO_APURACAO), padrao="data"
    )
    limite_efetivo = normalizar_limite(limite)

    consulta = sa.select(ApuracaoDiaOrm).where(
        ApuracaoDiaOrm.tenant_id == tenant_id,
        ApuracaoDiaOrm.data >= de,
        ApuracaoDiaOrm.data <= ate,
    )
    if empresa_id is not None:
        consulta = consulta.where(ApuracaoDiaOrm.empresa_id == empresa_id)
    if unidade_id is not None:
        consulta = consulta.where(ApuracaoDiaOrm.unidade_id == unidade_id)
    if departamento_id is not None:
        consulta = consulta.where(ApuracaoDiaOrm.departamento_id == departamento_id)
    if colaborador_id is not None:
        consulta = consulta.where(ApuracaoDiaOrm.colaborador_id == colaborador_id)
    if vinculo_id is not None:
        consulta = consulta.where(ApuracaoDiaOrm.vinculo_id == vinculo_id)
    if status is not None:
        consulta = consulta.where(ApuracaoDiaOrm.status == status)
    if somente_inconsistentes:
        consulta = consulta.where(
            sa.or_(
                ApuracaoDiaOrm.marcacoes_impares.is_(True),
                ApuracaoDiaOrm.status.in_(_STATUS_INCONSISTENTE),
            )
        )
    if equipe_id is not None:
        # `apuracoes_dia` nao tem `equipe_id` (equipe e ortogonal a
        # departamento, tabela `equipe_membros`) -- filtra por participacao
        # que se sobrepoe ao intervalo `[de, ate]` consultado.
        consulta = consulta.where(
            sa.exists(
                sa.select(1).where(
                    EquipeMembro.tenant_id == tenant_id,
                    EquipeMembro.equipe_id == equipe_id,
                    EquipeMembro.colaborador_id == ApuracaoDiaOrm.colaborador_id,
                    EquipeMembro.vigencia_inicio <= ate,
                    sa.or_(EquipeMembro.vigencia_fim.is_(None), EquipeMembro.vigencia_fim >= de),
                )
            )
        )

    campo = _CAMPOS_ORDENACAO_APURACAO[ordenacao.campo]
    linhas, tem_mais = await executar_pagina(
        sessao,
        consulta,
        ordenacao=ordenacao,
        campo=campo,
        coluna_id=ApuracaoDiaOrm.id,
        cursor=cursor,
        limite=limite_efetivo,
    )
    atributo = "data" if ordenacao.campo == "data" else "colaborador_id"
    proximo_cursor = None
    if tem_mais and linhas:
        ultimo = linhas[-1]
        proximo_cursor = codificar_cursor(ordenacao, getattr(ultimo, atributo), ultimo.id)
    paginacao = montar_paginacao(
        proximo_cursor=proximo_cursor, tem_mais=tem_mais, limite=limite_efetivo
    )
    dados = [
        await _montar_apuracao_schema(sessao, linha, incluir_componentes=bool(incluir_componentes))
        for linha in linhas
    ]
    return dados, paginacao


async def obter_apuracao(sessao: AsyncSession, apuracao_id: UUID) -> esquemas.ApuracaoDia:
    linha = await sessao.get(ApuracaoDiaOrm, apuracao_id)
    if linha is None:
        raise ErroDeAplicacao(CODIGO_RECURSO_NAO_ENCONTRADO, detalhe="Apuracao nao encontrada.")
    return await _montar_apuracao_schema(sessao, linha, incluir_componentes=True)


async def listar_ocorrencias(
    sessao: AsyncSession,
    tenant_id: UUID,
    *,
    empresa_id: UUID | None = None,
    unidade_id: UUID | None = None,
    colaborador_id: UUID | None = None,
    codigo: str | None = None,
    severidade: str | None = None,
    status: str | None = None,
    de: dt.date | None = None,
    ate: dt.date | None = None,
    cursor: str | None = None,
    limite: int | None = None,
    ordenar: str | None = None,
) -> tuple[Sequence[esquemas.Ocorrencia], esquemas.Paginacao]:
    ordenacao = interpretar_ordenar(
        ordenar, campos_aceitos=frozenset(_CAMPOS_ORDENACAO_OCORRENCIA), padrao="data"
    )
    limite_efetivo = normalizar_limite(limite)

    consulta = sa.select(OcorrenciaOrm).where(OcorrenciaOrm.tenant_id == tenant_id)
    if empresa_id is not None or unidade_id is not None:
        consulta = consulta.join(Vinculo, Vinculo.id == OcorrenciaOrm.vinculo_id)
        if empresa_id is not None:
            consulta = consulta.where(Vinculo.empresa_id == empresa_id)
        if unidade_id is not None:
            consulta = consulta.where(Vinculo.unidade_id == unidade_id)
    if colaborador_id is not None:
        consulta = consulta.where(OcorrenciaOrm.colaborador_id == colaborador_id)
    if codigo is not None:
        consulta = consulta.where(OcorrenciaOrm.codigo == codigo)
    if severidade is not None:
        consulta = consulta.where(OcorrenciaOrm.severidade == severidade)
    if status is not None:
        consulta = consulta.where(OcorrenciaOrm.status == status)
    if de is not None:
        consulta = consulta.where(OcorrenciaOrm.data >= de)
    if ate is not None:
        consulta = consulta.where(OcorrenciaOrm.data <= ate)

    campo = _CAMPOS_ORDENACAO_OCORRENCIA[ordenacao.campo]
    linhas, tem_mais = await executar_pagina(
        sessao,
        consulta,
        ordenacao=ordenacao,
        campo=campo,
        coluna_id=OcorrenciaOrm.id,
        cursor=cursor,
        limite=limite_efetivo,
    )
    atributo = "data" if ordenacao.campo == "data" else "severidade"
    proximo_cursor = None
    if tem_mais and linhas:
        ultimo = linhas[-1]
        proximo_cursor = codificar_cursor(ordenacao, getattr(ultimo, atributo), ultimo.id)
    paginacao = montar_paginacao(
        proximo_cursor=proximo_cursor, tem_mais=tem_mais, limite=limite_efetivo
    )
    dados = [esquemas.Ocorrencia.model_validate(linha, from_attributes=True) for linha in linhas]
    return dados, paginacao
