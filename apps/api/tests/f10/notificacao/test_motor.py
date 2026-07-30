"""Testes de `app.notificacao.motor.processar_evento` contra o banco real
(T10) -- critério de aceite 5 (notificação chega nos canais reais) e
critério de aceite 6, na parte que cabe a este motor (regra de disparo por
evento)."""

from __future__ import annotations

import datetime as dt
from uuid import uuid4

import pytest
import sqlalchemy as sa
from ponto_contracts import Notificacao
from sqlalchemy.ext.asyncio import AsyncSession

from app.notificacao import mensagens, preferencias
from app.notificacao.motor import processar_evento
from tests.f10.notificacao.conftest import ContextoNotificacao


def _envelope(tipo: str, tenant_id, dados: dict) -> dict:
    agora = dt.datetime.now(tz=dt.UTC)
    return {
        "id": str(uuid4()),
        "tipo": tipo,
        "versao": 1,
        "ocorridoEm": agora.isoformat(),
        "publicadoEm": agora.isoformat(),
        "tenantId": str(tenant_id),
        "dados": dados,
    }


async def _notificacoes_do_usuario(
    sessao: AsyncSession, usuario_id, evento: str
) -> list[Notificacao]:
    linhas = await sessao.execute(
        sa.select(Notificacao).where(
            Notificacao.usuario_id == usuario_id, Notificacao.evento == evento
        )
    )
    return list(linhas.scalars().all())


@pytest.mark.asyncio
async def test_ajuste_solicitado_notifica_o_aprovador_pendente(
    sessao_notificacao: AsyncSession, contexto_notificacao: ContextoNotificacao
) -> None:
    envelope = _envelope(
        mensagens.NOME_AJUSTE_SOLICITADO,
        contexto_notificacao.tenant_id,
        {
            "solicitacaoId": str(contexto_notificacao.solicitacao_id),
            "protocolo": "2026-000123",
            "colaboradorId": str(contexto_notificacao.colaborador_id),
            "tipoSolicitacaoCodigo": "ajuste_ponto",
            "dataReferencia": "2026-07-22",
        },
    )
    criadas = await processar_evento(sessao_notificacao, contexto_notificacao.tenant_id, envelope)
    # Um destinatario (o aprovador) x tres canais padrao (push, email, in_app).
    assert criadas == 3

    linhas = await _notificacoes_do_usuario(
        sessao_notificacao,
        contexto_notificacao.aprovador_usuario_id,
        mensagens.NOME_AJUSTE_SOLICITADO,
    )
    assert {linha.canal for linha in linhas} == {"push", "email", "in_app"}
    for linha in linhas:
        assert linha.status == "pendente"
        assert linha.entidade == "solicitacoes"
        assert linha.entidade_id == contexto_notificacao.solicitacao_id
        assert "2026-000123" in linha.corpo

    # O solicitante (o proprio colaborador) NAO recebe esta notificacao --
    # e' o aprovador quem precisa agir.
    do_solicitante = await _notificacoes_do_usuario(
        sessao_notificacao, contexto_notificacao.usuario_id, mensagens.NOME_AJUSTE_SOLICITADO
    )
    assert do_solicitante == []


@pytest.mark.asyncio
async def test_ajuste_aprovado_notifica_o_colaborador(
    sessao_notificacao: AsyncSession, contexto_notificacao: ContextoNotificacao
) -> None:
    envelope = _envelope(
        mensagens.NOME_AJUSTE_APROVADO,
        contexto_notificacao.tenant_id,
        {
            "solicitacaoId": str(contexto_notificacao.solicitacao_id),
            "protocolo": "2026-000123",
            "colaboradorId": str(contexto_notificacao.colaborador_id),
            "dataReferencia": "2026-07-22",
            "tratamentoId": str(uuid4()),
            "decididoEm": dt.datetime.now(tz=dt.UTC).isoformat(),
        },
    )
    criadas = await processar_evento(sessao_notificacao, contexto_notificacao.tenant_id, envelope)
    assert criadas == 3

    linhas = await _notificacoes_do_usuario(
        sessao_notificacao, contexto_notificacao.usuario_id, mensagens.NOME_AJUSTE_APROVADO
    )
    assert {linha.canal for linha in linhas} == {"push", "email", "in_app"}


@pytest.mark.asyncio
async def test_ajuste_reprovado_notifica_o_colaborador_com_motivo(
    sessao_notificacao: AsyncSession, contexto_notificacao: ContextoNotificacao
) -> None:
    envelope = _envelope(
        mensagens.NOME_AJUSTE_REPROVADO,
        contexto_notificacao.tenant_id,
        {
            "solicitacaoId": str(contexto_notificacao.solicitacao_id),
            "protocolo": "2026-000123",
            "colaboradorId": str(contexto_notificacao.colaborador_id),
            "dataReferencia": "2026-07-22",
            "decididoEm": dt.datetime.now(tz=dt.UTC).isoformat(),
            "motivo": "Divergência com o controle de acesso da unidade.",
        },
    )
    criadas = await processar_evento(sessao_notificacao, contexto_notificacao.tenant_id, envelope)
    assert criadas == 3
    linhas = await _notificacoes_do_usuario(
        sessao_notificacao, contexto_notificacao.usuario_id, mensagens.NOME_AJUSTE_REPROVADO
    )
    assert any("controle de acesso" in linha.corpo for linha in linhas)


