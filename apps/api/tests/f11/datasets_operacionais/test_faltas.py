"""Dataset `faltas` (item 8, `PROJETO.md` §9, dataset `apuracao_dia_faltas`)
-- T8 do PCF F11/A2.

**Pronto quando (T8):** teste prova que `faltas` reflete corretamente a
lacuna do ADR-011 (uma falta com tratamento `afastamento` retroativo
aprovado continua aparecendo como falta, não é escondida) -- documenta o
comportamento real, não o esconde (mesmo padrão que F10/A4 já fez para o
mesmo achado).
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from ponto_contracts import ApuracaoDia
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.relatorios.datasets.operacionais import faltas
from app.relatorios.motor import ContextoConsulta
from tests.f11.conftest import ContextoF11
from tests.f11.datasets_operacionais._apoio import executar, executar_bruto


async def _soma_direta_falta(sessao: AsyncSession, tenant_id: object) -> int:
    resultado = await sessao.execute(
        sa.select(sa.func.coalesce(sa.func.sum(ApuracaoDia.falta_minutos), 0)).where(
            ApuracaoDia.tenant_id == tenant_id
        )
    )
    return int(resultado.scalar_one())


async def test_soma_falta_minutos_bate_com_apuracoes_dia(
    sessao_f11: AsyncSession, contexto_f11: ContextoF11
) -> None:
    contexto = ContextoConsulta(
        tenant_id=contexto_f11.tenant_id,
        de=contexto_f11.dias_uteis[0],
        ate=contexto_f11.dias_uteis[-1],
    )
    resultado = await executar(
        sessao_f11,
        contexto_f11.tenant_id,
        "faltas",
        contexto_f11.relatorio_ids,
        filtros=contexto,
    )
    # So o colaborador C, ultimo dia util, tem falta > 0 (o WHERE do dataset
    # restringe a falta_minutos > 0).
    assert len(resultado.linhas) == 1
    linha = resultado.linhas[0]
    assert linha["faltaMinutos"] == 480
    assert linha["faltaMinutos"] == await _soma_direta_falta(sessao_f11, contexto_f11.tenant_id)
    # O tratamento semeado pela fixture e categoria 'abono', aprovado -- deve
    # aparecer como "tem tratamento".
    assert linha["temTratamento"] is True

    # `possuiAfastamentoRetroativo` não está em `colunas_disponiveis` da
    # fixture (T1/A1) -- chama a função de consulta diretamente.
    linhas_brutas = await executar_bruto(
        sessao_f11, contexto_f11.tenant_id, faltas, filtros=contexto
    )
    assert linhas_brutas[0]["possuiAfastamentoRetroativo"] is False


async def test_reflete_a_lacuna_do_adr011_sem_compensar(
    sessao_f11: AsyncSession, contexto_f11: ContextoF11
) -> None:
    """Acrescenta, localmente, um `Tratamento` categoria `afastamento`
    aprovado para o MESMO dia que já tem falta -- prova que `faltaMinutos`
    continua 480 (não zera, não é "corrigido" pelo dataset) mesmo com
    `possuiAfastamentoRetroativo = true`, exatamente o comportamento
    documentado pelo ADR-011 (`_carregar_marcacoes_e_tratamentos`, F4, não dá
    efeito numérico à categoria `afastamento`)."""
    colaborador_c = contexto_f11.colaboradores[2]
    ultimo_dia = contexto_f11.dias_uteis[-1]

    tipo_afastamento_retroativo_id = uuid.uuid4()
    await sessao_f11.execute(
        text(
            "INSERT INTO tipos_tratamento "
            "(id, tenant_id, codigo, nome, categoria, exige_aprovacao, exige_anexo, "
            " exige_motivo, permite_retroativo_dias, ativo) "
            "VALUES (:id, :tenant_id, :codigo, 'Afastamento retroativo de teste F11', "
            "        'afastamento', TRUE, FALSE, TRUE, 60, TRUE)"
        ),
        {
            "id": tipo_afastamento_retroativo_id,
            "tenant_id": contexto_f11.tenant_id,
            "codigo": f"AFAST-RETRO-{uuid.uuid4().hex[:8]}",
        },
    )
    await sessao_f11.execute(
        text(
            "INSERT INTO tratamentos "
            "(id, tenant_id, colaborador_id, vinculo_id, tipo_tratamento_id, data_referencia, "
            " motivo, origem, status, aprovado_em) "
            "VALUES (:id, :tenant_id, :colaborador_id, :vinculo_id, :tipo_tratamento_id, "
            "        :data_referencia, 'Afastamento retroativo sintetico ADR-011', 'rh', "
            "        'aprovado', now())"
        ),
        {
            "id": uuid.uuid4(),
            "tenant_id": contexto_f11.tenant_id,
            "colaborador_id": colaborador_c.colaborador_id,
            "vinculo_id": colaborador_c.vinculo_id,
            "tipo_tratamento_id": tipo_afastamento_retroativo_id,
            "data_referencia": ultimo_dia,
        },
    )
    await sessao_f11.flush()

    contexto = ContextoConsulta(
        tenant_id=contexto_f11.tenant_id,
        colaborador_id=colaborador_c.colaborador_id,
        de=ultimo_dia,
        ate=ultimo_dia,
    )
    resultado = await executar(
        sessao_f11,
        contexto_f11.tenant_id,
        "faltas",
        contexto_f11.relatorio_ids,
        filtros=contexto,
    )
    assert len(resultado.linhas) == 1
    linha = resultado.linhas[0]
    # A lacuna do ADR-011: o afastamento retroativo aprovado NAO zera a
    # falta -- apuracoes_dia.falta_minutos continua exatamente como F4
    # gravou (nunca recalculado por este dataset, proibicao 1).
    assert linha["faltaMinutos"] == 480
    # O tratamento de abono da fixture comum tambem existe para este mesmo
    # dia -- os dois fatos coexistem, lado a lado, sem um esconder o outro.
    assert linha["temTratamento"] is True

    linhas_brutas = await executar_bruto(
        sessao_f11, contexto_f11.tenant_id, faltas, filtros=contexto
    )
    assert linhas_brutas[0]["possuiAfastamentoRetroativo"] is True
