"""T12(a): "recalcular o mes inteiro apos invalidacao parcial de um unico
dia nao muda os demais dias" (ADR-004, consequencia negativa (a); PCF
criterio de aceite 6).

Estrategia: apura um mes inteiro (janeiro/2025, 31 dias) de uma vez com
`recalcular_periodo` (A3), guarda `(hash_entrada, versao)` de cada dia,
insere UMA marcacao nova em um UNICO dia do meio do mes (o que muda o
`hash_entrada` so daquele dia -- ADR-004, ponto 3: o hash cobre exatamente
os insumos do dia) e recalcula o mes inteiro de novo. A propriedade e que,
depois do segundo recalculo, absolutamente NENHUM dia fora do dia alterado
mudou `hash_entrada` nem `versao`, e o dia alterado mudou os dois.

Nao usa Hypothesis (nao declarado em `apps/api/pyproject.toml`; ver decisao
documentada em `test_componentes_batem_com_totais.py`, mesmo modulo de
conftest) -- a "amostra" desta propriedade e estrutural (todo dia do mes),
nao aleatoria, entao parametrizacao nao se aplica aqui: o teste roda a
sequencia completa determinada (apura o mes, altera um dia, apura de novo)
uma vez, com dois pontos de invalidacao (inicio e meio do mes) para cobrir
tambem a dependencia de borda que o ADR-004 documenta (interjornada olha o
dia anterior).
"""

from __future__ import annotations

import datetime as _dt

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.apuracao.tratamento.recalculo import recalcular_periodo
from tests.f4.propriedade.conftest import ContextoPropriedade, inserir_marcacao

_INICIO_MES = _dt.date(2025, 1, 1)
_FIM_MES = _dt.date(2025, 1, 31)


async def _estado_apuracoes(
    sessao: AsyncSession, tenant_id: object, vinculo_id: object
) -> dict[_dt.date, tuple[str | None, int | None]]:
    linhas = (
        await sessao.execute(
            text(
                "SELECT data, hash_entrada, versao FROM apuracoes_dia "
                "WHERE tenant_id = :tenant_id AND vinculo_id = :vinculo_id"
            ),
            {"tenant_id": tenant_id, "vinculo_id": vinculo_id},
        )
    ).all()
    return {linha.data: (linha.hash_entrada, linha.versao) for linha in linhas}


@pytest.mark.parametrize(
    "dia_alterado",
    [_dt.date(2025, 1, 15), _dt.date(2025, 1, 1)],
    ids=["meio_do_mes", "primeiro_dia_do_mes"],
)
async def test_invalidacao_de_um_dia_nao_muda_os_demais(
    dia_alterado: _dt.date,
    sessao_propriedade: AsyncSession,
    contexto_propriedade: ContextoPropriedade,
) -> None:
    resultado_inicial = await recalcular_periodo(
        sessao_propriedade,
        contexto_propriedade.tenant_id,
        vinculo_id=contexto_propriedade.vinculo_id,
        inicio=_INICIO_MES,
        fim=_FIM_MES,
        motivo="teste de propriedade T12(a) -- apuracao inicial do mes",
    )
    assert resultado_inicial.dias_processados == 31

    estado_antes = await _estado_apuracoes(
        sessao_propriedade, contexto_propriedade.tenant_id, contexto_propriedade.vinculo_id
    )
    assert len(estado_antes) == 31, "todo dia do mes deveria ter gerado apuracoes_dia"

    # Invalida so o dia_alterado: insere uma marcacao nova (entrada as 08:00,
    # NSR novo) -- isto muda `hash_entrada` SOMENTE deste dia (ADR-004, ponto
    # 3: hash cobre exatamente os insumos do dia, marcacoes incluidas).
    await inserir_marcacao(
        sessao_propriedade,
        tenant_id=contexto_propriedade.tenant_id,
        rep_p_id=contexto_propriedade.rep_p_id,
        empresa_id=contexto_propriedade.empresa_id,
        colaborador_id=contexto_propriedade.colaborador_id,
        vinculo_id=contexto_propriedade.vinculo_id,
        cpf="00000000000",
        datahora=_dt.datetime.combine(
            dia_alterado, _dt.time(8, 0), tzinfo=_dt.timezone(_dt.timedelta(hours=-3))
        ),
        nsr=90_000 + dia_alterado.day,
    )
    await sessao_propriedade.flush()

    resultado_segundo = await recalcular_periodo(
        sessao_propriedade,
        contexto_propriedade.tenant_id,
        vinculo_id=contexto_propriedade.vinculo_id,
        inicio=_INICIO_MES,
        fim=_FIM_MES,
        motivo="teste de propriedade T12(a) -- recalculo apos invalidacao parcial",
    )
    assert resultado_segundo.dias_processados == 31

    estado_depois = await _estado_apuracoes(
        sessao_propriedade, contexto_propriedade.tenant_id, contexto_propriedade.vinculo_id
    )
    assert len(estado_depois) == 31

    dias_com_hash_diferente = {
        data
        for data, (hash_antes, _versao_antes) in estado_antes.items()
        if estado_depois[data][0] != hash_antes
    }
    assert dias_com_hash_diferente == {dia_alterado}, (
        f"esperava que SOMENTE {dia_alterado} mudasse de hash_entrada; "
        f"mudaram tambem: {dias_com_hash_diferente - {dia_alterado}}"
    )

    dias_com_versao_incrementada = {
        data
        for data, (_hash_antes, versao_antes) in estado_antes.items()
        if estado_depois[data][1] != versao_antes
    }
    assert dias_com_versao_incrementada == {dia_alterado}, (
        f"esperava que SOMENTE {dia_alterado} incrementasse `versao`; "
        f"mudaram tambem: {dias_com_versao_incrementada - {dia_alterado}}"
    )

    # O dia alterado de fato mudou (nao apenas "nao mudou" por engano).
    assert estado_depois[dia_alterado][0] != estado_antes[dia_alterado][0]
    assert estado_depois[dia_alterado][1] == estado_antes[dia_alterado][1] + 1
