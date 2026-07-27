"""Testes de `decidirTratamento` (T9): aprovar/reprovar, eventos condicionados
a `solicitacao_id` e trava de período fechado."""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.apuracao.tratamento import decisao, eventos, servico
from app.core.erros import ErroDeAplicacao
from app.schemas import contrato as esquemas
from tests.f4.tratamento.conftest import ContextoTratamento


def _corpo_criar(ctx: ContextoTratamento, *, data_referencia: dt.date) -> esquemas.TratamentoCriar:
    return esquemas.TratamentoCriar(
        colaborador_id=ctx.colaborador_id,
        vinculo_id=ctx.vinculo_id,
        tipo_tratamento_id=ctx.tipo_tratamento_id,
        data_referencia=data_referencia,
        motivo="Atestado medico",
    )


async def _criar_solicitacao(
    sessao: AsyncSession, ctx: ContextoTratamento, *, protocolo: str
) -> uuid.UUID:
    tipo_solicitacao_id = uuid.uuid4()
    await sessao.execute(
        text(
            "INSERT INTO tipos_solicitacao (id, tenant_id, codigo, nome, categoria) "
            "VALUES (:id, :tenant_id, :codigo, 'Justificativa', 'justificativa')"
        ),
        {"id": tipo_solicitacao_id, "tenant_id": ctx.tenant_id, "codigo": f"TS-{protocolo}"},
    )
    solicitacao_id = uuid.uuid4()
    await sessao.execute(
        text(
            "INSERT INTO solicitacoes (id, tenant_id, tipo_solicitacao_id, colaborador_id, "
            " protocolo, descricao, status) "
            "VALUES (:id, :tenant_id, :tipo_solicitacao_id, :colaborador_id, :protocolo, "
            " 'Solicitacao de teste', 'pendente')"
        ),
        {
            "id": solicitacao_id,
            "tenant_id": ctx.tenant_id,
            "tipo_solicitacao_id": tipo_solicitacao_id,
            "colaborador_id": ctx.colaborador_id,
            "protocolo": protocolo,
        },
    )
    return solicitacao_id


async def test_aprovar_sem_solicitacao_nao_publica_ajuste_mas_publica_recalculo(
    sessao_tratamento: AsyncSession,
    contexto_tratamento: ContextoTratamento,
    apurar_dia_falso: None,
) -> None:
    eventos.limpar_barramento()
    tratamento = await servico.criar_tratamento(
        sessao_tratamento,
        contexto_tratamento.tenant_id,
        _corpo_criar(contexto_tratamento, data_referencia=dt.date(2026, 7, 10)),
        usuario_id=None,
    )
    corpo_decisao = esquemas.DecisaoRequisicao(decisao=esquemas.Decisao1.aprovar)
    decidido = await decisao.decidir_tratamento(
        sessao_tratamento,
        contexto_tratamento.tenant_id,
        tratamento.id,
        corpo_decisao,
        usuario_id=None,
    )
    assert decidido.status == "aprovado"

    tipos_publicados = [e["tipo"] for e in eventos.BARRAMENTO_INTERNO]
    assert "ajuste.aprovado" not in tipos_publicados
    assert "apuracao.recalculada" in tipos_publicados


