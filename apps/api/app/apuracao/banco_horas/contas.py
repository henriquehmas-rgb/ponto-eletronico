"""CRUD de `bh_contas` (T5, tag `banco-horas`).

`criarContaBancoHoras` deriva `periodoFim` de `bh_politicas.periodo_meses` a
partir de `periodoInicio` quando o corpo nao informa `periodoFim`
explicitamente, e recusa `ck_bh_contas_periodo`/duplicidade `uq_bh_contas`
com `PONTO-CONF-001` (traducao de `IntegrityError`, ver `erros_bd.py`).

`colaboradorId` e opcional em `BhContaCriar` (o contrato so exige
`vinculoId`, `bhPoliticaId`, `codigo`, `periodoInicio`) porque o vinculo ja
sabe o colaborador -- quando omitido, e derivado de `vinculos.colaborador_id`.

Nao ha `atualizarContaBancoHoras`/`excluirContaBancoHoras` no contrato
(openapi.yaml, tag `banco-horas`) -- so listar e criar.
"""

from __future__ import annotations

import calendar
import datetime as dt
from collections.abc import Sequence
from uuid import UUID

from ponto_contracts import BhConta, Vinculo
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.apuracao.banco_horas.erros_bd import traduzir_integridade
from app.apuracao.banco_horas.paginacao import (
    CampoOrdenacao,
    codificar_cursor,
    executar_pagina,
    interpretar_ordenar,
    montar_paginacao,
    normalizar_limite,
)
from app.apuracao.banco_horas.politicas import obter_politica_banco_horas
from app.core.erros import ErroDeAplicacao
from app.schemas import contrato as esquemas

CODIGO_RECURSO_NAO_ENCONTRADO = "PONTO-REC-001"
CODIGO_CORPO_INVALIDO = "PONTO-VAL-001"

_CAMPOS_ORDENACAO: dict[str, CampoOrdenacao] = {
    "periodoFim": CampoOrdenacao(BhConta.periodo_fim, dt.date.fromisoformat),
    "saldoAtualMinutos": CampoOrdenacao(BhConta.saldo_atual_minutos, int),
}


def adicionar_meses(data: dt.date, meses: int) -> dt.date:
    """Soma `meses` a `data`, ajustando o dia para o ultimo dia do mes de
    destino quando o mes de origem nao existe la (ex.: 31/01 + 1 mes ->
    28/02 ou 29/02). Aritmetica de calendario pura, sem dependencia externa
    (`dateutil` nao e dependencia deste pacote)."""
    mes_total = data.month - 1 + meses
    ano = data.year + mes_total // 12
    mes = mes_total % 12 + 1
    dia = min(data.day, calendar.monthrange(ano, mes)[1])
    return dt.date(ano, mes, dia)


async def _obter_vinculo(sessao: AsyncSession, tenant_id: UUID, vinculo_id: UUID) -> Vinculo:
    resultado = await sessao.execute(
        select(Vinculo).where(Vinculo.id == vinculo_id, Vinculo.tenant_id == tenant_id)
    )
    vinculo = resultado.scalar_one_or_none()
    if vinculo is None:
        raise ErroDeAplicacao(CODIGO_RECURSO_NAO_ENCONTRADO, detalhe="Vinculo nao encontrado.")
    return vinculo


