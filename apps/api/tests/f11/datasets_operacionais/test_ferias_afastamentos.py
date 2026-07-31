"""Dataset `ferias-afastamentos` (item 12, `PROJETO.md` §9, dataset
`afastamentos`) -- T8 do PCF F11/A2.

A semente comum de `tests/f11/conftest.py` não insere `afastamentos`/
`tipos_afastamento` (não é escopo da semente comum) -- este módulo semeia o
mínimo localmente, mesma regra que a docstring da fixture já autoriza.
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.relatorios.datasets.operacionais import ferias_afastamentos
from app.relatorios.motor import ContextoConsulta
from tests.f11.conftest import ContextoF11
from tests.f11.datasets_operacionais._apoio import executar, executar_bruto


async def _semear_ferias(sessao: AsyncSession, contexto_f11: ContextoF11) -> dict[str, object]:
    colaborador_b = contexto_f11.colaboradores[1]
    tipo_id = uuid.uuid4()
    codigo = f"FERIAS-{uuid.uuid4().hex[:8]}"
    await sessao.execute(
        text(
            "INSERT INTO tipos_afastamento "
            "(id, tenant_id, codigo, nome, categoria, abona_dia, remunerado, ativo) "
            "VALUES (:id, :tenant_id, :codigo, 'Ferias de teste F11', 'ferias', TRUE, TRUE, TRUE)"
        ),
        {"id": tipo_id, "tenant_id": contexto_f11.tenant_id, "codigo": codigo},
    )
    data_inicio = contexto_f11.dias_uteis[0]
    data_fim = data_inicio + dt.timedelta(days=13)
    afastamento_id = uuid.uuid4()
    await sessao.execute(
        text(
            "INSERT INTO afastamentos "
            "(id, tenant_id, colaborador_id, vinculo_id, tipo_afastamento_id, data_inicio, "
            " data_fim, dias_previstos, status) "
            "VALUES (:id, :tenant_id, :colaborador_id, :vinculo_id, :tipo_id, :data_inicio, "
            "        :data_fim, 14, 'aprovado')"
        ),
        {
            "id": afastamento_id,
            "tenant_id": contexto_f11.tenant_id,
            "colaborador_id": colaborador_b.colaborador_id,
            "vinculo_id": colaborador_b.vinculo_id,
            "tipo_id": tipo_id,
            "data_inicio": data_inicio,
            "data_fim": data_fim,
        },
    )
    await sessao.flush()
    return {
        "colaborador_id": colaborador_b.colaborador_id,
        "data_inicio": data_inicio,
        "data_fim": data_fim,
        "codigo": codigo,
    }


async def test_ferias_semeadas_localmente_aparecem(
    sessao_f11: AsyncSession, contexto_f11: ContextoF11
) -> None:
    semente = await _semear_ferias(sessao_f11, contexto_f11)
    contexto = ContextoConsulta(
        tenant_id=contexto_f11.tenant_id,
        de=semente["data_inicio"],  # type: ignore[arg-type]
        ate=semente["data_fim"],  # type: ignore[arg-type]
    )
    resultado = await executar(
        sessao_f11,
        contexto_f11.tenant_id,
        "ferias-afastamentos",
        contexto_f11.relatorio_ids,
        filtros=contexto,
    )
    assert len(resultado.linhas) == 1
    linha = resultado.linhas[0]
    assert linha["colaboradorNome"] == contexto_f11.colaboradores[1].nome
    assert linha["categoria"] == "ferias"
    assert linha["dataInicio"] == semente["data_inicio"]
    assert linha["dataFim"] == semente["data_fim"]

    # `status`/`remunerado`/`abonaDia`/`colaborador` (uuid) não estão em
    # `colunas_disponiveis` da fixture (T1/A1) -- chama a função de consulta
    # diretamente para conferir os campos adicionais.
    linhas_brutas = await executar_bruto(
        sessao_f11, contexto_f11.tenant_id, ferias_afastamentos, filtros=contexto
    )
    assert len(linhas_brutas) == 1
    assert linhas_brutas[0]["colaborador"] == semente["colaborador_id"]
    assert linhas_brutas[0]["status"] == "aprovado"
    assert linhas_brutas[0]["remunerado"] is True
    assert linhas_brutas[0]["abonaDia"] is True


async def test_filtro_por_categoria_sem_match(
    sessao_f11: AsyncSession, contexto_f11: ContextoF11
) -> None:
    semente = await _semear_ferias(sessao_f11, contexto_f11)
    contexto = ContextoConsulta(
        tenant_id=contexto_f11.tenant_id,
        de=semente["data_inicio"],  # type: ignore[arg-type]
        ate=semente["data_fim"],  # type: ignore[arg-type]
        filtros={"categoria": "atestado"},
    )
    resultado = await executar(
        sessao_f11,
        contexto_f11.tenant_id,
        "ferias-afastamentos",
        contexto_f11.relatorio_ids,
        filtros=contexto,
    )
    assert resultado.linhas == []
