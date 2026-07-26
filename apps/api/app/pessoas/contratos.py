"""Servicos de dominio dos recursos `contratos` e `vinculos`.

`contratos` e o INSTRUMENTO JURIDICO entre colaborador e empresa (tipo de
contratacao, cargo, salario, carga contratada, a clausula do art. 62 da
CLT). `vinculos` e a RELACAO DE TRABALHO operacional, na granularidade que o
eSocial e o AEJ exigem -- **todo o motor de apuracao das fases seguintes
pendura em `vinculo_id`, nunca em `colaborador_id`**. Um contrato origina um
vinculo; a criacao e o encerramento de vinculo publicam, respectivamente,
`colaborador.admitido` e `colaborador.demitido`.
"""

from __future__ import annotations

import datetime as dt
import decimal
from collections.abc import Sequence
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from ponto_contracts import Colaborador, Contrato, Vinculo
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.erros import ErroDeAplicacao
from app.pessoas import eventos
from app.pessoas.erros_bd import traduzir_integridade
from app.pessoas.paginacao import (
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

_CAMPOS_ORDENACAO_CONTRATO: dict[str, CampoOrdenacao] = {
    "criadoEm": CampoOrdenacao(Contrato.criado_em, dt.datetime.fromisoformat),
    "dataInicio": CampoOrdenacao(Contrato.data_inicio, dt.date.fromisoformat),
}
_CAMPOS_ORDENACAO_VINCULO: dict[str, CampoOrdenacao] = {
    "criadoEm": CampoOrdenacao(Vinculo.criado_em, dt.datetime.fromisoformat),
    "dataInicio": CampoOrdenacao(Vinculo.data_inicio, dt.date.fromisoformat),
}


def _decimal_ou_none(valor: float | None) -> decimal.Decimal | None:
    """`ContratoCriar.salario` chega como `float` (JSON nao tem `Decimal`);
    a coluna e `NUMERIC(14,2)` e o driver assincrono exige o tipo exato."""
    if valor is None:
        return None
    return decimal.Decimal(str(valor))


def _validar_dispensa_controle(
    controle_jornada: bool | None, dispensa_controle_motivo: Any | None
) -> None:
    """Espelha `ck_contratos_dispensa` em app: falso dispensa o controle de
    ponto (art. 62 da CLT) e exige o motivo; verdadeiro (ou ausente, que o
    banco assume `TRUE`) proibe o motivo."""
    if controle_jornada is False and dispensa_controle_motivo is None:
        raise ErroDeAplicacao(
            CODIGO_CORPO_INVALIDO,
            detalhe="dispensaControleMotivo e obrigatorio quando controleJornada e falso "
            "(art. 62 da CLT).",
        )
    if controle_jornada is not False and dispensa_controle_motivo is not None:
        raise ErroDeAplicacao(
            CODIGO_CORPO_INVALIDO,
            detalhe="dispensaControleMotivo so e aceito quando controleJornada e falso.",
        )


# ---------------------------------------------------------------------------
# Contratos
# ---------------------------------------------------------------------------
async def obter_contrato(sessao: AsyncSession, contrato_id: UUID) -> Contrato:
    resultado = await sessao.execute(
        select(Contrato).where(Contrato.id == contrato_id, Contrato.excluido_em.is_(None))
    )
    contrato = resultado.scalar_one_or_none()
    if contrato is None:
        raise ErroDeAplicacao(CODIGO_RECURSO_NAO_ENCONTRADO, detalhe="Contrato nao encontrado.")
    return contrato


async def criar_contrato(
    sessao: AsyncSession, tenant_id: UUID, dados: esquemas.ContratoCriar
) -> Contrato:
    _validar_dispensa_controle(dados.controle_jornada, dados.dispensa_controle_motivo)
    campos: dict[str, Any] = dados.model_dump(exclude_unset=True)
    if "dispensa_controle_motivo" in campos and campos["dispensa_controle_motivo"] is not None:
        campos["dispensa_controle_motivo"] = campos["dispensa_controle_motivo"].value
    if "salario" in campos:
        campos["salario"] = _decimal_ou_none(campos["salario"])
    contrato = Contrato(tenant_id=tenant_id, **campos)
    sessao.add(contrato)
    try:
        await sessao.flush()
    except IntegrityError as exc:
        raise traduzir_integridade(exc, padrao=CODIGO_CORPO_INVALIDO) from exc
    return contrato


async def atualizar_contrato(
    sessao: AsyncSession, contrato_id: UUID, dados: esquemas.ContratoAtualizar
) -> Contrato:
    contrato = await obter_contrato(sessao, contrato_id)
    campos: dict[str, Any] = dados.model_dump(exclude_unset=True)

    controle_jornada = campos.get("controle_jornada", contrato.controle_jornada)
    dispensa_motivo_bruto = campos.get(
        "dispensa_controle_motivo", contrato.dispensa_controle_motivo
    )
    _validar_dispensa_controle(
        controle_jornada,
        dispensa_motivo_bruto.value
        if hasattr(dispensa_motivo_bruto, "value")
        else dispensa_motivo_bruto,
    )
    if "dispensa_controle_motivo" in campos and campos["dispensa_controle_motivo"] is not None:
        campos["dispensa_controle_motivo"] = campos["dispensa_controle_motivo"].value
    if "salario" in campos:
        campos["salario"] = _decimal_ou_none(campos["salario"])

    for campo, valor in campos.items():
        setattr(contrato, campo, valor)
    try:
        await sessao.flush()
    except IntegrityError as exc:
        raise traduzir_integridade(exc, padrao=CODIGO_CORPO_INVALIDO) from exc
    return contrato


async def listar_contratos(
    sessao: AsyncSession,
    tenant_id: UUID,
    *,
    colaborador_id: UUID | None = None,
    empresa_id: UUID | None = None,
    tipo: str | None = None,
    status: str | None = None,
    vigente_em: dt.date | None = None,
    cursor: str | None = None,
    limite: int | None = None,
    ordenar: str | None = None,
) -> tuple[Sequence[Contrato], esquemas.Paginacao]:
    ordenacao = interpretar_ordenar(
        ordenar, campos_aceitos=frozenset(_CAMPOS_ORDENACAO_CONTRATO), padrao="criadoEm"
    )
    limite_efetivo = normalizar_limite(limite)

    consulta = select(Contrato).where(
        Contrato.tenant_id == tenant_id, Contrato.excluido_em.is_(None)
    )
    if colaborador_id is not None:
        consulta = consulta.where(Contrato.colaborador_id == colaborador_id)
    if empresa_id is not None:
        consulta = consulta.where(Contrato.empresa_id == empresa_id)
    if tipo is not None:
        consulta = consulta.where(Contrato.tipo == tipo)
    if status is not None:
        consulta = consulta.where(Contrato.status == status)
    if vigente_em is not None:
        consulta = consulta.where(
            Contrato.data_inicio <= vigente_em,
            sa.or_(Contrato.data_fim.is_(None), Contrato.data_fim >= vigente_em),
        )

    campo = _CAMPOS_ORDENACAO_CONTRATO[ordenacao.campo]
    linhas, tem_mais = await executar_pagina(
        sessao,
        consulta,
        ordenacao=ordenacao,
        campo=campo,
        coluna_id=Contrato.id,
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


# ---------------------------------------------------------------------------
# Vinculos
# ---------------------------------------------------------------------------
async def obter_vinculo(sessao: AsyncSession, vinculo_id: UUID) -> Vinculo:
    resultado = await sessao.execute(
        select(Vinculo).where(Vinculo.id == vinculo_id, Vinculo.excluido_em.is_(None))
    )
    vinculo = resultado.scalar_one_or_none()
    if vinculo is None:
        raise ErroDeAplicacao(CODIGO_RECURSO_NAO_ENCONTRADO, detalhe="Vinculo nao encontrado.")
    return vinculo


async def criar_vinculo(
    sessao: AsyncSession, tenant_id: UUID, dados: esquemas.VinculoCriar
) -> Vinculo:
    """Cria o vinculo. `ex_vinculos_sobreposicao` (`EXCLUDE ... WHERE
    tenant_id, colaborador_id, empresa_id`) recusa dois vinculos ativos
    sobrepostos do MESMO colaborador na MESMA empresa (`PONTO-VAL-010`) e
    aceita vinculos simultaneos em empresas diferentes do mesmo tenant, por
    nao entrarem na mesma particao da exclusao.

    Publica `colaborador.admitido` quando o vinculo nasce com `status`
    ativo (o padrao do contrato).
    """
    campos: dict[str, Any] = dados.model_dump(exclude_unset=True)
    vinculo = Vinculo(tenant_id=tenant_id, **campos)
    sessao.add(vinculo)
    try:
        await sessao.flush()
    except IntegrityError as exc:
        raise traduzir_integridade(exc, padrao=CODIGO_CORPO_INVALIDO) from exc

    if vinculo.status == "ativo":
        colaborador = await sessao.get(Colaborador, vinculo.colaborador_id)
        eventos.publicar_colaborador_admitido(
            tenant_id=tenant_id,
            colaborador_id=vinculo.colaborador_id,
            vinculo_id=vinculo.id,
            empresa_id=vinculo.empresa_id,
            matricula=colaborador.matricula if colaborador else "",
            cpf=colaborador.cpf if colaborador else "",
            data_inicio=vinculo.data_inicio,
            unidade_id=vinculo.unidade_id,
            matricula_esocial=vinculo.matricula_esocial,
            nome_completo=(
                (colaborador.nome_social or colaborador.nome_completo) if colaborador else None
            ),
            cargo_id=vinculo.cargo_id,
            apura_ponto=vinculo.apura_ponto,
        )
    return vinculo


async def listar_vinculos(
    sessao: AsyncSession,
    tenant_id: UUID,
    *,
    colaborador_id: UUID | None = None,
    empresa_id: UUID | None = None,
    unidade_id: UUID | None = None,
    status: str | None = None,
    apura_ponto: bool | None = None,
    vigente_em: dt.date | None = None,
    cursor: str | None = None,
    limite: int | None = None,
    ordenar: str | None = None,
) -> tuple[Sequence[Vinculo], esquemas.Paginacao]:
    ordenacao = interpretar_ordenar(
        ordenar, campos_aceitos=frozenset(_CAMPOS_ORDENACAO_VINCULO), padrao="criadoEm"
    )
    limite_efetivo = normalizar_limite(limite)

    consulta = select(Vinculo).where(Vinculo.tenant_id == tenant_id, Vinculo.excluido_em.is_(None))
    if colaborador_id is not None:
        consulta = consulta.where(Vinculo.colaborador_id == colaborador_id)
    if empresa_id is not None:
        consulta = consulta.where(Vinculo.empresa_id == empresa_id)
    if unidade_id is not None:
        consulta = consulta.where(Vinculo.unidade_id == unidade_id)
    if status is not None:
        consulta = consulta.where(Vinculo.status == status)
    if apura_ponto is not None:
        consulta = consulta.where(Vinculo.apura_ponto == apura_ponto)
    if vigente_em is not None:
        consulta = consulta.where(
            Vinculo.data_inicio <= vigente_em,
            sa.or_(Vinculo.data_fim.is_(None), Vinculo.data_fim >= vigente_em),
        )

    campo = _CAMPOS_ORDENACAO_VINCULO[ordenacao.campo]
    linhas, tem_mais = await executar_pagina(
        sessao,
        consulta,
        ordenacao=ordenacao,
        campo=campo,
        coluna_id=Vinculo.id,
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


async def encerrar_vinculo(
    sessao: AsyncSession,
    tenant_id: UUID,
    vinculo_id: UUID,
    dados: esquemas.EncerramentoVinculoRequisicao,
) -> Vinculo:
    """Registra o desligamento: define `data_fim`, `motivo_desligamento` e
    muda `status` para `encerrado`. Publica `colaborador.demitido`.

    A quitacao de banco de horas (`quitarBancoHoras`) e o acerto na folha
    (`competenciaFolha`) sao do dominio de banco de horas e de folha -- fora
    do escopo desta fase; aqui so acusamos que o pedido foi recebido, sem
    implementar o calculo.
    """
    vinculo = await obter_vinculo(sessao, vinculo_id)
    if vinculo.status == "encerrado":
        raise ErroDeAplicacao("PONTO-CONF-003", detalhe="Vinculo ja esta encerrado.")
    data_fim = dados.data_fim or dt.date.today()
    if data_fim < vinculo.data_inicio:
        raise ErroDeAplicacao(
            CODIGO_CORPO_INVALIDO, detalhe="dataFim nao pode ser anterior ao inicio do vinculo."
        )
    vinculo.data_fim = data_fim
    vinculo.motivo_desligamento = dados.motivo_desligamento
    vinculo.status = "encerrado"
    try:
        await sessao.flush()
    except IntegrityError as exc:
        raise traduzir_integridade(exc, padrao=CODIGO_CORPO_INVALIDO) from exc

    colaborador = await sessao.get(Colaborador, vinculo.colaborador_id)
    eventos.publicar_colaborador_demitido(
        tenant_id=tenant_id,
        colaborador_id=vinculo.colaborador_id,
        vinculo_id=vinculo.id,
        empresa_id=vinculo.empresa_id,
        data_fim=data_fim,
        matricula=colaborador.matricula if colaborador else None,
        motivo_desligamento=vinculo.motivo_desligamento,
    )
    return vinculo
