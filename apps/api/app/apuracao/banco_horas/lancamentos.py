"""Extrato imutavel (`bh_lancamentos`) e consumo FIFO/LIFO (T6).

`lancar()` e a UNICA porta de entrada para gravar um lancamento: aloca
`sequencia` (via `bh_contas.ultima_sequencia`, o mesmo padrao transacional de
NSR/auditoria -- trava a linha da conta com `SELECT ... FOR UPDATE` e
recalcula em Python, nunca `SEQUENCE`/`SERIAL`, para que um `ROLLBACK` nunca
deixe lacuna), calcula `minutos_equivalentes` (fator aplicado sobre inteiro,
arredondamento unico documentado em `hash_chain.aplicar_fator`), `saldo_apos_
minutos` e a cadeia de hash (`hash_chain.py`). Respeita os tetos da politica
(`PONTO-BH-001`/`PONTO-BH-002`) e, quando o lancamento e um debito real
(falta, quitacao, expiracao -- nunca estorno nem ajuste, que tem semantica
propria nao coberta por este modulo), aciona o consumo FIFO/LIFO sobre os
creditos da mesma conta.

Nenhuma outra funcao deste pacote grava em `bh_lancamentos` fora daqui -- o
`UPDATE` de `consumido_minutos` feito por `consumir_creditos` e a UNICA
excecao permitida por `fn_bh_lancamento_imutavel()` (schema.sql, secao 17),
e e feito por mutacao de atributo ORM (nunca por `UPDATE` bruto que tocasse
outra coluna), o que garante que o `UPDATE` gerado pelo `flush()` toca
exclusivamente essa coluna.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from uuid import UUID

import sqlalchemy as sa
from ponto_contracts import BhConta, BhLancamento, BhPolitica, Ocorrencia
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.apuracao.banco_horas.erros_bd import traduzir_integridade
from app.apuracao.banco_horas.hash_chain import (
    aplicar_fator,
    calcular_hash,
    canonicalizar_lancamento,
)
from app.core.erros import ErroDeAplicacao

CODIGO_RECURSO_NAO_ENCONTRADO = "PONTO-REC-001"
CODIGO_CORPO_INVALIDO = "PONTO-VAL-001"
CODIGO_TETO_POSITIVO = "PONTO-BH-001"
CODIGO_TETO_NEGATIVO = "PONTO-BH-002"
CODIGO_CONTA_ENCERRADA = "PONTO-BH-004"

#: Tipos de lancamento que representam consumo real de saldo credor e por
#: isso disparam a rotina FIFO/LIFO. `estorno` e `ajuste` tem semantica
#: propria (reversao de um lancamento especifico, ou correcao manual) que
#: nao mapeia 1:1 para "abater credito mais antigo/mais novo" sem uma
#: associacao explicita credito<->debito que este schema nao guarda -- fica
#: de fora deliberadamente, documentado aqui, nao e omissao.
_TIPOS_QUE_CONSOMEM_CREDITO = frozenset({"debito", "quitacao", "expiracao"})

#: Sentinela de "nunca vence" para ordenar creditos sem `vence_em` por
#: ultimo no FIFO e primeiro no LIFO (ver `consumir_creditos`).
_HORIZONTE_SEM_VENCIMENTO = dt.date(9999, 12, 31)


async def lancar(
    sessao: AsyncSession,
    *,
    tenant_id: UUID,
    bh_conta_id: UUID,
    tipo: str,
    origem: str,
    minutos: int,
    data_competencia: dt.date,
    descricao: str,
    fator: Decimal | None = None,
    vence_em: dt.date | None = None,
    apuracao_dia_id: UUID | None = None,
    tratamento_id: UUID | None = None,
    quitacao_id: UUID | None = None,
    estorna_lancamento_id: UUID | None = None,
    criado_por: UUID | None = None,
) -> BhLancamento:
    """Grava um lancamento em `bh_lancamentos` e atualiza `bh_contas` na
    mesma transacao. `fator` ausente usa o padrao da politica
    (`fator_credito_padrao` para `minutos > 0`, `fator_debito_padrao` para
    `minutos < 0`). `minutos == 0` e sempre recusado (proibido pelo
    `CHECK` da coluna, e sem sentido de negocio)."""
    if minutos == 0:
        raise ErroDeAplicacao(CODIGO_CORPO_INVALIDO, detalhe="minutos nao pode ser zero.")

    resultado_conta = await sessao.execute(
        select(BhConta)
        .where(BhConta.id == bh_conta_id, BhConta.tenant_id == tenant_id)
        .with_for_update()
    )
    conta = resultado_conta.scalar_one_or_none()
    if conta is None:
        raise ErroDeAplicacao(
            CODIGO_RECURSO_NAO_ENCONTRADO, detalhe="Conta de banco de horas nao encontrada."
        )
    if conta.status != "aberta":
        raise ErroDeAplicacao(
            CODIGO_CONTA_ENCERRADA,
            detalhe=f"Conta esta '{conta.status}' e nao recebe novos lancamentos.",
        )

    resultado_politica = await sessao.execute(
        select(BhPolitica).where(
            BhPolitica.id == conta.bh_politica_id, BhPolitica.tenant_id == tenant_id
        )
    )
    politica = resultado_politica.scalar_one_or_none()
    if politica is None:
        raise ErroDeAplicacao(
            CODIGO_RECURSO_NAO_ENCONTRADO,
            detalhe="Politica de banco de horas da conta nao encontrada.",
        )

    fator_efetivo = (
        fator
        if fator is not None
        else (politica.fator_credito_padrao if minutos > 0 else politica.fator_debito_padrao)
    )
    minutos_equivalentes = aplicar_fator(minutos, fator_efetivo)
    if minutos_equivalentes == 0:
        raise ErroDeAplicacao(
            CODIGO_CORPO_INVALIDO,
            detalhe="minutosEquivalentes nao pode ser zero apos aplicar o fator.",
        )

    saldo_apos = conta.saldo_atual_minutos + minutos_equivalentes
    _validar_tetos(politica, minutos_equivalentes=minutos_equivalentes, saldo_apos=saldo_apos)

    sequencia = conta.ultima_sequencia + 1
    dados_canonicos = canonicalizar_lancamento(
        tenant_id=tenant_id,
        bh_conta_id=bh_conta_id,
        sequencia=sequencia,
        data_competencia=data_competencia,
        tipo=tipo,
        origem=origem,
        minutos=minutos,
        fator=fator_efetivo,
        minutos_equivalentes=minutos_equivalentes,
        saldo_apos_minutos=saldo_apos,
        descricao=descricao,
    )
    hash_registro = calcular_hash(dados_canonicos, conta.ultimo_hash)

    lancamento = BhLancamento(
        tenant_id=tenant_id,
        bh_conta_id=bh_conta_id,
        sequencia=sequencia,
        data_competencia=data_competencia,
        tipo=tipo,
        origem=origem,
        apuracao_dia_id=apuracao_dia_id,
        tratamento_id=tratamento_id,
        quitacao_id=quitacao_id,
        estorna_lancamento_id=estorna_lancamento_id,
        minutos=minutos,
        fator=fator_efetivo,
        minutos_equivalentes=minutos_equivalentes,
        saldo_apos_minutos=saldo_apos,
        vence_em=vence_em,
        consumido_minutos=0,
        descricao=descricao,
        hash_anterior=conta.ultimo_hash,
        hash_registro=hash_registro,
        criado_por=criado_por,
    )
    sessao.add(lancamento)
    conta.ultima_sequencia = sequencia
    conta.ultimo_hash = hash_registro
    conta.saldo_atual_minutos = saldo_apos
    try:
        await sessao.flush()
    except IntegrityError as exc:
        raise traduzir_integridade(exc, padrao=CODIGO_CORPO_INVALIDO) from exc

    if tipo in _TIPOS_QUE_CONSOMEM_CREDITO and minutos_equivalentes < 0:
        await consumir_creditos(
            sessao,
            tenant_id=tenant_id,
            bh_conta_id=bh_conta_id,
            minutos=abs(minutos_equivalentes),
            metodo_consumo=politica.metodo_consumo,
        )

    if excede_teto_positivo_sinalizavel(politica, saldo_apos=saldo_apos):
        await _abrir_ocorrencia_banco_teto(
            sessao, tenant_id=tenant_id, conta=conta, saldo_apos=saldo_apos, politica=politica
        )

    return lancamento


async def _abrir_ocorrencia_banco_teto(
    sessao: AsyncSession, *, tenant_id: UUID, conta: BhConta, saldo_apos: int, politica: BhPolitica
) -> Ocorrencia:
    """Abre `ocorrencias.codigo='banco_teto'` quando o credito excede o
    teto positivo mas a politica sinaliza em vez de bloquear
    (`bloqueia_extra_no_teto = False`) -- T7. So a linha da tabela;
    `ocorrencia.aberta` (events.yaml) e publicado por `app.apuracao.dominio`
    (A1) durante `apurar_dia`, unico produtor deste evento nesta fase (PCF
    secao 4) -- este modulo nao republica."""
    ocorrencia = Ocorrencia(
        tenant_id=tenant_id,
        colaborador_id=conta.colaborador_id,
        vinculo_id=conta.vinculo_id,
        data=dt.date.today(),
        codigo="banco_teto",
        severidade="atencao",
        descricao=(
            f"Saldo credor da conta '{conta.codigo}' atingiu {saldo_apos} minutos, acima "
            f"do teto positivo configurado ({politica.teto_positivo_minutos} minutos)."
        ),
        detalhes={
            "contaId": str(conta.id),
            "saldoAposMinutos": saldo_apos,
            "tetoPositivoMinutos": politica.teto_positivo_minutos,
        },
    )
    sessao.add(ocorrencia)
    await sessao.flush()
    return ocorrencia


def _validar_tetos(politica: BhPolitica, *, minutos_equivalentes: int, saldo_apos: int) -> None:
    """Tetos da politica (`bh_politicas.teto_positivo_minutos`/
    `teto_negativo_minutos`/`bloqueia_extra_no_teto`/`permite_saldo_negativo`).

    Credito que excede o teto positivo: recusado com `PONTO-BH-001` quando
    `bloqueia_extra_no_teto` e verdadeiro; quando falso, o lancamento
    prossegue e o CHAMADOR (`quitacoes.py`/quem credita) e responsavel por
    abrir a ocorrencia `banco_teto` -- este modulo so calcula, nao decide
    ocorrencia (mantido em `quitacoes.py`/`contas.py` para nao acoplar
    `lancar()` a escrita em `ocorrencias`).

    Debito que levaria a saldo negativo alem do permitido: `PONTO-BH-002`,
    tanto quando a politica proibe saldo negativo (`permite_saldo_negativo
    = False`) quanto quando excede `teto_negativo_minutos` -- decisao de
    projeto desta fase (nao ha, no PCF, uma bandeira de "sinalizar em vez de
    bloquear" para o teto negativo, ao contrario do positivo).
    """
    if minutos_equivalentes > 0:
        if (
            politica.teto_positivo_minutos is not None
            and saldo_apos > politica.teto_positivo_minutos
            and politica.bloqueia_extra_no_teto
        ):
            raise ErroDeAplicacao(
                CODIGO_TETO_POSITIVO,
                detalhe=(
                    f"Saldo resultante ({saldo_apos} min) excederia o teto positivo da "
                    f"politica ({politica.teto_positivo_minutos} min)."
                ),
            )
    elif minutos_equivalentes < 0:
        if not politica.permite_saldo_negativo and saldo_apos < 0:
            raise ErroDeAplicacao(
                CODIGO_TETO_NEGATIVO, detalhe="A politica nao permite saldo devedor."
            )
        if (
            politica.teto_negativo_minutos is not None
            and saldo_apos < -politica.teto_negativo_minutos
        ):
            raise ErroDeAplicacao(
                CODIGO_TETO_NEGATIVO,
                detalhe=(
                    f"Saldo resultante ({saldo_apos} min) excederia o teto negativo da "
                    f"politica ({politica.teto_negativo_minutos} min)."
                ),
            )


def excede_teto_positivo_sinalizavel(politica: BhPolitica, *, saldo_apos: int) -> bool:
    """Verdadeiro quando o saldo excede o teto positivo mas a politica NAO
    bloqueia (`bloqueia_extra_no_teto = False`) -- o caso em que o CHAMADOR
    deve abrir a ocorrencia `banco_teto` em vez de recusar (T7). Extraido
    como funcao propria para os chamadores nao duplicarem a comparacao."""
    return (
        politica.teto_positivo_minutos is not None
        and saldo_apos > politica.teto_positivo_minutos
        and not politica.bloqueia_extra_no_teto
    )


async def consumir_creditos(
    sessao: AsyncSession,
    *,
    tenant_id: UUID,
    bh_conta_id: UUID,
    minutos: int,
    metodo_consumo: str,
) -> int:
    """Percorre os creditos abertos da conta (`tipo='credito'`,
    `minutos_equivalentes > consumido_minutos`) e incrementa
    `consumido_minutos` de cada um ate esgotar `minutos` (o debito a
    abater), na ordem de `metodo_consumo`:

    * **fifo** consome primeiro os creditos MAIS PROXIMOS do vencimento
      (`vence_em` ascendente, `sequencia` ascendente como desempate) --
      "protege o empregado do vencimento" (comentario de
      `bh_politicas.metodo_consumo` em `schema.sql`): se o debito nao
      consumisse o credito prestes a vencer primeiro, ele venceria e
      seria perdido em vez de aproveitado.
    * **lifo** consome primeiro os MAIS DISTANTES do vencimento (`vence_em`
      descendente, `sequencia` descendente) -- o inverso.

    Creditos sem `vence_em` (nunca vencem) entram por ultimo no FIFO e
    primeiro no LIFO, tratados como "vencimento infinito".

    So MUTA o atributo ORM `consumido_minutos` (nunca `UPDATE` bruto de
    outra coluna): o `flush()` gerado pelo SQLAlchemy so inclui no `SET` as
    colunas efetivamente alteradas, entao o `UPDATE` fisico toca
    exclusivamente `consumido_minutos` -- a unica excecao que
    `fn_bh_lancamento_imutavel()` permite.

    Devolve os minutos que sobraram sem contrapartida de credito
    especifico (> 0 quando o debito excede os creditos disponiveis --
    economicamente valido, o saldo agregado fica negativo, so nao ha mais
    o que "consumir" por lancamento).
    """
    if minutos <= 0:
        return 0

    chave_vencimento = sa.func.coalesce(
        BhLancamento.vence_em, sa.literal(_HORIZONTE_SEM_VENCIMENTO)
    )
    if metodo_consumo == "lifo":
        ordem = (chave_vencimento.desc(), BhLancamento.sequencia.desc())
    else:
        ordem = (chave_vencimento.asc(), BhLancamento.sequencia.asc())

    consulta = (
        select(BhLancamento)
        .where(
            BhLancamento.tenant_id == tenant_id,
            BhLancamento.bh_conta_id == bh_conta_id,
            BhLancamento.tipo == "credito",
            BhLancamento.minutos_equivalentes > BhLancamento.consumido_minutos,
        )
        .order_by(*ordem)
        .with_for_update()
    )
    resultado = await sessao.execute(consulta)

    restante = minutos
    for credito in resultado.scalars():
        if restante <= 0:
            break
        disponivel = credito.minutos_equivalentes - credito.consumido_minutos
        consumir_agora = min(disponivel, restante)
        if consumir_agora <= 0:
            continue
        credito.consumido_minutos += consumir_agora
        restante -= consumir_agora

    await sessao.flush()
    return restante
