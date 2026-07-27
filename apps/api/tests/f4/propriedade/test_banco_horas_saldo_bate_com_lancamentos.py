"""T12(c): "a soma de `bh_lancamentos.minutos_equivalentes` de uma conta e
sempre igual a `bh_contas.saldo_atual_minutos`" sob uma sequencia aleatoria
de creditos/debitos/quitacoes.

**Escolha documentada: parametrizacao com semente fixa, nao Hypothesis** --
mesma justificativa de `test_componentes_batem_com_totais.py` (mesmo
modulo de conftest): `hypothesis` nao esta declarado em `apps/api/
pyproject.toml` nem instalado no ambiente desta verificacao; o PCF autoriza
"Hypothesis ou parametrizacao equivalente". A sequencia aleatoria de
operacoes e gerada por um `random.Random` de semente FIXA (reprodutivel).

**O que este teste NAO faz por escolha explicita:** nao gera `tipo=
'transferencia'` (semantica de mover saldo entre DUAS contas, fora do
escopo de uma sequencia de uma conta so) nem `tipo='estorno'` (exige um
`estorna_lancamento_id` de um lancamento concreto anterior -- adicionado
como variacao natural, ja que qualquer lancamento anterior da sequencia e
um candidato valido). Usa `credito`/`debito`/`quitacao` -- os tres tipos que
o proprio enunciado da T12(c) cita.

`lancar()` (`app.apuracao.banco_horas.lancamentos`, A2) e a UNICA porta de
gravacao chamada aqui -- este teste nunca faz `INSERT`/`UPDATE` direto em
`bh_lancamentos`/`bh_contas` (proprio ADR-004/glossario 1.2: extrato e
append-only), exatamente como a producao chamaria.
"""

from __future__ import annotations

import datetime as dt
import random
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.apuracao.banco_horas.lancamentos import lancar
from tests.f4.propriedade.conftest import ContextoPropriedade

_SEMENTE = 20260726


async def _saldo_e_soma_lancamentos(
    sessao: AsyncSession, tenant_id: object, bh_conta_id: object
) -> tuple[int, int]:
    saldo = (
        await sessao.execute(
            text("SELECT saldo_atual_minutos FROM bh_contas WHERE id = :id AND tenant_id = :tid"),
            {"id": bh_conta_id, "tid": tenant_id},
        )
    ).scalar_one()
    soma = (
        await sessao.execute(
            text(
                "SELECT COALESCE(SUM(minutos_equivalentes), 0) FROM bh_lancamentos "
                "WHERE bh_conta_id = :id AND tenant_id = :tid"
            ),
            {"id": bh_conta_id, "tid": tenant_id},
        )
    ).scalar_one()
    return int(saldo), int(soma)


async def test_saldo_bate_com_soma_dos_lancamentos_sob_sequencia_aleatoria(
    sessao_propriedade: AsyncSession, contexto_propriedade: ContextoPropriedade
) -> None:
    rng = random.Random(_SEMENTE)  # noqa: S311 -- reprodutivel, nao criptografico.
    data_competencia = dt.date(2025, 1, 1)

    # Estado inicial: conta nova, sem lancamento -- saldo e soma devem ser 0.
    saldo, soma = await _saldo_e_soma_lancamentos(
        sessao_propriedade, contexto_propriedade.tenant_id, contexto_propriedade.bh_conta_id
    )
    assert saldo == soma == 0

    for indice in range(60):
        operacao = rng.choice(["credito", "credito", "debito", "quitacao"])
        data_competencia += dt.timedelta(days=1)
        if operacao == "credito":
            minutos = rng.choice([15, 30, 60, 120, 245])
            await lancar(
                sessao_propriedade,
                tenant_id=contexto_propriedade.tenant_id,
                bh_conta_id=contexto_propriedade.bh_conta_id,
                tipo="credito",
                origem="apuracao",
                minutos=minutos,
                data_competencia=data_competencia,
                descricao=f"Credito de teste de propriedade #{indice}",
                fator=Decimal("1.0"),
            )
        elif operacao == "debito":
            minutos = -rng.choice([10, 20, 45, 90])
            await lancar(
                sessao_propriedade,
                tenant_id=contexto_propriedade.tenant_id,
                bh_conta_id=contexto_propriedade.bh_conta_id,
                tipo="debito",
                origem="apuracao",
                minutos=minutos,
                data_competencia=data_competencia,
                descricao=f"Debito de teste de propriedade #{indice}",
                fator=Decimal("1.0"),
            )
        else:  # quitacao -- sempre debito (liquidacao de saldo credor).
            minutos = -rng.choice([30, 60])
            await lancar(
                sessao_propriedade,
                tenant_id=contexto_propriedade.tenant_id,
                bh_conta_id=contexto_propriedade.bh_conta_id,
                tipo="quitacao",
                origem="quitacao",
                minutos=minutos,
                data_competencia=data_competencia,
                descricao=f"Quitacao de teste de propriedade #{indice}",
                fator=Decimal("1.0"),
            )

        # A propriedade e verificada APOS CADA lancamento, nao so no final --
        # uma divergencia transitoria (que se "corrigisse" no lancamento
        # seguinte) seria igualmente um defeito.
        saldo, soma = await _saldo_e_soma_lancamentos(
            sessao_propriedade, contexto_propriedade.tenant_id, contexto_propriedade.bh_conta_id
        )
        assert saldo == soma, (
            f"apos a operacao #{indice} ({operacao}, {minutos} min): "
            f"bh_contas.saldo_atual_minutos={saldo} != "
            f"SUM(bh_lancamentos.minutos_equivalentes)={soma}"
        )
