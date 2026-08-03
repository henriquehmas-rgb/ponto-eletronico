"""Testes de `app.integracoes.folha.comum.dados` (F13/A5, T15) contra
banco real -- unico ponto do motor que fala com `apuracoes_dia`/
`apuracao_componentes`. Usa a fixture propria de `tests/f13/folha/
conftest.py` (A5, T1-first do subgrupo -- nao depende de `tests/f13/
conftest.py`, exclusiva de A1)."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.erros import ErroDeAplicacao
from app.integracoes.folha.comum.dados import coletar_linhas_apuracao, resolver_intervalo
from tests.f13.folha.conftest import ContextoFolhaF13

pytestmark = pytest.mark.asyncio


async def test_resolver_intervalo_por_periodo_id(
    sessao_f13a5: AsyncSession, contexto_folha_f13a5: ContextoFolhaF13
) -> None:
    inicio, fim = await resolver_intervalo(
        sessao_f13a5,
        tenant_id=contexto_folha_f13a5.tenant_id,
        empresa_id=contexto_folha_f13a5.empresa_id,
        periodo_id=contexto_folha_f13a5.periodo_id,
        competencia_folha=None,
    )
    assert inicio == contexto_folha_f13a5.periodo_inicio
    assert fim == contexto_folha_f13a5.periodo_fim


async def test_resolver_intervalo_por_competencia_folha(
    sessao_f13a5: AsyncSession, contexto_folha_f13a5: ContextoFolhaF13
) -> None:
    inicio, fim = await resolver_intervalo(
        sessao_f13a5,
        tenant_id=contexto_folha_f13a5.tenant_id,
        empresa_id=contexto_folha_f13a5.empresa_id,
        periodo_id=None,
        competencia_folha=contexto_folha_f13a5.competencia_folha,
    )
    assert inicio.isoformat()[:7] == contexto_folha_f13a5.competencia_folha
    assert fim.isoformat()[:7] == contexto_folha_f13a5.competencia_folha


async def test_resolver_intervalo_sem_periodo_nem_competencia_e_ponto_val_001(
    sessao_f13a5: AsyncSession, contexto_folha_f13a5: ContextoFolhaF13
) -> None:
    with pytest.raises(ErroDeAplicacao) as exc_info:
        await resolver_intervalo(
            sessao_f13a5,
            tenant_id=contexto_folha_f13a5.tenant_id,
            empresa_id=contexto_folha_f13a5.empresa_id,
            periodo_id=None,
            competencia_folha=None,
        )
    assert exc_info.value.codigo == "PONTO-VAL-001"


async def test_periodo_id_de_outra_empresa_e_nao_encontrado(
    sessao_f13a5: AsyncSession, contexto_folha_f13a5: ContextoFolhaF13
) -> None:
    from uuid import uuid4

    with pytest.raises(ErroDeAplicacao) as exc_info:
        await resolver_intervalo(
            sessao_f13a5,
            tenant_id=contexto_folha_f13a5.tenant_id,
            empresa_id=uuid4(),
            periodo_id=contexto_folha_f13a5.periodo_id,
            competencia_folha=None,
        )
    assert exc_info.value.codigo == "PONTO-REC-001"


async def test_coletar_linhas_uma_por_vinculo_dia_componente(
    sessao_f13a5: AsyncSession, contexto_folha_f13a5: ContextoFolhaF13
) -> None:
    linhas = await coletar_linhas_apuracao(
        sessao_f13a5,
        tenant_id=contexto_folha_f13a5.tenant_id,
        empresa_id=contexto_folha_f13a5.empresa_id,
        inicio=contexto_folha_f13a5.periodo_inicio,
        fim=contexto_folha_f13a5.periodo_fim,
        unidade_id=None,
        somente_fechados=True,
    )
    # A fixture semeia 2 dias x 2 componentes = 4 linhas.
    assert len(linhas) == len(contexto_folha_f13a5.linhas)
    codigos_esperados = {semente.codigo for semente in contexto_folha_f13a5.linhas}
    codigos_obtidos = {linha.componente_codigo for linha in linhas}
    assert codigos_obtidos == codigos_esperados
    for linha in linhas:
        assert linha.matricula == contexto_folha_f13a5.colaborador_matricula
        assert linha.cpf == contexto_folha_f13a5.colaborador_cpf
        assert linha.pis_nit == contexto_folha_f13a5.colaborador_pis
        assert linha.empresa_cnpj == contexto_folha_f13a5.empresa_cnpj
        assert linha.departamento_codigo == contexto_folha_f13a5.departamento_codigo
        assert linha.rubrica is None  # resolvido so pelo exportador, nao aqui


async def test_somente_fechados_false_nao_filtra_por_status(
    sessao_f13a5: AsyncSession, contexto_folha_f13a5: ContextoFolhaF13
) -> None:
    linhas_fechados = await coletar_linhas_apuracao(
        sessao_f13a5,
        tenant_id=contexto_folha_f13a5.tenant_id,
        empresa_id=contexto_folha_f13a5.empresa_id,
        inicio=contexto_folha_f13a5.periodo_inicio,
        fim=contexto_folha_f13a5.periodo_fim,
        unidade_id=None,
        somente_fechados=True,
    )
    linhas_todos = await coletar_linhas_apuracao(
        sessao_f13a5,
        tenant_id=contexto_folha_f13a5.tenant_id,
        empresa_id=contexto_folha_f13a5.empresa_id,
        inicio=contexto_folha_f13a5.periodo_inicio,
        fim=contexto_folha_f13a5.periodo_fim,
        unidade_id=None,
        somente_fechados=False,
    )
    # A fixture so semeia dias 'fechado' -- os dois conjuntos coincidem,
    # mas a chamada com somente_fechados=False nao deve FALHAR nem
    # filtrar a mais.
    assert len(linhas_todos) >= len(linhas_fechados)