async def criar_conta_banco_horas(
    sessao: AsyncSession, tenant_id: UUID, corpo: esquemas.BhContaCriar
) -> BhConta:
    politica = await obter_politica_banco_horas(sessao, tenant_id, corpo.bh_politica_id)
    vinculo = await _obter_vinculo(sessao, tenant_id, corpo.vinculo_id)
    colaborador_id = corpo.colaborador_id or vinculo.colaborador_id

    periodo_fim = corpo.periodo_fim or (
        adicionar_meses(corpo.periodo_inicio, politica.periodo_meses) - dt.timedelta(days=1)
    )
    if periodo_fim <= corpo.periodo_inicio:
        raise ErroDeAplicacao(
            CODIGO_CORPO_INVALIDO, detalhe="periodoFim precisa ser posterior a periodoInicio."
        )

    conta = BhConta(
        tenant_id=tenant_id,
        colaborador_id=colaborador_id,
        vinculo_id=corpo.vinculo_id,
        bh_politica_id=corpo.bh_politica_id,
        codigo=corpo.codigo,
        nome=corpo.nome or f"Banco de horas ({corpo.codigo})",
        periodo_inicio=corpo.periodo_inicio,
        periodo_fim=periodo_fim,
        status=(corpo.status.value if corpo.status is not None else "aberta"),
    )
    sessao.add(conta)
    try:
        await sessao.flush()
    except IntegrityError as exc:
        raise traduzir_integridade(exc, padrao=CODIGO_CORPO_INVALIDO) from exc
    return conta


async def obter_conta_banco_horas(sessao: AsyncSession, tenant_id: UUID, conta_id: UUID) -> BhConta:
    resultado = await sessao.execute(
        select(BhConta).where(BhConta.id == conta_id, BhConta.tenant_id == tenant_id)
    )
    conta = resultado.scalar_one_or_none()
    if conta is None:
        raise ErroDeAplicacao(
            CODIGO_RECURSO_NAO_ENCONTRADO, detalhe="Conta de banco de horas nao encontrada."
        )
    return conta


async def listar_contas_banco_horas(
    sessao: AsyncSession,
    tenant_id: UUID,
    *,
    colaborador_id: UUID | None = None,
    vinculo_id: UUID | None = None,
    empresa_id: UUID | None = None,
    status: str | None = None,
    vence_ate: dt.date | None = None,
    com_saldo_negativo: bool | None = None,
    cursor: str | None = None,
    limite: int | None = None,
    ordenar: str | None = None,
) -> tuple[Sequence[BhConta], esquemas.Paginacao]:
    ordenacao = interpretar_ordenar(
        ordenar, campos_aceitos=frozenset(_CAMPOS_ORDENACAO), padrao="periodoFim"
    )
    limite_efetivo = normalizar_limite(limite)

    consulta = select(BhConta).where(BhConta.tenant_id == tenant_id)
    if colaborador_id is not None:
        consulta = consulta.where(BhConta.colaborador_id == colaborador_id)
    if vinculo_id is not None:
        consulta = consulta.where(BhConta.vinculo_id == vinculo_id)
    if empresa_id is not None:
        # `bh_contas` nao carrega `empresa_id` diretamente (so `vinculo_id`);
        # o escopo por empresa passa pelo vinculo dono da conta.
        consulta = consulta.join(Vinculo, Vinculo.id == BhConta.vinculo_id).where(
            Vinculo.empresa_id == empresa_id
        )
    if status is not None:
        consulta = consulta.where(BhConta.status == status)
    if vence_ate is not None:
        consulta = consulta.where(BhConta.periodo_fim <= vence_ate)
    if com_saldo_negativo:
        consulta = consulta.where(BhConta.saldo_atual_minutos < 0)

    campo = _CAMPOS_ORDENACAO[ordenacao.campo]
    linhas, tem_mais = await executar_pagina(
        sessao,
        consulta,
        ordenacao=ordenacao,
        campo=campo,
        coluna_id=BhConta.id,
        cursor=cursor,
        limite=limite_efetivo,
    )
    atributo = "periodo_fim" if ordenacao.campo == "periodoFim" else "saldo_atual_minutos"
    proximo_cursor = None
    if tem_mais and linhas:
        ultimo = linhas[-1]
        proximo_cursor = codificar_cursor(ordenacao, getattr(ultimo, atributo), ultimo.id)
    paginacao = montar_paginacao(
        proximo_cursor=proximo_cursor, tem_mais=tem_mais, limite=limite_efetivo
    )
    return linhas, paginacao
