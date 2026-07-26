"""Resolvedor: vinculo inexistente ou de outro tenant responde
`PONTO-REC-001` (PCF, secao 6, T7).
"""

from __future__ import annotations

import datetime as dt
import secrets
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.erros import ErroDeAplicacao
from app.jornada.resolvedor.servico import resolver_jornada_do_dia
from tests.f3.conftest import ContextoF3, aplicar_tenant_teste


async def test_vinculo_inexistente_responde_rec_001(
    contexto_f3: ContextoF3, sessao_f3: AsyncSession
) -> None:
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await resolver_jornada_do_dia(
            sessao_f3, contexto_f3.tenant_id, uuid.uuid4(), dt.date(2026, 7, 27)
        )
    assert excinfo.value.codigo == "PONTO-REC-001"
    assert excinfo.value.http_status == 404


async def test_vinculo_de_outro_tenant_responde_rec_001(
    contexto_f3: ContextoF3, sessao_f3: AsyncSession
) -> None:
    """RLS restringe a consulta ao `app.tenant_id` corrente da sessao: um
    `vinculo_id` real, mas de outro tenant, e invisivel e responde
    `PONTO-REC-001` -- nunca vaza dado de outro tenant (ADR-001)."""
    sufixo = uuid.uuid4().hex[:10]
    tenant2_id = uuid.uuid4()
    empresa2_id = uuid.uuid4()
    colaborador2_id = uuid.uuid4()
    vinculo2_id = uuid.uuid4()

    # Semeia um segundo tenant, com sua propria empresa/colaborador/vinculo --
    # o `SET LOCAL app.tenant_id` precisa apontar para o tenant2 durante a
    # escrita, senao a policy de RLS recusa o INSERT (a linha nova nao bate
    # com o tenant corrente da sessao).
    await aplicar_tenant_teste(sessao_f3, tenant2_id)
    await sessao_f3.execute(
        text(
            "INSERT INTO tenants (id, slug, razao_social, nome_exibicao, status) "
            "VALUES (:id, :slug, 'Tenant Outro F3', 'Tenant Outro F3', 'ativo')"
        ),
        {"id": tenant2_id, "slug": f"f3-outro-{sufixo}"},
    )
    await sessao_f3.execute(
        text(
            "INSERT INTO empresas "
            "(id, tenant_id, tipo, cnpj, razao_social, nome_fantasia, uf, "
            " codigo_ibge_municipio, fuso_horario) "
            "VALUES (:id, :tenant_id, 'matriz', :cnpj, 'Empresa Outro Tenant', "
            "        'Empresa Outro Tenant', 'SP', '3550308', 'America/Sao_Paulo')"
        ),
        {
            "id": empresa2_id,
            "tenant_id": tenant2_id,
            "cnpj": f"{secrets.randbelow(10**14):014d}",
        },
    )
    await sessao_f3.execute(
        text(
            "INSERT INTO colaboradores "
            "(id, tenant_id, empresa_id, matricula, cpf, nome_completo, status) "
            "VALUES (:id, :tenant_id, :empresa_id, :matricula, :cpf, "
            "        'Colaborador Outro Tenant', 'ativo')"
        ),
        {
            "id": colaborador2_id,
            "tenant_id": tenant2_id,
            "empresa_id": empresa2_id,
            "matricula": f"MAT-OUTRO-{sufixo}",
            "cpf": f"{secrets.randbelow(10**11):011d}",
        },
    )
    await sessao_f3.execute(
        text(
            "INSERT INTO vinculos "
            "(id, tenant_id, colaborador_id, empresa_id, matricula_esocial, "
            " tipo_vinculo, data_inicio, apura_ponto, status) "
            "VALUES (:id, :tenant_id, :colaborador_id, :empresa_id, :esocial, "
            "        'empregado', :data_inicio, TRUE, 'ativo')"
        ),
        {
            "id": vinculo2_id,
            "tenant_id": tenant2_id,
            "colaborador_id": colaborador2_id,
            "empresa_id": empresa2_id,
            "esocial": f"ESOC-OUTRO-{sufixo}",
            "data_inicio": dt.date(2020, 1, 1),
        },
    )
    await sessao_f3.flush()

    # Volta o tenant corrente da sessao para o da fixture antes de resolver.
    await aplicar_tenant_teste(sessao_f3, contexto_f3.tenant_id)

    with pytest.raises(ErroDeAplicacao) as excinfo:
        await resolver_jornada_do_dia(
            sessao_f3, contexto_f3.tenant_id, vinculo2_id, dt.date(2026, 7, 27)
        )
    assert excinfo.value.codigo == "PONTO-REC-001"
