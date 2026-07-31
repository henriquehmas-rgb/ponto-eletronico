"""Dataset `ocorrencias` (item 10, `PROJETO.md` §9, dataset `ocorrencias`) --
T8 do PCF F11/A2.

A semente comum de `tests/f11/conftest.py` já insere uma `Ocorrencia`
(colaborador A, código `atraso`, severidade `atencao`, status `aberta`, no
primeiro dia útil) -- este teste consulta exatamente essa linha.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.relatorios.motor import ContextoConsulta
from tests.f11.conftest import ContextoF11
from tests.f11.datasets_operacionais._apoio import executar


async def test_ocorrencia_semeada_aparece_com_os_campos_corretos(
    sessao_f11: AsyncSession, contexto_f11: ContextoF11
) -> None:
    colaborador_a = contexto_f11.colaboradores[0]
    contexto = ContextoConsulta(
        tenant_id=contexto_f11.tenant_id,
        de=contexto_f11.dias_uteis[0],
        ate=contexto_f11.dias_uteis[-1],
    )
    resultado = await executar(
        sessao_f11,
        contexto_f11.tenant_id,
        "ocorrencias",
        contexto_f11.relatorio_ids,
        filtros=contexto,
    )
    assert len(resultado.linhas) == 1
    linha = resultado.linhas[0]
    assert linha["colaboradorNome"] == colaborador_a.nome
    assert linha["codigo"] == "atraso"
    assert linha["severidade"] == "atencao"
    assert linha["status"] == "aberta"
    assert linha["data"] == contexto_f11.dias_uteis[0]


async def test_filtro_por_codigo_e_severidade(
    sessao_f11: AsyncSession, contexto_f11: ContextoF11
) -> None:
    contexto_sem_match = ContextoConsulta(
        tenant_id=contexto_f11.tenant_id,
        de=contexto_f11.dias_uteis[0],
        ate=contexto_f11.dias_uteis[-1],
        filtros={"codigo": "falta"},
    )
    resultado_sem_match = await executar(
        sessao_f11,
        contexto_f11.tenant_id,
        "ocorrencias",
        contexto_f11.relatorio_ids,
        filtros=contexto_sem_match,
    )
    assert resultado_sem_match.linhas == []

    contexto_com_match = ContextoConsulta(
        tenant_id=contexto_f11.tenant_id,
        de=contexto_f11.dias_uteis[0],
        ate=contexto_f11.dias_uteis[-1],
        filtros={"codigo": "atraso", "severidade": "atencao"},
    )
    resultado_com_match = await executar(
        sessao_f11,
        contexto_f11.tenant_id,
        "ocorrencias",
        contexto_f11.relatorio_ids,
        filtros=contexto_com_match,
    )
    assert len(resultado_com_match.linhas) == 1
