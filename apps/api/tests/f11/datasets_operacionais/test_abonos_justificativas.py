"""Dataset `abonos-justificativas` (item 11, `PROJETO.md` §9, dataset
`tratamentos_abono`) -- T8 do PCF F11/A2.

A semente comum de `tests/f11/conftest.py` já insere um `Tratamento`
categoria `abono` (colaborador C, aprovado, no último dia útil, motivo
"Atestado medico de teste") -- este teste consulta exatamente essa linha.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.relatorios.datasets.operacionais import abonos_justificativas
from app.relatorios.motor import ContextoConsulta
from tests.f11.conftest import ContextoF11
from tests.f11.datasets_operacionais._apoio import executar, executar_bruto


async def test_tratamento_de_abono_semeado_aparece(
    sessao_f11: AsyncSession, contexto_f11: ContextoF11
) -> None:
    colaborador_c = contexto_f11.colaboradores[2]
    contexto = ContextoConsulta(
        tenant_id=contexto_f11.tenant_id,
        de=contexto_f11.dias_uteis[0],
        ate=contexto_f11.dias_uteis[-1],
    )
    resultado = await executar(
        sessao_f11,
        contexto_f11.tenant_id,
        "abonos-justificativas",
        contexto_f11.relatorio_ids,
        filtros=contexto,
    )
    assert len(resultado.linhas) == 1
    linha = resultado.linhas[0]
    assert linha["colaboradorNome"] == colaborador_c.nome
    assert linha["dataReferencia"] == contexto_f11.dias_uteis[-1]
    assert linha["status"] == "aprovado"
    assert linha["motivo"] == "Atestado medico de teste"

    # `categoria` não está em `colunas_disponiveis` da fixture (T1/A1) --
    # chama a função de consulta diretamente para conferir a categoria.
    linhas_brutas = await executar_bruto(
        sessao_f11, contexto_f11.tenant_id, abonos_justificativas, filtros=contexto
    )
    assert linhas_brutas[0]["categoria"] == "abono"
    assert linhas_brutas[0]["colaborador"] == colaborador_c.colaborador_id


async def test_filtro_por_status_reprovado_nao_encontra_nada(
    sessao_f11: AsyncSession, contexto_f11: ContextoF11
) -> None:
    contexto = ContextoConsulta(
        tenant_id=contexto_f11.tenant_id,
        de=contexto_f11.dias_uteis[0],
        ate=contexto_f11.dias_uteis[-1],
        filtros={"status": "reprovado"},
    )
    resultado = await executar(
        sessao_f11,
        contexto_f11.tenant_id,
        "abonos-justificativas",
        contexto_f11.relatorio_ids,
        filtros=contexto,
    )
    assert resultado.linhas == []
