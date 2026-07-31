"""Dados extras, específicos dos datasets gerenciais/fiscais/financeiro/lgpd
(itens 13-24), sobre a fixture compartilhada da fase (`tests/f11/conftest.py`,
T1/A1). Mesmo padrão que a docstring daquele módulo já autoriza: "Cada teste
que precisar de dado adicional cria a própria linha extra localmente".

Import direto dos DATASETS via `app.relatorios.datasets.gerenciais` garante
que os 12 nomes fiquem registrados em `app.relatorios.catalogo` antes de
qualquer teste chamar `executar_dataset`.
"""

from __future__ import annotations

import datetime as dt
import secrets
import uuid
from dataclasses import dataclass

import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

import app.relatorios.datasets.gerenciais as _registra_datasets_gerenciais  # noqa: F401
from tests.f11.conftest import ContextoF11


@dataclass(frozen=True, slots=True)
class ExtrasGerenciais:
    """IDs dos dados extras semeados por este conftest, sobre `ContextoF11`."""

    centro_custo_id: uuid.UUID
    cargo_id: uuid.UUID
    salario_base: str
    escala_id: uuid.UUID
    turno_id: uuid.UUID
    rep_p_id: uuid.UUID
    dia_extra: dt.date


@pytest_asyncio.fixture
async def extras_gerenciais(
    sessao_f11: AsyncSession, contexto_f11: ContextoF11
) -> ExtrasGerenciais:
    sufixo = uuid.uuid4().hex[:8]
    tenant_id = contexto_f11.tenant_id
    empresa_id = contexto_f11.empresa_id

    centro_custo_id = uuid.uuid4()
    await sessao_f11.execute(
        text(
            "INSERT INTO centros_custo (id, tenant_id, empresa_id, codigo, nome, ativo) "
            "VALUES (:id, :tenant_id, :empresa_id, :codigo, 'Centro de Custo Teste', TRUE)"
        ),
        {
            "id": centro_custo_id,
            "tenant_id": tenant_id,
            "empresa_id": empresa_id,
            "codigo": f"CC-{sufixo}",
        },
    )

    cargo_id = uuid.uuid4()
    salario_base = "4400.00"
    await sessao_f11.execute(
        text(
            "INSERT INTO cargos (id, tenant_id, empresa_id, codigo, nome, salario_base, ativo) "
            "VALUES (:id, :tenant_id, :empresa_id, :codigo, 'Cargo de Teste', :salario, TRUE)"
        ),
        {
            "id": cargo_id,
            "tenant_id": tenant_id,
            "empresa_id": empresa_id,
            "codigo": f"CARGO-{sufixo}",
            "salario": salario_base,
        },
    )

    turno_id = uuid.uuid4()
    await sessao_f11.execute(
        text(
            "INSERT INTO turnos (id, tenant_id, empresa_id, codigo, nome, tipo, ativo) "
            "VALUES (:id, :tenant_id, :empresa_id, :codigo, 'Turno de Teste', 'diurno', TRUE)"
        ),
        {
            "id": turno_id,
            "tenant_id": tenant_id,
            "empresa_id": empresa_id,
            "codigo": f"TUR-{sufixo}",
        },
    )

    escala_id = uuid.uuid4()
    await sessao_f11.execute(
        text(
            "INSERT INTO escalas "
            "(id, tenant_id, empresa_id, codigo, nome, tipo, dias_ciclo, data_referencia, ativo) "
            "VALUES (:id, :tenant_id, :empresa_id, :codigo, 'Escala de Teste', '5x2', 7, "
            "        :data_referencia, TRUE)"
        ),
        {
            "id": escala_id,
            "tenant_id": tenant_id,
            "empresa_id": empresa_id,
            "codigo": f"ESC-{sufixo}",
            "data_referencia": dt.date(2020, 1, 1),
        },
    )

    rep_p_id = uuid.uuid4()
    cnpj = f"{secrets.randbelow(10**14):014d}"
    await sessao_f11.execute(
        text(
            "INSERT INTO rep_ps "
            "(id, tenant_id, empresa_id, identificador, numero_inpi, cnpj_desenvolvedor, "
            " razao_social_desenvolvedor, cnpj_empregador, razao_social_empregador, "
            " versao_programa, data_inicio_operacao, status) "
            "VALUES (:id, :tenant_id, :empresa_id, :identificador, '12345678', :cnpj_dev, "
            "        'SEEG Servicos de TI', :cnpj_emp, 'Empresa de Teste F11 Ltda', '1.0.0', "
            "        '2020-01-01', 'ativo')"
        ),
        {
            "id": rep_p_id,
            "tenant_id": tenant_id,
            "empresa_id": empresa_id,
            "identificador": f"REP-{sufixo}",
            "cnpj_dev": cnpj,
            "cnpj_emp": cnpj,
        },
    )

    # Vincula um dia extra (fora dos 3 dias uteis padrao da fixture) aos dois
    # primeiros colaboradores, com escala/turno/centro de custo preenchidos
    # -- necessario para escalas-previsto-realizado e horas-por-centro-custo.
    dia_extra = max(contexto_f11.dias_uteis) + dt.timedelta(days=7)
    for colaborador in contexto_f11.colaboradores[:2]:
        apuracao_dia_id = uuid.uuid4()
        await sessao_f11.execute(
            text(
                "INSERT INTO apuracoes_dia "
                "(id, tenant_id, vinculo_id, colaborador_id, data, empresa_id, unidade_id, "
                " departamento_id, centro_custo_id, escala_id, turno_id, tipo_dia, "
                " previsto_minutos, trabalhado_minutos, normais_minutos, extras_minutos, "
                " intrajornada_suprimida_minutos, interjornada_minutos, interjornada_violada, "
                " status) "
                "VALUES (:id, :tenant_id, :vinculo_id, :colaborador_id, :data, :empresa_id, "
                "        :unidade_id, :departamento_id, :centro_custo_id, :escala_id, :turno_id, "
                "        'util', 480, 500, 480, 20, 25, 480, TRUE, 'com_ocorrencia')"
            ),
            {
                "id": apuracao_dia_id,
                "tenant_id": tenant_id,
                "vinculo_id": colaborador.vinculo_id,
                "colaborador_id": colaborador.colaborador_id,
                "data": dia_extra,
                "empresa_id": empresa_id,
                "unidade_id": contexto_f11.unidade_id,
                "departamento_id": colaborador.departamento_id,
                "centro_custo_id": centro_custo_id,
                "escala_id": escala_id,
                "turno_id": turno_id,
            },
        )
        # `apuracao_dia_id` PRECISA ser preenchido: o dataset junta
        # `ocorrencias` a `apuracoes_dia` por essa FK (nao por
        # colaborador+data), mesmo padrao que a funcao real usa.
        await sessao_f11.execute(
            text(
                "INSERT INTO ocorrencias "
                "(id, tenant_id, colaborador_id, vinculo_id, apuracao_dia_id, data, codigo, "
                " severidade, descricao, status) "
                "VALUES (:id, :tenant_id, :colaborador_id, :vinculo_id, :apuracao_dia_id, :data, "
                "        'intrajornada_suprimida', 'alta', 'Intervalo suprimido de teste', "
                "        'aberta')"
            ),
            {
                "id": uuid.uuid4(),
                "tenant_id": tenant_id,
                "colaborador_id": colaborador.colaborador_id,
                "vinculo_id": colaborador.vinculo_id,
                "apuracao_dia_id": apuracao_dia_id,
                "data": dia_extra,
            },
        )
        await sessao_f11.execute(
            text(
                "INSERT INTO ocorrencias "
                "(id, tenant_id, colaborador_id, vinculo_id, apuracao_dia_id, data, codigo, "
                " severidade, descricao, status) "
                "VALUES (:id, :tenant_id, :colaborador_id, :vinculo_id, :apuracao_dia_id, :data, "
                "        'interjornada_violada', 'critica', 'Interjornada violada de teste', "
                "        'aberta')"
            ),
            {
                "id": uuid.uuid4(),
                "tenant_id": tenant_id,
                "colaborador_id": colaborador.colaborador_id,
                "vinculo_id": colaborador.vinculo_id,
                "apuracao_dia_id": apuracao_dia_id,
                "data": dia_extra,
            },
        )

    await sessao_f11.commit()
    from tests.f11.conftest import aplicar_tenant_teste

    await aplicar_tenant_teste(sessao_f11, tenant_id)

    return ExtrasGerenciais(
        centro_custo_id=centro_custo_id,
        cargo_id=cargo_id,
        salario_base=salario_base,
        escala_id=escala_id,
        turno_id=turno_id,
        rep_p_id=rep_p_id,
        dia_extra=dia_extra,
    )
