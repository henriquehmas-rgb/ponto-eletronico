"""Testes de CRUD de tratamentos e tipos de tratamento (T8)."""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
import sqlalchemy as sa
from ponto_contracts import Tratamento
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.apuracao.tratamento import servico
from app.core.erros import ErroDeAplicacao
from app.schemas import contrato as esquemas
from tests.f4.tratamento.conftest import ContextoTratamento


def _corpo_criar(
    ctx: ContextoTratamento, *, data_referencia: dt.date, motivo: str = "Atestado medico"
) -> esquemas.TratamentoCriar:
    return esquemas.TratamentoCriar(
        colaborador_id=ctx.colaborador_id,
        vinculo_id=ctx.vinculo_id,
        tipo_tratamento_id=ctx.tipo_tratamento_id,
        data_referencia=data_referencia,
        motivo=motivo,
    )


async def test_criar_tratamento_sucesso(
    sessao_tratamento: AsyncSession, contexto_tratamento: ContextoTratamento
) -> None:
    corpo = _corpo_criar(contexto_tratamento, data_referencia=dt.date(2026, 7, 10))
    tratamento = await servico.criar_tratamento(
        sessao_tratamento, contexto_tratamento.tenant_id, corpo, usuario_id=None
    )
    assert tratamento.id is not None
    assert tratamento.status == "pendente"
    assert tratamento.motivo == "Atestado medico"
    assert tratamento.marcacao_id is None
    assert tratamento.marcacao_datahora is None


async def test_criar_tratamento_motivo_vazio_e_recusado(
    sessao_tratamento: AsyncSession, contexto_tratamento: ContextoTratamento
) -> None:
    corpo = _corpo_criar(contexto_tratamento, data_referencia=dt.date(2026, 7, 10), motivo="   ")
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.criar_tratamento(
            sessao_tratamento, contexto_tratamento.tenant_id, corpo, usuario_id=None
        )
    assert excinfo.value.codigo == "PONTO-VAL-001"


async def test_criar_tratamento_sem_vinculo_id_e_recusado(
    sessao_tratamento: AsyncSession, contexto_tratamento: ContextoTratamento
) -> None:
    """Achado de contrato (ver docstring de `servico.py`): `vinculoId` e
    opcional no schema HTTP mas NOT NULL no banco. Sem uma forma saneada de
    resolver o vinculo principal do colaborador nesta fase, exigimos o
    campo -- este teste apenas documenta e prova o comportamento."""
    corpo = esquemas.TratamentoCriar(
        colaborador_id=contexto_tratamento.colaborador_id,
        tipo_tratamento_id=contexto_tratamento.tipo_tratamento_id,
        data_referencia=dt.date(2026, 7, 10),
        motivo="Sem vinculo",
    )
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.criar_tratamento(
            sessao_tratamento, contexto_tratamento.tenant_id, corpo, usuario_id=None
        )
    assert excinfo.value.codigo == "PONTO-VAL-001"


async def test_criar_tratamento_em_periodo_fechado_responde_per_001(
    sessao_tratamento: AsyncSession, contexto_tratamento: ContextoTratamento
) -> None:
    periodo_id = uuid.uuid4()
    await sessao_tratamento.execute(
        text(
            "INSERT INTO periodos (id, tenant_id, empresa_id, codigo, tipo, "
            " data_inicio, data_fim, status) "
            "VALUES (:id, :tenant_id, :empresa_id, '2026-06', 'mensal', "
            " '2026-06-01', '2026-06-30', 'fechado')"
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
            "id": uuid.uuid4(),
            "tenant_id": contexto_tratamento.tenant_id,
            "periodo_id": periodo_id,
            "empresa_id": contexto_tratamento.empresa_id,
        },
    )

    corpo = _corpo_criar(contexto_tratamento, data_referencia=dt.date(2026, 6, 15))
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.criar_tratamento(
            sessao_tratamento, contexto_tratamento.tenant_id, corpo, usuario_id=None
        )
    assert excinfo.value.codigo == "PONTO-PER-001"


