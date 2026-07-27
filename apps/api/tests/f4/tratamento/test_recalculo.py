"""Testes de recálculo determinístico e idempotente com diff auditado (T10).

Usa `apurar_dia_falso` (substituto de `app.apuracao.dominio.servico
.apurar_dia`, ver `_apurar_dia_fake.py`) porque o motor real é ownership
exclusivo de A1 e roda em paralelo com esta fase -- o que se testa AQUI é a
responsabilidade de `recalcular_periodo`: comparação de hash antes/depois,
diff auditado, contagem de dias pulados por período fechado sem abortar o
restante, e publicação de `apuracao.recalculada` uma vez por vínculo.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
import sqlalchemy as sa
from ponto_contracts import Auditoria
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.apuracao.tratamento import eventos
from app.apuracao.tratamento.recalculo import enfileirar_recalculo, recalcular_periodo
from app.core.erros import ErroDeAplicacao
from app.schemas import contrato as esquemas
from tests.f4.tratamento._apurar_dia_fake import definir_marcador
from tests.f4.tratamento.conftest import ContextoTratamento


async def test_recalcular_periodo_e_idempotente_sem_mudanca_de_insumo(
    sessao_tratamento: AsyncSession,
    contexto_tratamento: ContextoTratamento,
    apurar_dia_falso: None,
) -> None:
    eventos.limpar_barramento()
    dia = dt.date(2026, 7, 20)

    primeiro = await recalcular_periodo(
        sessao_tratamento,
        contexto_tratamento.tenant_id,
        vinculo_id=contexto_tratamento.vinculo_id,
        inicio=dia,
        fim=dia,
        motivo="manual",
    )
    assert primeiro.dias_processados == 1
    assert primeiro.dias_alterados == 1  # primeira materializacao: None -> algo

    linhas_auditoria_apos_primeiro = (
        await sessao_tratamento.execute(
            sa.select(sa.func.count())
            .select_from(Auditoria)
            .where(
                Auditoria.tenant_id == contexto_tratamento.tenant_id,
                Auditoria.entidade == "apuracoes_dia",
            )
        )
    ).scalar_one()
    assert linhas_auditoria_apos_primeiro == 1

    eventos.limpar_barramento()
    segundo = await recalcular_periodo(
        sessao_tratamento,
        contexto_tratamento.tenant_id,
        vinculo_id=contexto_tratamento.vinculo_id,
        inicio=dia,
        fim=dia,
        motivo="manual",
    )
    assert segundo.dias_processados == 1
    assert segundo.dias_alterados == 0  # no-op: mesmo hash_entrada

    linhas_auditoria_apos_segundo = (
        await sessao_tratamento.execute(
            sa.select(sa.func.count())
            .select_from(Auditoria)
            .where(
                Auditoria.tenant_id == contexto_tratamento.tenant_id,
                Auditoria.entidade == "apuracoes_dia",
            )
        )
    ).scalar_one()
    assert linhas_auditoria_apos_segundo == 1  # nenhuma linha nova
    assert eventos.BARRAMENTO_INTERNO == []  # nenhum evento na segunda chamada


async def test_recalcular_periodo_muda_apenas_o_dia_alterado(
    sessao_tratamento: AsyncSession,
    contexto_tratamento: ContextoTratamento,
    apurar_dia_falso: None,
) -> None:
    dias = [dt.date(2026, 8, 1), dt.date(2026, 8, 2), dt.date(2026, 8, 3)]
    resultado_inicial = await recalcular_periodo(
        sessao_tratamento,
        contexto_tratamento.tenant_id,
        vinculo_id=contexto_tratamento.vinculo_id,
        inicio=dias[0],
        fim=dias[-1],
        motivo="manual",
    )
    assert resultado_inicial.dias_alterados == 3

    # So o segundo dia recebe um marcador novo (simula um tratamento aprovado
    # que so afeta aquele dia).
    definir_marcador(contexto_tratamento.vinculo_id, dias[1], "tratamento-aprovado")

    resultado_final = await recalcular_periodo(
        sessao_tratamento,
        contexto_tratamento.tenant_id,
        vinculo_id=contexto_tratamento.vinculo_id,
        inicio=dias[0],
        fim=dias[-1],
        motivo="tratamento",
    )
    assert resultado_final.dias_processados == 3
    assert resultado_final.dias_alterados == 1

    linhas_diff = (
        (
            await sessao_tratamento.execute(
                sa.select(Auditoria).where(
                    Auditoria.tenant_id == contexto_tratamento.tenant_id,
                    Auditoria.entidade == "apuracoes_dia",
                    Auditoria.metadados["motivo"].astext == "tratamento",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(linhas_diff) == 1
    assert linhas_diff[0].metadados["data"] == dias[1].isoformat()


async def test_recalcular_periodo_pula_dia_fechado_sem_abortar_o_resto(
    sessao_tratamento: AsyncSession,
    contexto_tratamento: ContextoTratamento,
    apurar_dia_falso: None,
) -> None:
    inicio = dt.date(2026, 9, 1)
    meio = dt.date(2026, 9, 2)
    fim = dt.date(2026, 9, 3)

    periodo_id = uuid.uuid4()
    await sessao_tratamento.execute(
        text(
            "INSERT INTO periodos (id, tenant_id, empresa_id, codigo, tipo, "
            " data_inicio, data_fim, status) "
            "VALUES (:id, :tenant_id, :empresa_id, '2026-09-meio', 'personalizado', "
            " :data_inicio, :data_fim, 'fechado')"
        ),
        {
            "id": periodo_id,
            "tenant_id": contexto_tratamento.tenant_id,
            "empresa_id": contexto_tratamento.empresa_id,
            "data_inicio": meio,
            "data_fim": meio,
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
            "empresa_id": contexto_tratamento.empresa_id,
        },
    )

    resultado = await recalcular_periodo(
        sessao_tratamento,
        contexto_tratamento.tenant_id,
        vinculo_id=contexto_tratamento.vinculo_id,
        inicio=inicio,
        fim=fim,
        motivo="manual",
    )
    assert resultado.dias_processados == 2  # inicio e fim, nao o meio
    assert resultado.dias_ignorados_fechados == 1
    assert resultado.dias_ignorados_detalhe[0].data == meio


async def test_recalcular_periodo_sem_escopo_e_recusado(
    sessao_tratamento: AsyncSession, contexto_tratamento: ContextoTratamento
) -> None:
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await recalcular_periodo(
            sessao_tratamento,
            contexto_tratamento.tenant_id,
            inicio=dt.date(2026, 7, 1),
            fim=dt.date(2026, 7, 1),
            motivo="manual",
        )
    assert excinfo.value.codigo == "PONTO-VAL-001"


async def test_enfileirar_recalculo_resolve_vinculo_e_enfileira(
    sessao_tratamento: AsyncSession,
    contexto_tratamento: ContextoTratamento,
    redis_teste_url: str,
) -> None:
    corpo = esquemas.RecalculoRequisicao(
        vinculo_ids=[contexto_tratamento.vinculo_id],
        data_inicio=dt.date(2026, 7, 1),
        data_fim=dt.date(2026, 7, 2),
        motivo=esquemas.Motivo.manual,
    )
    job_id, total = await enfileirar_recalculo(
        sessao_tratamento, contexto_tratamento.tenant_id, corpo, redis_url=redis_teste_url
    )
    assert total == 1
    assert job_id is not None


async def test_enfileirar_recalculo_sem_escopo_e_recusado(
    sessao_tratamento: AsyncSession,
    contexto_tratamento: ContextoTratamento,
    redis_teste_url: str,
) -> None:
    corpo = esquemas.RecalculoRequisicao(
        data_inicio=dt.date(2026, 7, 1), data_fim=dt.date(2026, 7, 2)
    )
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await enfileirar_recalculo(
            sessao_tratamento, contexto_tratamento.tenant_id, corpo, redis_url=redis_teste_url
        )
    assert excinfo.value.codigo == "PONTO-VAL-001"
