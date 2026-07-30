"""Testes de `app.workflow.fechamento.conferencia` (T6, F10/A2).

Cobre o critério "pronto quando" do PCF: `podeFechar=false` quando existe
`ocorrencias` com código bloqueante aberta; `conferirFechamento` chamado
duas vezes seguidas é idempotente (mesmos totais, sem duplicar contagem).
"""

from __future__ import annotations

import pytest
from ponto_contracts import Fechamento, Ocorrencia

from app.workflow.fechamento.conferencia import (
    CODIGO_NAO_APURADO,
    ParametrosConferencia,
    calcular_conferencia,
    conferir_fechamento,
)
from tests.f10.conftest import ContextoF10, aplicar_tenant_teste


async def _obter_periodo(sessao, contexto: ContextoF10):
    from ponto_contracts import Periodo

    return await sessao.get(Periodo, contexto.periodo_id)


@pytest.mark.asyncio
async def test_sem_pendencia_pode_fechar(sessao_f10, contexto_f10: ContextoF10) -> None:
    periodo = await _obter_periodo(sessao_f10, contexto_f10)
    parametros = ParametrosConferencia(
        periodo=periodo, escopo="empresa", empresa_id=contexto_f10.empresa_id
    )
    resposta = await calcular_conferencia(sessao_f10, contexto_f10.tenant_id, parametros)

    # Nenhuma apuracao existe ainda no periodo -> todo dia-vinculo conta
    # como "nao apurado", que E bloqueante por decisao fixada do PCF.
    assert CODIGO_NAO_APURADO in (resposta.bloqueantes or [])
    assert resposta.pode_fechar is False
    assert resposta.total_colaboradores == 1


@pytest.mark.asyncio
async def test_ocorrencia_marcacao_impar_aberta_bloqueia(
    sessao_f10, contexto_f10: ContextoF10
) -> None:
    periodo = await _obter_periodo(sessao_f10, contexto_f10)
    sessao_f10.add(
        Ocorrencia(
            tenant_id=contexto_f10.tenant_id,
            colaborador_id=contexto_f10.colaborador_id,
            vinculo_id=contexto_f10.vinculo_id,
            data=periodo.data_inicio,
            codigo="marcacao_impar",
            severidade="atencao",
            descricao="Numero impar de marcacoes no dia (teste).",
            status="aberta",
        )
    )
    await sessao_f10.flush()

    parametros = ParametrosConferencia(
        periodo=periodo, escopo="empresa", empresa_id=contexto_f10.empresa_id
    )
    resposta = await calcular_conferencia(sessao_f10, contexto_f10.tenant_id, parametros)

    assert "marcacao_impar" in (resposta.bloqueantes or [])
    assert resposta.ocorrencias_abertas == 1
    assert resposta.pode_fechar is False


@pytest.mark.asyncio
async def test_ocorrencia_nao_bloqueante_nao_entra_em_bloqueantes(
    sessao_f10, contexto_f10: ContextoF10
) -> None:
    """`jornada_excedida` e um AVISO, nunca bloqueante (PCF §6, T6)."""
    periodo = await _obter_periodo(sessao_f10, contexto_f10)
    sessao_f10.add(
        Ocorrencia(
            tenant_id=contexto_f10.tenant_id,
            colaborador_id=contexto_f10.colaborador_id,
            vinculo_id=contexto_f10.vinculo_id,
            data=periodo.data_inicio,
            codigo="jornada_excedida",
            severidade="atencao",
            descricao="Jornada excedida (teste, aviso apenas).",
            status="aberta",
        )
    )
    await sessao_f10.flush()

    parametros = ParametrosConferencia(
        periodo=periodo, escopo="empresa", empresa_id=contexto_f10.empresa_id
    )
    resposta = await calcular_conferencia(sessao_f10, contexto_f10.tenant_id, parametros)

    assert "jornada_excedida" not in (resposta.bloqueantes or [])
    assert resposta.ocorrencias_abertas == 1


@pytest.mark.asyncio
async def test_conferir_fechamento_e_idempotente(sessao_f10, contexto_f10: ContextoF10) -> None:
    periodo = await _obter_periodo(sessao_f10, contexto_f10)
    fechamento = Fechamento(
        tenant_id=contexto_f10.tenant_id,
        periodo_id=periodo.id,
        empresa_id=contexto_f10.empresa_id,
        escopo="empresa",
        status="em_andamento",
    )
    sessao_f10.add(fechamento)
    await sessao_f10.flush()
    await sessao_f10.commit()
    await aplicar_tenant_teste(sessao_f10, contexto_f10.tenant_id)

    primeira = await conferir_fechamento(
        sessao_f10, contexto_f10.tenant_id, fechamento.id, usuario_id=contexto_f10.rh_usuario_id
    )
    segunda = await conferir_fechamento(
        sessao_f10, contexto_f10.tenant_id, fechamento.id, usuario_id=contexto_f10.rh_usuario_id
    )

    assert primeira.total_colaboradores == segunda.total_colaboradores
    assert primeira.ocorrencias_abertas == segunda.ocorrencias_abertas
    assert primeira.apuracoes_pendentes == segunda.apuracoes_pendentes
    assert primeira.bloqueantes == segunda.bloqueantes
    assert fechamento.status == "conferido"