async def test_ck_tratamentos_marcacao_recusa_par_incompleto(
    sessao_tratamento: AsyncSession, contexto_tratamento: ContextoTratamento
) -> None:
    """Prova de desenho do `CHECK ck_tratamentos_marcacao` diretamente no
    banco (conectado como a role de aplicacao via `sessao_tratamento`):
    `marcacao_id` presente sem `marcacao_datahora` e recusado. O servico
    (`criar_tratamento`) nunca produz este estado -- ele sempre deriva os
    dois campos juntos (ver `servico.py`) -- mas o CHECK precisa existir e
    funcionar independentemente de quem escreve."""
    tratamento = Tratamento(
        tenant_id=contexto_tratamento.tenant_id,
        colaborador_id=contexto_tratamento.colaborador_id,
        vinculo_id=contexto_tratamento.vinculo_id,
        tipo_tratamento_id=contexto_tratamento.tipo_tratamento_id,
        data_referencia=dt.date(2026, 7, 1),
        marcacao_id=uuid.uuid4(),
        marcacao_datahora=None,
        motivo="Forcando o CHECK diretamente",
    )
    sessao_tratamento.add(tratamento)
    with pytest.raises(IntegrityError):
        await sessao_tratamento.flush()


async def test_atualizar_tratamento_fora_de_rascunho_pendente_e_recusado(
    sessao_tratamento: AsyncSession, contexto_tratamento: ContextoTratamento
) -> None:
    corpo = _corpo_criar(contexto_tratamento, data_referencia=dt.date(2026, 7, 10))
    tratamento = await servico.criar_tratamento(
        sessao_tratamento, contexto_tratamento.tenant_id, corpo, usuario_id=None
    )
    tratamento.status = "aprovado"
    await sessao_tratamento.flush()

    atualizacao = esquemas.TratamentoAtualizar(motivo="Nova justificativa")
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.atualizar_tratamento(
            sessao_tratamento,
            contexto_tratamento.tenant_id,
            tratamento.id,
            atualizacao,
            usuario_id=None,
        )
    assert excinfo.value.codigo == "PONTO-CONF-003"


async def test_atualizar_tratamento_nao_aceita_status_decidido_via_patch(
    sessao_tratamento: AsyncSession, contexto_tratamento: ContextoTratamento
) -> None:
    corpo = _corpo_criar(contexto_tratamento, data_referencia=dt.date(2026, 7, 10))
    tratamento = await servico.criar_tratamento(
        sessao_tratamento, contexto_tratamento.tenant_id, corpo, usuario_id=None
    )
    atualizacao = esquemas.TratamentoAtualizar(status=esquemas.Status24.aprovado)
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.atualizar_tratamento(
            sessao_tratamento,
            contexto_tratamento.tenant_id,
            tratamento.id,
            atualizacao,
            usuario_id=None,
        )
    assert excinfo.value.codigo == "PONTO-CONF-003"


async def test_cancelar_tratamento_pendente_nao_agenda_recalculo(
    sessao_tratamento: AsyncSession, contexto_tratamento: ContextoTratamento
) -> None:
    corpo = _corpo_criar(contexto_tratamento, data_referencia=dt.date(2026, 7, 10))
    tratamento = await servico.criar_tratamento(
        sessao_tratamento, contexto_tratamento.tenant_id, corpo, usuario_id=None
    )
    cancelado = await servico.cancelar_tratamento(
        sessao_tratamento, contexto_tratamento.tenant_id, tratamento.id, usuario_id=None
    )
    assert cancelado.status == "cancelado"
    assert cancelado.motivo == "Atestado medico"  # linha original preservada