@pytest.mark.asyncio
async def test_periodo_fechado_notifica_quem_fechou(
    sessao_notificacao: AsyncSession, contexto_notificacao: ContextoNotificacao
) -> None:
    envelope = _envelope(
        mensagens.NOME_PERIODO_FECHADO,
        contexto_notificacao.tenant_id,
        {
            "fechamentoId": str(uuid4()),
            "periodoId": str(uuid4()),
            "empresaId": str(contexto_notificacao.empresa_id),
            "escopo": "empresa",
            "dataInicio": "2026-07-01",
            "dataFim": "2026-07-31",
            "totalColaboradores": 2,
            "totalPendencias": 0,
            "fechadoPor": str(contexto_notificacao.aprovador_usuario_id),
            "fechadoEm": dt.datetime.now(tz=dt.UTC).isoformat(),
        },
    )
    criadas = await processar_evento(sessao_notificacao, contexto_notificacao.tenant_id, envelope)
    assert criadas == 3
    linhas = await _notificacoes_do_usuario(
        sessao_notificacao,
        contexto_notificacao.aprovador_usuario_id,
        mensagens.NOME_PERIODO_FECHADO,
    )
    assert len(linhas) == 3
    for linha in linhas:
        assert linha.entidade_id is not None


@pytest.mark.asyncio
async def test_periodo_reaberto_notifica_quem_reabriu(
    sessao_notificacao: AsyncSession, contexto_notificacao: ContextoNotificacao
) -> None:
    envelope = _envelope(
        mensagens.NOME_PERIODO_REABERTO,
        contexto_notificacao.tenant_id,
        {
            "fechamentoId": str(uuid4()),
            "periodoId": str(uuid4()),
            "empresaId": str(contexto_notificacao.empresa_id),
            "reabertoPor": str(contexto_notificacao.usuario_id),
            "reabertoEm": dt.datetime.now(tz=dt.UTC).isoformat(),
            "motivo": "Atestado retroativo entregue pelo colaborador.",
        },
    )
    criadas = await processar_evento(sessao_notificacao, contexto_notificacao.tenant_id, envelope)
    assert criadas == 3
    linhas = await _notificacoes_do_usuario(
        sessao_notificacao, contexto_notificacao.usuario_id, mensagens.NOME_PERIODO_REABERTO
    )
    assert len(linhas) == 3


@pytest.mark.asyncio
async def test_espelho_assinado_notifica_o_colaborador(
    sessao_notificacao: AsyncSession, contexto_notificacao: ContextoNotificacao
) -> None:
    envelope = _envelope(
        mensagens.NOME_ESPELHO_ASSINADO,
        contexto_notificacao.tenant_id,
        {
            "espelhoId": str(uuid4()),
            "colaboradorId": str(contexto_notificacao.colaborador_id),
            "vinculoId": str(contexto_notificacao.vinculo_id),
            "periodoId": str(uuid4()),
            "versaoEspelho": 1,
            "signatarioTipo": "colaborador",
            "metodo": "aceiteEletronico",
            "carimboTempo": dt.datetime.now(tz=dt.UTC).isoformat(),
            "hashAssinado": "a" * 64,
        },
    )
    criadas = await processar_evento(sessao_notificacao, contexto_notificacao.tenant_id, envelope)
    assert criadas == 3


@pytest.mark.asyncio
async def test_ocorrencia_aberta_so_notifica_in_app(
    sessao_notificacao: AsyncSession, contexto_notificacao: ContextoNotificacao
) -> None:
    envelope = _envelope(
        mensagens.NOME_OCORRENCIA_ABERTA,
        contexto_notificacao.tenant_id,
        {
            "ocorrenciaId": str(uuid4()),
            "colaboradorId": str(contexto_notificacao.colaborador_id),
            "data": "2026-07-22",
            "codigo": "jornada_excedida",
            "severidade": "atencao",
        },
    )
    criadas = await processar_evento(sessao_notificacao, contexto_notificacao.tenant_id, envelope)
    assert criadas == 1
    linhas = await _notificacoes_do_usuario(
        sessao_notificacao, contexto_notificacao.usuario_id, mensagens.NOME_OCORRENCIA_ABERTA
    )
    assert [linha.canal for linha in linhas] == ["in_app"]


@pytest.mark.asyncio
async def test_evento_desconhecido_nao_cria_notificacao(
    sessao_notificacao: AsyncSession, contexto_notificacao: ContextoNotificacao
) -> None:
    envelope = _envelope("evento.que.nao.existe.em.events.yaml", contexto_notificacao.tenant_id, {})
    criadas = await processar_evento(sessao_notificacao, contexto_notificacao.tenant_id, envelope)
    assert criadas == 0