async def test_aprovar_com_solicitacao_publica_os_dois_eventos(
    sessao_tratamento: AsyncSession,
    contexto_tratamento: ContextoTratamento,
    apurar_dia_falso: None,
) -> None:
    eventos.limpar_barramento()
    protocolo = f"2026-{uuid.uuid4().hex[:6]}"
    solicitacao_id = await _criar_solicitacao(
        sessao_tratamento, contexto_tratamento, protocolo=protocolo
    )

    corpo = _corpo_criar(contexto_tratamento, data_referencia=dt.date(2026, 7, 11))
    campos = corpo.model_dump(exclude_unset=True)
    campos["solicitacao_id"] = solicitacao_id
    corpo_com_solicitacao = esquemas.TratamentoCriar(**campos)
    tratamento = await servico.criar_tratamento(
        sessao_tratamento, contexto_tratamento.tenant_id, corpo_com_solicitacao, usuario_id=None
    )
    assert tratamento.solicitacao_id == solicitacao_id

    corpo_decisao = esquemas.DecisaoRequisicao(
        decisao=esquemas.Decisao1.aprovar, comentario="Conferido"
    )
    usuario_id = uuid.uuid4()
    await decisao.decidir_tratamento(
        sessao_tratamento,
        contexto_tratamento.tenant_id,
        tratamento.id,
        corpo_decisao,
        usuario_id=usuario_id,
    )

    envelopes_ajuste = [e for e in eventos.BARRAMENTO_INTERNO if e["tipo"] == "ajuste.aprovado"]
    assert len(envelopes_ajuste) == 1
    dados = envelopes_ajuste[0]["dados"]
    assert dados["solicitacaoId"] == str(solicitacao_id)
    assert dados["protocolo"] == protocolo
    assert dados["colaboradorId"] == str(contexto_tratamento.colaborador_id)
    assert dados["dataReferencia"] == "2026-07-11"
    assert dados["tratamentoId"] == str(tratamento.id)
    assert dados["aprovadorUsuarioId"] == str(usuario_id)
    assert dados["comentario"] == "Conferido"

    tipos_publicados = [e["tipo"] for e in eventos.BARRAMENTO_INTERNO]
    assert "apuracao.recalculada" in tipos_publicados


async def test_reprovar_sem_comentario_e_recusado(
    sessao_tratamento: AsyncSession, contexto_tratamento: ContextoTratamento
) -> None:
    tratamento = await servico.criar_tratamento(
        sessao_tratamento,
        contexto_tratamento.tenant_id,
        _corpo_criar(contexto_tratamento, data_referencia=dt.date(2026, 7, 12)),
        usuario_id=None,
    )
    corpo_decisao = esquemas.DecisaoRequisicao(decisao=esquemas.Decisao1.reprovar)
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await decisao.decidir_tratamento(
            sessao_tratamento,
            contexto_tratamento.tenant_id,
            tratamento.id,
            corpo_decisao,
            usuario_id=None,
        )
    assert excinfo.value.codigo == "PONTO-VAL-001"


async def test_reprovar_nunca_toca_apuracao(
    sessao_tratamento: AsyncSession, contexto_tratamento: ContextoTratamento
) -> None:
    eventos.limpar_barramento()
    tratamento = await servico.criar_tratamento(
        sessao_tratamento,
        contexto_tratamento.tenant_id,
        _corpo_criar(contexto_tratamento, data_referencia=dt.date(2026, 7, 13)),
        usuario_id=None,
    )
    corpo_decisao = esquemas.DecisaoRequisicao(
        decisao=esquemas.Decisao1.reprovar, comentario="Nao confere com o portao"
    )
    decidido = await decisao.decidir_tratamento(
        sessao_tratamento,
        contexto_tratamento.tenant_id,
        tratamento.id,
        corpo_decisao,
        usuario_id=None,
    )
    assert decidido.status == "reprovado"
    assert decidido.reprovado_motivo == "Nao confere com o portao"
    tipos_publicados = [e["tipo"] for e in eventos.BARRAMENTO_INTERNO]
    assert "apuracao.recalculada" not in tipos_publicados
    assert "ajuste.aprovado" not in tipos_publicados
    assert "ajuste.reprovado" not in tipos_publicados  # sem solicitacao_id


async def test_decidir_tratamento_fora_de_pendente_e_recusado(
    sessao_tratamento: AsyncSession, contexto_tratamento: ContextoTratamento
) -> None:
    tratamento = await servico.criar_tratamento(
        sessao_tratamento,
        contexto_tratamento.tenant_id,
        _corpo_criar(contexto_tratamento, data_referencia=dt.date(2026, 7, 14)),
        usuario_id=None,
    )
    tratamento.status = "cancelado"
    await sessao_tratamento.flush()

    corpo_decisao = esquemas.DecisaoRequisicao(decisao=esquemas.Decisao1.aprovar)
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await decisao.decidir_tratamento(
            sessao_tratamento,
            contexto_tratamento.tenant_id,
            tratamento.id,
            corpo_decisao,
            usuario_id=None,
        )
    assert excinfo.value.codigo == "PONTO-CONF-003"
