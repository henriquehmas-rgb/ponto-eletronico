"""Testes de `app.apuracao.tratamento.fechamento.verificar_periodo_aberto`
(T9). Mesma consulta somente-leitura que a F3 implementou para
`periodos`/`fechamentos`; aqui só provamos que a cópia própria de A3 se
comporta identicamente: passa quando não há fechamento, e recusa
(`PONTO-PER-001`) quando um fechamento `status='fechado'` cobre a data e o
escopo do vínculo.
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.apuracao.tratamento.fechamento import (
    CODIGO_PERIODO_FECHADO,
    verificar_periodo_aberto,
)
from app.core.erros import ErroDeAplicacao
from tests.f4.tratamento.conftest import ContextoTratamento


async def test_periodo_aberto_nao_levanta_quando_fechamentos_vazio(
    sessao_tratamento: AsyncSession, contexto_tratamento: ContextoTratamento
) -> None:
    # Nenhuma fase anterior a F10 popula `fechamentos` -- este caminho e'
    # sempre verdadeiro hoje, como a F3 documentou para o caso analogo.
    await verificar_periodo_aberto(
        sessao_tratamento,
        contexto_tratamento.tenant_id,
        empresa_id=contexto_tratamento.empresa_id,
        data=date(2026, 7, 15),
        unidade_id=contexto_tratamento.unidade_id,
    )


async def test_periodo_fechado_levanta_ponto_per_001(
    sessao_tratamento: AsyncSession, contexto_tratamento: ContextoTratamento
) -> None:
    periodo_id = uuid.uuid4()
    fechamento_id = uuid.uuid4()
    await sessao_tratamento.execute(
        text(
            "INSERT INTO periodos (id, tenant_id, empresa_id, codigo, tipo, "
            " data_inicio, data_fim, status) "
            "VALUES (:id, :tenant_id, :empresa_id, '2026-07', 'mensal', "
            " '2026-07-01', '2026-07-31', 'fechado')"
        ),
        {
            "id": periodo_id,
            "tenant_id": contexto_tratamento.tenant_id,
            "empresa_id": contexto_tratamento.empresa_id,
        },
    )
    await sessao_tratamento.execute(
        text(
            "INSERT INTO fechamentos (id, tenant_id, periodo_id, empresa_id, "
            " escopo, status) "
            "VALUES (:id, :tenant_id, :periodo_id, :empresa_id, 'empresa', 'fechado')"
        ),
        {
            "id": fechamento_id,
            "tenant_id": contexto_tratamento.tenant_id,
            "periodo_id": periodo_id,
            "empresa_id": contexto_tratamento.empresa_id,
        },
    )

    with pytest.raises(ErroDeAplicacao) as excinfo:
        await verificar_periodo_aberto(
            sessao_tratamento,
            contexto_tratamento.tenant_id,
            empresa_id=contexto_tratamento.empresa_id,
            data=date(2026, 7, 15),
        )
    assert excinfo.value.codigo == CODIGO_PERIODO_FECHADO


async def test_periodo_fechado_de_outra_empresa_nao_afeta(
    sessao_tratamento: AsyncSession, contexto_tratamento: ContextoTratamento
) -> None:
    outra_empresa_id = uuid.uuid4()
    periodo_id = uuid.uuid4()
    await sessao_tratamento.execute(
        text(
            "INSERT INTO empresas (id, tenant_id, tipo, cnpj, razao_social, "
            " nome_fantasia, uf, codigo_ibge_municipio, fuso_horario) "
            "VALUES (:id, :tenant_id, 'matriz', :cnpj, 'Outra Empresa', 'Outra', "
            " 'SP', '3550308', 'America/Sao_Paulo')"
        ),
        {
            "id": outra_empresa_id,
            "tenant_id": contexto_tratamento.tenant_id,
            "cnpj": f"{uuid.uuid4().int % 10**14:014d}",
        },
    )
    await sessao_tratamento.execute(
        text(
            "INSERT INTO periodos (id, tenant_id, empresa_id, codigo, tipo, "
            " data_inicio, data_fim, status) "
            "VALUES (:id, :tenant_id, :empresa_id, '2026-07', 'mensal', "
            " '2026-07-01', '2026-07-31', 'fechado')"
        ),
        {
            "id": periodo_id,
            "tenant_id": contexto_tratamento.tenant_id,
            "empresa_id": outra_empresa_id,
        },
    )
    await sessao_tratamento.execute(
        text(
            "INSERT INTO fechamentos (id, tenant_id, periodo_id, empresa_id, "
            " escopo, status) "
            "VALUES (:id, :tenant_id, :periodo_id, :empresa_id, 'empresa', 'fechado')"
        ),
        {
            "id": uuid.uuid4(),
            "tenant_id": contexto_tratamento.tenant_id,
            "periodo_id": periodo_id,
            "empresa_id": outra_empresa_id,
        },
    )

    # A empresa do contexto (diferente da que fechou) continua aberta.
    await verificar_periodo_aberto(
        sessao_tratamento,
        contexto_tratamento.tenant_id,
        empresa_id=contexto_tratamento.empresa_id,
        data=date(2026, 7, 15),
    )
