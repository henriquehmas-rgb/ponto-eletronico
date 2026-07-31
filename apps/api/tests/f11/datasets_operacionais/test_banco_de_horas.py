"""Dataset `banco-de-horas` (item 3, `PROJETO.md` §9, dataset
`bh_lancamentos`) -- T7 do PCF F11/A2.

A fixture comum de F11 (`tests/f11/conftest.py`) não semeia `bh_contas`/
`bh_lancamentos` (não é escopo da semente comum) -- este módulo semeia o
mínimo localmente, mesma regra que a docstring da fixture já autoriza
("cada teste que precisar de dado adicional cria a própria linha extra
localmente").

**Pronto quando (T7):** prova que a soma das colunas numéricas bate com a
soma direta em `bh_lancamentos` para o mesmo escopo.
"""

from __future__ import annotations

import secrets
import uuid

import sqlalchemy as sa
from ponto_contracts import BhLancamento
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.relatorios.motor import ContextoConsulta
from tests.f11.conftest import ContextoF11
from tests.f11.datasets_operacionais._apoio import executar


async def _semear_lancamentos(sessao: AsyncSession, contexto_f11: ContextoF11) -> dict[str, object]:
    colaborador_a = contexto_f11.colaboradores[0]
    politica_id = uuid.uuid4()
    await sessao.execute(
        text(
            "INSERT INTO bh_politicas "
            "(id, tenant_id, empresa_id, codigo, nome, regime, periodo_meses, vigencia_inicio) "
            "VALUES (:id, :tenant_id, :empresa_id, :codigo, 'Politica de teste F11', "
            "        'individual', 6, :vigencia_inicio)"
        ),
        {
            "id": politica_id,
            "tenant_id": contexto_f11.tenant_id,
            "empresa_id": contexto_f11.empresa_id,
            "codigo": f"BHPOL-{uuid.uuid4().hex[:8]}",
            "vigencia_inicio": contexto_f11.periodo_data_inicio,
        },
    )

    conta_id = uuid.uuid4()
    await sessao.execute(
        text(
            "INSERT INTO bh_contas "
            "(id, tenant_id, colaborador_id, vinculo_id, bh_politica_id, codigo, nome, "
            " periodo_inicio, periodo_fim, saldo_atual_minutos) "
            "VALUES (:id, :tenant_id, :colaborador_id, :vinculo_id, :politica_id, 'normal', "
            "        'Conta de teste F11', :periodo_inicio, :periodo_fim, :saldo_atual)"
        ),
        {
            "id": conta_id,
            "tenant_id": contexto_f11.tenant_id,
            "colaborador_id": colaborador_a.colaborador_id,
            "vinculo_id": colaborador_a.vinculo_id,
            "politica_id": politica_id,
            "periodo_inicio": contexto_f11.periodo_data_inicio,
            "periodo_fim": contexto_f11.periodo_data_fim,
            "saldo_atual": 60,
        },
    )

    lancamentos = (
        # (sequencia, tipo, minutos, minutos_equivalentes, saldo_apos)
        (1, "credito", 100, 100, 100),
        (2, "debito", -40, -40, 60),
    )
    for sequencia, tipo, minutos, equivalentes, saldo_apos in lancamentos:
        await sessao.execute(
            text(
                "INSERT INTO bh_lancamentos "
                "(id, tenant_id, bh_conta_id, sequencia, data_competencia, tipo, origem, "
                " minutos, minutos_equivalentes, saldo_apos_minutos, descricao, hash_registro) "
                "VALUES (:id, :tenant_id, :conta_id, :sequencia, :data, :tipo, 'ajuste_manual', "
                "        :minutos, :equivalentes, :saldo_apos, 'Lancamento de teste F11', :hash)"
            ),
            {
                "id": uuid.uuid4(),
                "tenant_id": contexto_f11.tenant_id,
                "conta_id": conta_id,
                "sequencia": sequencia,
                "data": contexto_f11.dias_uteis[0],
                "tipo": tipo,
                "minutos": minutos,
                "equivalentes": equivalentes,
                "saldo_apos": saldo_apos,
                "hash": secrets.token_hex(32),
            },
        )
    await sessao.flush()
    return {"colaborador_id": colaborador_a.colaborador_id, "conta_id": conta_id}


async def _soma_direta_minutos(sessao: AsyncSession, tenant_id: object) -> int:
    resultado = await sessao.execute(
        sa.select(sa.func.coalesce(sa.func.sum(BhLancamento.minutos), 0)).where(
            BhLancamento.tenant_id == tenant_id
        )
    )
    return int(resultado.scalar_one())


async def test_soma_minutos_bate_com_bh_lancamentos(
    sessao_f11: AsyncSession, contexto_f11: ContextoF11
) -> None:
    semente = await _semear_lancamentos(sessao_f11, contexto_f11)
    contexto = ContextoConsulta(
        tenant_id=contexto_f11.tenant_id,
        colaborador_id=semente["colaborador_id"],  # type: ignore[arg-type]
        de=contexto_f11.periodo_data_inicio,
        ate=contexto_f11.periodo_data_fim,
    )
    resultado = await executar(
        sessao_f11,
        contexto_f11.tenant_id,
        "banco-de-horas",
        contexto_f11.relatorio_ids,
        filtros=contexto,
    )
    assert len(resultado.linhas) == 2
    soma_minutos = sum(linha["minutos"] for linha in resultado.linhas)
    assert soma_minutos == 60  # 100 credito - 40 debito
    assert soma_minutos == await _soma_direta_minutos(sessao_f11, contexto_f11.tenant_id)

    # Os dois lancamentos sinteticos tem a mesma data_competencia (mesmo
    # dia) -- confere o CONJUNTO de saldos apos cada lancamento, sem
    # depender de uma ordenacao especifica por data (empatada).
    saldos = {linha["saldoAposMinutos"] for linha in resultado.linhas}
    assert saldos == {100, 60}