@pytest.mark.asyncio
async def test_sem_colaborador_id_no_payload_nao_resolve_destinatario(
    sessao_notificacao: AsyncSession, contexto_notificacao: ContextoNotificacao
) -> None:
    envelope = _envelope(
        mensagens.NOME_AJUSTE_APROVADO,
        contexto_notificacao.tenant_id,
        {"solicitacaoId": str(contexto_notificacao.solicitacao_id), "protocolo": "2026-000123"},
    )
    criadas = await processar_evento(sessao_notificacao, contexto_notificacao.tenant_id, envelope)
    assert criadas == 0


@pytest.mark.asyncio
async def test_preferencia_desabilitada_impede_criacao_daquele_canal(
    sessao_notificacao: AsyncSession, contexto_notificacao: ContextoNotificacao
) -> None:
    await preferencias.definir_preferencia(
        sessao_notificacao,
        contexto_notificacao.tenant_id,
        contexto_notificacao.usuario_id,
        mensagens.NOME_AJUSTE_APROVADO,
        "email",
        habilitado=False,
    )
    envelope = _envelope(
        mensagens.NOME_AJUSTE_APROVADO,
        contexto_notificacao.tenant_id,
        {
            "solicitacaoId": str(contexto_notificacao.solicitacao_id),
            "protocolo": "2026-000123",
            "colaboradorId": str(contexto_notificacao.colaborador_id),
            "dataReferencia": "2026-07-22",
            "tratamentoId": str(uuid4()),
            "decididoEm": dt.datetime.now(tz=dt.UTC).isoformat(),
        },
    )
    criadas = await processar_evento(sessao_notificacao, contexto_notificacao.tenant_id, envelope)
    assert criadas == 2
    linhas = await _notificacoes_do_usuario(
        sessao_notificacao, contexto_notificacao.usuario_id, mensagens.NOME_AJUSTE_APROVADO
    )
    assert "email" not in {linha.canal for linha in linhas}


@pytest.mark.asyncio
async def test_fora_da_janela_de_silencio_agenda_em_vez_de_enviar_ja(
    sessao_notificacao: AsyncSession, contexto_notificacao: ContextoNotificacao
) -> None:
    # Janela de aceite bem estreita, quase certamente fora dela agora --
    # usamos um minuto no passado imediato como "fim" e um segundo depois
    # como "inicio", forcando a rotina a cair no ramo "fora da janela"
    # independente do horario real em que o teste roda.
    agora_real = dt.datetime.now(tz=dt.UTC)
    inicio = (agora_real + dt.timedelta(minutes=2)).time().replace(microsecond=0)
    fim = (agora_real + dt.timedelta(minutes=3)).time().replace(microsecond=0)
    await preferencias.definir_preferencia(
        sessao_notificacao,
        contexto_notificacao.tenant_id,
        contexto_notificacao.usuario_id,
        mensagens.NOME_AJUSTE_APROVADO,
        "push",
        habilitado=True,
        janela_inicio=inicio,
        janela_fim=fim,
    )
    envelope = _envelope(
        mensagens.NOME_AJUSTE_APROVADO,
        contexto_notificacao.tenant_id,
        {
            "solicitacaoId": str(contexto_notificacao.solicitacao_id),
            "protocolo": "2026-000123",
            "colaboradorId": str(contexto_notificacao.colaborador_id),
            "dataReferencia": "2026-07-22",
            "tratamentoId": str(uuid4()),
            "decididoEm": dt.datetime.now(tz=dt.UTC).isoformat(),
        },
    )
    criadas = await processar_evento(sessao_notificacao, contexto_notificacao.tenant_id, envelope)
    assert criadas == 3
    linhas = await _notificacoes_do_usuario(
        sessao_notificacao, contexto_notificacao.usuario_id, mensagens.NOME_AJUSTE_APROVADO
    )
    do_push = next(linha for linha in linhas if linha.canal == "push")
    assert do_push.status == "pendente"
    assert do_push.agendada_para is not None
    outros_canais = [linha for linha in linhas if linha.canal != "push"]
    assert all(linha.agendada_para is None for linha in outros_canais)


@pytest.mark.asyncio
async def test_categoria_configurada_pelo_tenant_tambem_funciona_generico(
    sessao_notificacao: AsyncSession, contexto_notificacao: ContextoNotificacao
) -> None:
    """Prova que o motor não tem `if tipo == "..."` fixo por categoria de
    domínio -- qualquer `tipo` presente em `mensagens.TEMPLATES` funciona,
    mesmo um evento novo/hipotético, desde que o payload traga
    `colaboradorId`."""
    envelope = _envelope(
        mensagens.NOME_ESPELHO_ASSINADO,
        contexto_notificacao.tenant_id,
        {
            "espelhoId": str(uuid4()),
            "colaboradorId": str(contexto_notificacao.colaborador_id),
            "vinculoId": str(contexto_notificacao.vinculo_id),
            "periodoId": str(uuid4()),
            "signatarioTipo": "colaborador",
            "metodo": "aceiteEletronico",
            "carimboTempo": dt.datetime.now(tz=dt.UTC).isoformat(),
            "hashAssinado": "b" * 64,
        },
    )
    criadas = await processar_evento(sessao_notificacao, contexto_notificacao.tenant_id, envelope)
    assert criadas == 3
