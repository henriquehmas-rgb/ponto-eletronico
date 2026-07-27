"""Extrato, saldo e simulador de banco de horas (T6, tag `banco-horas`).

`obterExtratoBancoHoras` e `obterSaldoBancoHoras` resolvem primeiro qual
`bh_conta` responder: filtro explicito (`contaId`, ou `contaCodigo` +
`vinculoId`) tem prioridade; sem filtro, a conta de codigo `normal` do
colaborador (a mais comum), senao a conta mais recente por `periodoInicio`.
Colaborador sem nenhuma conta correspondente aos filtros e `PONTO-REC-001`.

`simularBancoHoras` NUNCA GRAVA NADA -- clona o calculo em memoria (nenhuma
chamada a `sessao.add`/`flush` neste modulo, exceto no proprio
`obter_extrato_banco_horas`/`obter_saldo_banco_horas`, que tambem so leem).
"""

from __future__ import annotations

import datetime as dt
from uuid import UUID

import sqlalchemy as sa
from ponto_contracts import BhConta, BhLancamento, BhPolitica
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.apuracao.banco_horas.hash_chain import aplicar_fator
from app.apuracao.banco_horas.paginacao import (
    CampoOrdenacao,
    Ordenacao,
    codificar_cursor,
    executar_pagina,
    montar_paginacao,
    normalizar_limite,
)
from app.core.erros import ErroDeAplicacao
from app.schemas import contrato as esquemas

CODIGO_RECURSO_NAO_ENCONTRADO = "PONTO-REC-001"
CODIGO_CORPO_INVALIDO = "PONTO-VAL-001"

#: `bh_contas.codigo` preferido quando a consulta nao restringe a uma conta
#: especifica -- a conta "principal" do colaborador na pratica do produto
#: (`PROJETO.md` §4.3).
_CODIGO_CONTA_PADRAO = "normal"


async def _resolver_conta(
    sessao: AsyncSession,
    tenant_id: UUID,
    colaborador_id: UUID,
    *,
    vinculo_id: UUID | None = None,
    conta_id: UUID | None = None,
    conta_codigo: str | None = None,
) -> BhConta:
    base = select(BhConta).where(
        BhConta.tenant_id == tenant_id, BhConta.colaborador_id == colaborador_id
    )
    if vinculo_id is not None:
        base = base.where(BhConta.vinculo_id == vinculo_id)

    if conta_id is not None:
        consulta = base.where(BhConta.id == conta_id)
    elif conta_codigo is not None:
        consulta = base.where(BhConta.codigo == conta_codigo)
    else:
        resultado_padrao = await sessao.execute(
            base.where(BhConta.codigo == _CODIGO_CONTA_PADRAO)
            .order_by(BhConta.periodo_inicio.desc())
            .limit(1)
        )
        conta = resultado_padrao.scalar_one_or_none()
        if conta is not None:
            return conta
        consulta = base

    resultado = await sessao.execute(consulta.order_by(BhConta.periodo_inicio.desc()).limit(1))
    conta = resultado.scalar_one_or_none()
    if conta is None:
        raise ErroDeAplicacao(
            CODIGO_RECURSO_NAO_ENCONTRADO,
            detalhe="Nenhuma conta de banco de horas encontrada para os filtros informados.",
        )
    return conta


async def carregar_politica(sessao: AsyncSession, tenant_id: UUID, politica_id: UUID) -> BhPolitica:
    resultado = await sessao.execute(
        select(BhPolitica).where(BhPolitica.id == politica_id, BhPolitica.tenant_id == tenant_id)
    )
    politica = resultado.scalar_one_or_none()
    if politica is None:
        raise ErroDeAplicacao(
            CODIGO_RECURSO_NAO_ENCONTRADO, detalhe="Politica de banco de horas nao encontrada."
        )
    return politica


async def _ultimo_lancamento(
    sessao: AsyncSession, tenant_id: UUID, conta_id: UUID, *, ate: dt.date | None = None
) -> BhLancamento | None:
    consulta = select(BhLancamento).where(
        BhLancamento.tenant_id == tenant_id, BhLancamento.bh_conta_id == conta_id
    )
    if ate is not None:
        consulta = consulta.where(BhLancamento.data_competencia <= ate)
    consulta = consulta.order_by(BhLancamento.sequencia.desc()).limit(1)
    resultado = await sessao.execute(consulta)
    return resultado.scalar_one_or_none()


async def _minutos_a_vencer(
    sessao: AsyncSession, tenant_id: UUID, conta_id: UUID, referencia: dt.date, dias: int
) -> int:
    """Soma de `minutos_equivalentes - consumido_minutos` dos creditos com
    `vence_em` dentro de `[referencia, referencia + dias]` -- so a parte
    ainda nao consumida de cada credito conta (o que o FIFO/LIFO ja
    consumiu nao "vence" mais, ja foi usado)."""
    if dias < 0:
        return 0
    limite = referencia + dt.timedelta(days=dias)
    consulta = select(
        sa.func.coalesce(
            sa.func.sum(BhLancamento.minutos_equivalentes - BhLancamento.consumido_minutos), 0
        )
    ).where(
        BhLancamento.tenant_id == tenant_id,
        BhLancamento.bh_conta_id == conta_id,
        BhLancamento.tipo == "credito",
        BhLancamento.vence_em.is_not(None),
        BhLancamento.vence_em >= referencia,
        BhLancamento.vence_em <= limite,
        BhLancamento.minutos_equivalentes > BhLancamento.consumido_minutos,
    )
    resultado = await sessao.execute(consulta)
    return int(resultado.scalar_one())


