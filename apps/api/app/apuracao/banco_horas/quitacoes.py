"""Quitacao e expiracao de saldo de banco de horas (T7, tag `banco-horas`).

`criarQuitacaoBancoHoras` cobre AMBOS os casos que o proprio `openapi.yaml`
descreve na operacao: liquidacao pedida (`tipo` in `folha`/`folga`/
`rescisao`/`compensacao_programada`) e expiracao rastreavel (`tipo=
'expiracao'`, "a perda de horas por vencimento precisa ficar rastreavel
mesmo sem pagamento"). Nao ha `atualizarQuitacaoBancoHoras`/
`excluirQuitacaoBancoHoras` no contrato -- nenhuma operacao promove uma
quitacao `planejada`/`aprovada` para `efetivada` depois da criacao. Por
isso, quando o corpo nao pede explicitamente `status='planejada'`/
`'aprovada'`/`'cancelada'`, a criacao EFETIVA imediatamente (decisao desta
fase, documentada tambem no relatorio -- se o contrato pretendia um
workflow de aprovacao separado para quitacao, falta uma operacao, e isso e
achado de RFC, nao algo que este modulo resolveria inventando um endpoint).

Ordem das validacoes na efetivacao, na mesma ordem que o PCF descreve:
saldo suficiente (`PONTO-BH-005`) primeiro, trava de periodo fechado
(`PONTO-PER-001`, via a copia propria de `verificar_periodo_aberto` --
T9/A3) em seguida. O saldo comparado e o EQUIVALENTE apos o fator (nao os
minutos brutos do pedido): uma politica com `fator_debito_padrao != 1`
debitaria mais (ou menos) do saldo do que o valor bruto pedido.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from uuid import UUID

from ponto_contracts import BhConta, BhQuitacao, Vinculo
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.apuracao.banco_horas.consulta import carregar_politica
from app.apuracao.banco_horas.erros_bd import traduzir_integridade
from app.apuracao.banco_horas.eventos import publicar_banco_horas_quitado
from app.apuracao.banco_horas.hash_chain import aplicar_fator
from app.apuracao.banco_horas.lancamentos import lancar
from app.apuracao.tratamento.fechamento import verificar_periodo_aberto
from app.core.erros import ErroDeAplicacao
from app.schemas import contrato as esquemas

CODIGO_RECURSO_NAO_ENCONTRADO = "PONTO-REC-001"
CODIGO_SALDO_INSUFICIENTE = "PONTO-BH-005"

#: `status` que a criacao aceita sem efetivar de imediato -- ver docstring
#: do modulo. Qualquer outro valor (ausente, ou explicitamente `efetivada`)
#: efetiva na hora.
_STATUS_SEM_EFETIVACAO_IMEDIATA = frozenset({"planejada", "aprovada", "cancelada"})


async def _obter_conta(sessao: AsyncSession, tenant_id: UUID, conta_id: UUID) -> BhConta:
    resultado = await sessao.execute(
        select(BhConta).where(BhConta.id == conta_id, BhConta.tenant_id == tenant_id)
    )
    conta = resultado.scalar_one_or_none()
    if conta is None:
        raise ErroDeAplicacao(
            CODIGO_RECURSO_NAO_ENCONTRADO, detalhe="Conta de banco de horas nao encontrada."
        )
    return conta


async def _obter_vinculo(sessao: AsyncSession, tenant_id: UUID, vinculo_id: UUID) -> Vinculo:
    resultado = await sessao.execute(
        select(Vinculo).where(Vinculo.id == vinculo_id, Vinculo.tenant_id == tenant_id)
    )
    vinculo = resultado.scalar_one_or_none()
    if vinculo is None:
        raise ErroDeAplicacao(CODIGO_RECURSO_NAO_ENCONTRADO, detalhe="Vinculo nao encontrado.")
    return vinculo


def _decimal_ou(valor: float | None, padrao: Decimal) -> Decimal:
    if valor is None:
        return padrao
    return Decimal(str(valor))


async def criar_quitacao_banco_horas(
    sessao: AsyncSession,
    tenant_id: UUID,
    dados: esquemas.BhQuitacaoCriar,
    *,
    criado_por: UUID | None = None,
) -> BhQuitacao:
    conta = await _obter_conta(sessao, tenant_id, dados.bh_conta_id)
    politica = await carregar_politica(sessao, tenant_id, conta.bh_politica_id)
    colaborador_id = dados.colaborador_id or conta.colaborador_id
    fator_efetivo = _decimal_ou(dados.fator, politica.fator_debito_padrao)
    valor_decimal = Decimal(str(dados.valor)) if dados.valor is not None else None

    status_pedido = dados.status.value if dados.status is not None else "efetivada"

    if status_pedido in _STATUS_SEM_EFETIVACAO_IMEDIATA:
        # Registra o pedido sem efetivar -- nenhum lancamento, nenhum
        # evento. Ver docstring do modulo: nao ha operacao neste contrato
        # para promover o status depois.
        quitacao = BhQuitacao(
            tenant_id=tenant_id,
            bh_conta_id=conta.id,
            colaborador_id=colaborador_id,
            tipo=dados.tipo.value,
            minutos=dados.minutos,
            fator=fator_efetivo,
            valor=valor_decimal,
            competencia_folha=dados.competencia_folha,
            data_prevista=dados.data_prevista,
            data_efetivacao=dados.data_efetivacao,
            status=status_pedido,
            observacao=dados.observacao,
            criado_por=criado_por,
        )
        sessao.add(quitacao)
        try:
            await sessao.flush()
        except IntegrityError as exc:
            raise traduzir_integridade(exc) from exc
        return quitacao

    data_efetivacao = dados.data_efetivacao or dt.date.today()

    minutos_equivalentes_esperado = aplicar_fator(dados.minutos, fator_efetivo)
    if conta.saldo_atual_minutos < minutos_equivalentes_esperado:
        raise ErroDeAplicacao(
            CODIGO_SALDO_INSUFICIENTE,
            detalhe=(
                f"Saldo disponivel ({conta.saldo_atual_minutos} min) e menor que a "
                f"quitacao pedida ({minutos_equivalentes_esperado} min equivalentes)."
            ),
        )

    vinculo = await _obter_vinculo(sessao, tenant_id, conta.vinculo_id)
    await verificar_periodo_aberto(
        sessao,
        tenant_id,
        empresa_id=vinculo.empresa_id,
        data=data_efetivacao,
        unidade_id=vinculo.unidade_id,
        departamento_id=vinculo.departamento_id,
    )

    quitacao = BhQuitacao(
        tenant_id=tenant_id,
        bh_conta_id=conta.id,
        colaborador_id=colaborador_id,
        tipo=dados.tipo.value,
        minutos=dados.minutos,
        fator=fator_efetivo,
        valor=valor_decimal,
        competencia_folha=dados.competencia_folha,
        data_prevista=dados.data_prevista,
        data_efetivacao=data_efetivacao,
        status="efetivada",
        aprovado_por=criado_por,
        aprovado_em=dt.datetime.now(tz=dt.UTC),
        observacao=dados.observacao,
        criado_por=criado_por,
    )
    sessao.add(quitacao)
    try:
        await sessao.flush()
    except IntegrityError as exc:
        raise traduzir_integridade(exc) from exc

    tipo_lancamento = "expiracao" if dados.tipo.value == "expiracao" else "quitacao"
    origem_lancamento = "expiracao" if dados.tipo.value == "expiracao" else "quitacao"
    lancamento = await lancar(
        sessao,
        tenant_id=tenant_id,
        bh_conta_id=conta.id,
        tipo=tipo_lancamento,
        origem=origem_lancamento,
        minutos=-dados.minutos,
        data_competencia=data_efetivacao,
        descricao=dados.observacao or f"Quitacao de banco de horas ({dados.tipo.value})",
        fator=fator_efetivo,
        quitacao_id=quitacao.id,
        criado_por=criado_por,
    )

    publicar_banco_horas_quitado(
        tenant_id=tenant_id,
        quitacao_id=quitacao.id,
        conta_id=conta.id,
        colaborador_id=colaborador_id,
        tipo=dados.tipo.value,
        minutos=dados.minutos,
        data_efetivacao=data_efetivacao,
        saldo_apos_minutos=lancamento.saldo_apos_minutos,
        lancamento_id=lancamento.id,
        valor=dados.valor,
        competencia_folha=dados.competencia_folha,
    )

    return quitacao