async def test_cancelar_tratamento_aplicado_preserva_linha_e_audita(
    sessao_tratamento: AsyncSession,
    contexto_tratamento: ContextoTratamento,
    apurar_dia_falso: None,
) -> None:
    from ponto_contracts import Auditoria

    corpo = _corpo_criar(contexto_tratamento, data_referencia=dt.date(2026, 7, 10))
    tratamento = await servico.criar_tratamento(
        sessao_tratamento, contexto_tratamento.tenant_id, corpo, usuario_id=None
    )
    # Simula o que `apurar_dia` (A1) faria: consumir o tratamento aprovado.
    tratamento.status = "aprovado"
    tratamento.aplicado_em = dt.datetime.now(tz=dt.UTC)
    await sessao_tratamento.flush()
    motivo_original = tratamento.motivo

    cancelado = await servico.cancelar_tratamento(
        sessao_tratamento, contexto_tratamento.tenant_id, tratamento.id, usuario_id=None
    )
    assert cancelado.status == "cancelado"
    assert cancelado.motivo == motivo_original  # linha original preservada, nao reescrita
    assert cancelado.aplicado_em is not None

    linhas_auditoria = (
        (
            await sessao_tratamento.execute(
                sa.select(Auditoria).where(
                    Auditoria.tenant_id == contexto_tratamento.tenant_id,
                    Auditoria.entidade == "tratamentos",
                    Auditoria.entidade_id == tratamento.id,
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(linhas_auditoria) == 1
    assert linhas_auditoria[0].acao == "revogar"
    assert linhas_auditoria[0].valor_anterior == {"status": "aprovado"}
    assert linhas_auditoria[0].valor_novo == {"status": "cancelado"}


async def test_cancelar_tratamento_ja_cancelado_e_recusado(
    sessao_tratamento: AsyncSession, contexto_tratamento: ContextoTratamento
) -> None:
    corpo = _corpo_criar(contexto_tratamento, data_referencia=dt.date(2026, 7, 10))
    tratamento = await servico.criar_tratamento(
        sessao_tratamento, contexto_tratamento.tenant_id, corpo, usuario_id=None
    )
    await servico.cancelar_tratamento(
        sessao_tratamento, contexto_tratamento.tenant_id, tratamento.id, usuario_id=None
    )
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await servico.cancelar_tratamento(
            sessao_tratamento, contexto_tratamento.tenant_id, tratamento.id, usuario_id=None
        )
    assert excinfo.value.codigo == "PONTO-CONF-003"


async def test_listar_tratamentos_filtra_por_status(
    sessao_tratamento: AsyncSession, contexto_tratamento: ContextoTratamento
) -> None:
    pendente = await servico.criar_tratamento(
        sessao_tratamento,
        contexto_tratamento.tenant_id,
        _corpo_criar(contexto_tratamento, data_referencia=dt.date(2026, 7, 1)),
        usuario_id=None,
    )
    reprovado = await servico.criar_tratamento(
        sessao_tratamento,
        contexto_tratamento.tenant_id,
        _corpo_criar(contexto_tratamento, data_referencia=dt.date(2026, 7, 2)),
        usuario_id=None,
    )
    reprovado.status = "reprovado"
    await sessao_tratamento.flush()

    linhas, paginacao = await servico.listar_tratamentos(
        sessao_tratamento, contexto_tratamento.tenant_id, status="pendente"
    )
    ids = {linha.id for linha in linhas}
    assert pendente.id in ids
    assert reprovado.id not in ids
    assert paginacao.limite == 50


async def test_listar_tipos_tratamento(
    sessao_tratamento: AsyncSession, contexto_tratamento: ContextoTratamento
) -> None:
    linhas, _ = await servico.listar_tipos_tratamento(
        sessao_tratamento, contexto_tratamento.tenant_id
    )
    codigos = {linha.codigo for linha in linhas}
    assert any(codigo.startswith("JUST-") for codigo in codigos)
    for linha in linhas:
        assert linha.afeta_afd is False