async def obter_extrato_banco_horas(
    sessao: AsyncSession,
    tenant_id: UUID,
    colaborador_id: UUID,
    *,
    vinculo_id: UUID | None = None,
    conta_id: UUID | None = None,
    conta_codigo: str | None = None,
    de: dt.date | None = None,
    ate: dt.date | None = None,
    tipo: str | None = None,
    cursor: str | None = None,
    limite: int | None = None,
) -> esquemas.ExtratoBancoHoras:
    conta = await _resolver_conta(
        sessao,
        tenant_id,
        colaborador_id,
        vinculo_id=vinculo_id,
        conta_id=conta_id,
        conta_codigo=conta_codigo,
    )
    limite_efetivo = normalizar_limite(limite)
    ordenacao = Ordenacao(campo="sequencia", direcao="asc")
    campo = CampoOrdenacao(BhLancamento.sequencia, int)

    consulta = select(BhLancamento).where(
        BhLancamento.tenant_id == tenant_id, BhLancamento.bh_conta_id == conta.id
    )
    if de is not None:
        consulta = consulta.where(BhLancamento.data_competencia >= de)
    if ate is not None:
        consulta = consulta.where(BhLancamento.data_competencia <= ate)
    if tipo is not None:
        consulta = consulta.where(BhLancamento.tipo == tipo)

    linhas, tem_mais = await executar_pagina(
        sessao,
        consulta,
        ordenacao=ordenacao,
        campo=campo,
        coluna_id=BhLancamento.id,
        cursor=cursor,
        limite=limite_efetivo,
    )
    proximo_cursor = None
    if tem_mais and linhas:
        ultimo = linhas[-1]
        proximo_cursor = codificar_cursor(ordenacao, ultimo.sequencia, ultimo.id)
    paginacao = montar_paginacao(
        proximo_cursor=proximo_cursor, tem_mais=tem_mais, limite=limite_efetivo
    )

    # Agregados por tipo dentro do intervalo de datas (independentes do
    # filtro `tipo`, que so restringe a LISTAGEM paginada acima).
    agregados_consulta = select(
        BhLancamento.tipo,
        sa.func.coalesce(sa.func.sum(BhLancamento.minutos_equivalentes), 0),
    ).where(BhLancamento.tenant_id == tenant_id, BhLancamento.bh_conta_id == conta.id)
    if de is not None:
        agregados_consulta = agregados_consulta.where(BhLancamento.data_competencia >= de)
    if ate is not None:
        agregados_consulta = agregados_consulta.where(BhLancamento.data_competencia <= ate)
    agregados_consulta = agregados_consulta.group_by(BhLancamento.tipo)
    resultado_agregados = await sessao.execute(agregados_consulta)
    somas: dict[str, int] = {linha[0]: linha[1] for linha in resultado_agregados.all()}

    creditos = somas.get("credito", 0)
    debitos = abs(somas.get("debito", 0))
    quitacoes = abs(somas.get("quitacao", 0))
    expiracoes = abs(somas.get("expiracao", 0))

    saldo_inicial = 0
    if de is not None:
        anterior = await _ultimo_lancamento(
            sessao, tenant_id, conta.id, ate=de - dt.timedelta(days=1)
        )
        saldo_inicial = anterior.saldo_apos_minutos if anterior is not None else 0

    ultimo_no_intervalo = await _ultimo_lancamento(sessao, tenant_id, conta.id, ate=ate)
    saldo_final = (
        ultimo_no_intervalo.saldo_apos_minutos if ultimo_no_intervalo is not None else saldo_inicial
    )

    return esquemas.ExtratoBancoHoras(
        colaboradorId=colaborador_id,
        vinculoId=conta.vinculo_id,
        contaId=conta.id,
        contaCodigo=conta.codigo,
        periodoInicio=de or conta.periodo_inicio,
        periodoFim=ate or conta.periodo_fim,
        saldoInicialMinutos=saldo_inicial,
        creditosMinutos=creditos,
        debitosMinutos=debitos,
        quitacoesMinutos=quitacoes,
        expiracoesMinutos=expiracoes,
        saldoFinalMinutos=saldo_final,
        lancamentos=[
            esquemas.BhLancamento.model_validate(linha, from_attributes=True) for linha in linhas
        ],
        paginacao=paginacao,
    )


async def obter_saldo_banco_horas(
    sessao: AsyncSession,
    tenant_id: UUID,
    colaborador_id: UUID,
    *,
    vinculo_id: UUID | None = None,
    conta_codigo: str | None = None,
    data_referencia: dt.date | None = None,
) -> esquemas.SaldoBancoHoras:
    conta = await _resolver_conta(
        sessao, tenant_id, colaborador_id, vinculo_id=vinculo_id, conta_codigo=conta_codigo
    )
    politica = await carregar_politica(sessao, tenant_id, conta.bh_politica_id)

    hoje = dt.date.today()
    referencia = data_referencia or hoje
    if data_referencia is not None and data_referencia != hoje:
        # Saldo HISTORICO: reconstroi a partir do ultimo lancamento ate a
        # data pedida -- `bh_contas.saldo_atual_minutos` so materializa o
        # saldo CORRENTE.
        ultimo = await _ultimo_lancamento(sessao, tenant_id, conta.id, ate=data_referencia)
        saldo_minutos = ultimo.saldo_apos_minutos if ultimo is not None else 0
    else:
        saldo_minutos = conta.saldo_atual_minutos

    a_vencer_30 = await _minutos_a_vencer(sessao, tenant_id, conta.id, referencia, 30)
    a_vencer_15 = await _minutos_a_vencer(sessao, tenant_id, conta.id, referencia, 15)
    a_vencer_7 = await _minutos_a_vencer(sessao, tenant_id, conta.id, referencia, 7)
    dias_ate_fim_periodo = (conta.periodo_fim - referencia).days
    projecao = await _minutos_a_vencer(
        sessao, tenant_id, conta.id, referencia, dias_ate_fim_periodo
    )

    return esquemas.SaldoBancoHoras(
        colaboradorId=colaborador_id,
        vinculoId=conta.vinculo_id,
        contaId=conta.id,
        contaCodigo=conta.codigo,
        politicaCodigo=politica.codigo,
        periodoInicio=conta.periodo_inicio,
        periodoFim=conta.periodo_fim,
        saldoMinutos=saldo_minutos,
        aVencer30Minutos=a_vencer_30,
        aVencer15Minutos=a_vencer_15,
        aVencer7Minutos=a_vencer_7,
        projecaoVencimentoMinutos=projecao,
        tetoPositivoMinutos=politica.teto_positivo_minutos,
        tetoNegativoMinutos=politica.teto_negativo_minutos,
        acaoVencimento=esquemas.AcaoVencimento2(politica.acao_vencimento),
        calculadoEm=dt.datetime.now(tz=dt.UTC),
    )


async def simular_banco_horas(
    sessao: AsyncSession, tenant_id: UUID, dados: esquemas.SimulacaoBancoRequisicao
) -> esquemas.SimulacaoBancoResposta:
    """Nunca grava: nenhuma chamada a `sessao.add`/`flush` neste modulo."""
    if dados.conta_id is not None:
        resultado = await sessao.execute(
            select(BhConta).where(BhConta.id == dados.conta_id, BhConta.tenant_id == tenant_id)
        )
        conta = resultado.scalar_one_or_none()
        if conta is None:
            raise ErroDeAplicacao(
                CODIGO_RECURSO_NAO_ENCONTRADO, detalhe="Conta de banco de horas nao encontrada."
            )
    elif dados.colaborador_id is not None:
        conta = await _resolver_conta(
            sessao, tenant_id, dados.colaborador_id, vinculo_id=dados.vinculo_id
        )
    else:
        raise ErroDeAplicacao(
            CODIGO_CORPO_INVALIDO,
            detalhe="Informe colaboradorId ou contaId para simular o banco de horas.",
        )

    politica = await carregar_politica(sessao, tenant_id, conta.bh_politica_id)
    saldo_atual = conta.saldo_atual_minutos

    avisos: list[str] = []
    if dados.minutos_compensar is not None:
        impacto = -aplicar_fator(abs(dados.minutos_compensar), politica.fator_debito_padrao)
    elif dados.saida_prevista is not None:
        # Simular a partir do horario de saida exigiria o motor de apuracao
        # da jornada (F3, resolver_jornada_do_dia + app.apuracao.dominio,
        # A1) para saber a carga prevista do dia -- fora do ownership desta
        # fase (app/apuracao/banco_horas/**). Documentado tambem no
        # relatorio da fase como limitacao, nao invencao de um segundo
        # caminho de resolucao de jornada.
        impacto = 0
        avisos.append(
            "Simulacao por horario de saida requer o motor de apuracao da jornada "
            "(fora do escopo do banco de horas); use minutosCompensar para simular "
            "consumo direto do saldo."
        )
    else:
        impacto = 0

    saldo_simulado = saldo_atual + impacto
    dentro_dos_tetos = True
    if (
        politica.teto_positivo_minutos is not None
        and saldo_simulado > politica.teto_positivo_minutos
    ):
        dentro_dos_tetos = False
    if (not politica.permite_saldo_negativo and saldo_simulado < 0) or (
        politica.teto_negativo_minutos is not None
        and saldo_simulado < -politica.teto_negativo_minutos
    ):
        dentro_dos_tetos = False

    return esquemas.SimulacaoBancoResposta(
        saldoAtualMinutos=saldo_atual,
        impactoMinutos=impacto,
        saldoSimuladoMinutos=saldo_simulado,
        dentroDosTetos=dentro_dos_tetos,
        avisos=avisos,
    )
