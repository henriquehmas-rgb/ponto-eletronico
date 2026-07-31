"""Testes do CRUD de agendamento de relatório (F11, T11/A3):
`app.relatorios.agendamentos.{criar_agendamento,listar_agendamentos,
calcular_proxima_execucao}`."""

from __future__ import annotations

import datetime as dt
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest
from ponto_contracts import RelatorioAgendamento
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.erros import ErroDeAplicacao
from app.relatorios.agendamentos import (
    calcular_proxima_execucao,
    criar_agendamento,
    listar_agendamentos,
)
from app.schemas import contrato as esquemas
from tests.f11.conftest import ContextoF11


def _corpo(
    *,
    relatorio_definicao_id: UUID,
    nome: str = "Agendamento de teste",
    cron: str = "0 8 1 * *",
    usuario_id: UUID | None = None,
    canal: esquemas.Canal5 = esquemas.Canal5.email,
    destinatarios: list[str] | None = None,
) -> esquemas.RelatorioAgendamentoCriar:
    return esquemas.RelatorioAgendamentoCriar(
        relatorioDefinicaoId=relatorio_definicao_id,
        usuarioId=usuario_id,
        nome=nome,
        parametros=None,
        formato=None,
        cron=cron,
        fusoHorario=None,
        canal=canal,
        destinatarios=destinatarios or ["rh@exemplo.com"],
        ativo=None,
    )


# =============================================================================
# calcular_proxima_execucao
# =============================================================================


def test_calcular_proxima_execucao_respeita_fuso() -> None:
    referencia = dt.datetime(2026, 8, 1, 7, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
    proxima = calcular_proxima_execucao(
        "0 8 1 * *", fuso_horario="America/Sao_Paulo", referencia=referencia
    )
    assert proxima.hour == 8
    assert proxima.day == 1
    assert proxima > referencia


def test_calcular_proxima_execucao_cron_invalido_falha() -> None:
    with pytest.raises(ErroDeAplicacao) as excinfo:
        calcular_proxima_execucao("nao e um cron", fuso_horario="America/Sao_Paulo")
    assert excinfo.value.codigo == "PONTO-VAL-001"


def test_calcular_proxima_execucao_fuso_invalido_falha() -> None:
    with pytest.raises(ErroDeAplicacao) as excinfo:
        calcular_proxima_execucao("0 8 1 * *", fuso_horario="Nao/Existe")
    assert excinfo.value.codigo == "PONTO-VAL-001"


# =============================================================================
# criar_agendamento
# =============================================================================


async def test_criar_agendamento_com_sucesso(
    sessao_f11: AsyncSession, contexto_f11: ContextoF11
) -> None:
    definicao_id = contexto_f11.relatorio_ids["auditoria"]
    solicitante = contexto_f11.usuario_rh_id
    corpo = _corpo(relatorio_definicao_id=definicao_id)

    agendamento = await criar_agendamento(
        sessao_f11, contexto_f11.tenant_id, corpo, usuario_id_solicitante=solicitante
    )

    assert agendamento.id is not None
    assert agendamento.relatorio_definicao_id == definicao_id
    assert agendamento.nome == "Agendamento de teste"
    assert agendamento.cron == "0 8 1 * *"
    assert agendamento.proxima_execucao_em is not None
    assert agendamento.usuario_id == solicitante  # corpo nao informou, cai para o solicitante
    assert agendamento.ativo is True


async def test_criar_agendamento_usuario_id_do_corpo_tem_prioridade(
    sessao_f11: AsyncSession, contexto_f11: ContextoF11
) -> None:
    definicao_id = contexto_f11.relatorio_ids["auditoria"]
    usuario_explicito = contexto_f11.colaboradores[0].usuario_id
    corpo = _corpo(
        relatorio_definicao_id=definicao_id,
        nome="Agendamento com usuario explicito",
        usuario_id=usuario_explicito,
    )

    agendamento = await criar_agendamento(
        sessao_f11, contexto_f11.tenant_id, corpo, usuario_id_solicitante=contexto_f11.usuario_rh_id
    )
    assert agendamento.usuario_id == usuario_explicito


async def test_criar_agendamento_relatorio_definicao_inexistente_falha(
    sessao_f11: AsyncSession, contexto_f11: ContextoF11
) -> None:
    corpo = _corpo(relatorio_definicao_id=uuid4())
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await criar_agendamento(
            sessao_f11,
            contexto_f11.tenant_id,
            corpo,
            usuario_id_solicitante=contexto_f11.usuario_rh_id,
        )
    assert excinfo.value.codigo == "PONTO-REC-001"


async def test_criar_agendamento_cron_invalido_falha(
    sessao_f11: AsyncSession, contexto_f11: ContextoF11
) -> None:
    definicao_id = contexto_f11.relatorio_ids["auditoria"]
    corpo = _corpo(relatorio_definicao_id=definicao_id, nome="Cron ruim", cron="lixo")
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await criar_agendamento(
            sessao_f11,
            contexto_f11.tenant_id,
            corpo,
            usuario_id_solicitante=contexto_f11.usuario_rh_id,
        )
    assert excinfo.value.codigo == "PONTO-VAL-001"


async def test_criar_agendamento_nome_duplicado_falha(
    sessao_f11: AsyncSession, contexto_f11: ContextoF11
) -> None:
    definicao_id = contexto_f11.relatorio_ids["auditoria"]
    corpo = _corpo(relatorio_definicao_id=definicao_id, nome="Nome unico de teste")
    await criar_agendamento(
        sessao_f11, contexto_f11.tenant_id, corpo, usuario_id_solicitante=contexto_f11.usuario_rh_id
    )
    await sessao_f11.commit()
    from tests.f11.conftest import aplicar_tenant_teste

    await aplicar_tenant_teste(sessao_f11, contexto_f11.tenant_id)

    corpo_duplicado = _corpo(relatorio_definicao_id=definicao_id, nome="Nome unico de teste")
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await criar_agendamento(
            sessao_f11,
            contexto_f11.tenant_id,
            corpo_duplicado,
            usuario_id_solicitante=contexto_f11.usuario_rh_id,
        )
    assert excinfo.value.codigo == "PONTO-CONF-001"


# =============================================================================
# listar_agendamentos
# =============================================================================


async def test_listar_agendamentos_filtra_por_canal_e_ativo(
    sessao_f11: AsyncSession, contexto_f11: ContextoF11
) -> None:
    definicao_id = contexto_f11.relatorio_ids["auditoria"]
    await criar_agendamento(
        sessao_f11,
        contexto_f11.tenant_id,
        _corpo(relatorio_definicao_id=definicao_id, nome="Email um", canal=esquemas.Canal5.email),
        usuario_id_solicitante=contexto_f11.usuario_rh_id,
    )
    await criar_agendamento(
        sessao_f11,
        contexto_f11.tenant_id,
        _corpo(
            relatorio_definicao_id=definicao_id,
            nome="Webhook um",
            canal=esquemas.Canal5.webhook,
            destinatarios=["https://cliente.exemplo.com/hook"],
        ),
        usuario_id_solicitante=contexto_f11.usuario_rh_id,
    )
    await sessao_f11.commit()
    from tests.f11.conftest import aplicar_tenant_teste

    await aplicar_tenant_teste(sessao_f11, contexto_f11.tenant_id)

    linhas_email, _ = await listar_agendamentos(sessao_f11, contexto_f11.tenant_id, canal="email")
    nomes_email = {linha.nome for linha in linhas_email}
    assert "Email um" in nomes_email
    assert "Webhook um" not in nomes_email

    linhas_webhook, _ = await listar_agendamentos(
        sessao_f11, contexto_f11.tenant_id, canal="webhook"
    )
    nomes_webhook = {linha.nome for linha in linhas_webhook}
    assert "Webhook um" in nomes_webhook
    assert "Email um" not in nomes_webhook


async def test_listar_agendamentos_ignora_excluidos(
    sessao_f11: AsyncSession, contexto_f11: ContextoF11
) -> None:
    definicao_id = contexto_f11.relatorio_ids["auditoria"]
    criado = await criar_agendamento(
        sessao_f11,
        contexto_f11.tenant_id,
        _corpo(relatorio_definicao_id=definicao_id, nome="Sera excluido"),
        usuario_id_solicitante=contexto_f11.usuario_rh_id,
    )
    await sessao_f11.flush()
    await sessao_f11.execute(
        text("UPDATE relatorio_agendamentos SET excluido_em = now() WHERE id = :id"),
        {"id": criado.id},
    )
    await sessao_f11.commit()
    from tests.f11.conftest import aplicar_tenant_teste

    await aplicar_tenant_teste(sessao_f11, contexto_f11.tenant_id)

    linhas, _ = await listar_agendamentos(sessao_f11, contexto_f11.tenant_id)
    assert all(linha.id != criado.id for linha in linhas)


async def test_listar_agendamentos_ordena_por_nome(
    sessao_f11: AsyncSession, contexto_f11: ContextoF11
) -> None:
    definicao_id = contexto_f11.relatorio_ids["auditoria"]
    for nome in ("Zebra", "Abacaxi"):
        await criar_agendamento(
            sessao_f11,
            contexto_f11.tenant_id,
            _corpo(relatorio_definicao_id=definicao_id, nome=f"Ordenacao {nome}"),
            usuario_id_solicitante=contexto_f11.usuario_rh_id,
        )
    await sessao_f11.commit()
    from tests.f11.conftest import aplicar_tenant_teste

    await aplicar_tenant_teste(sessao_f11, contexto_f11.tenant_id)

    linhas, _ = await listar_agendamentos(sessao_f11, contexto_f11.tenant_id, ordenar="nome:asc")
    nomes = [linha.nome for linha in linhas if linha.nome.startswith("Ordenacao")]
    assert nomes == sorted(nomes)


def test_relatorio_agendamento_model_aceita_campos_basicos() -> None:
    """Sanidade do model SQLAlchemy usado nos testes acima (sem tocar o
    banco) -- garante que a suíte não depende silenciosamente de um campo
    que não existe mais no model gerado."""
    instancia = RelatorioAgendamento(
        id=uuid4(), nome="x", cron="0 0 * * *", canal="email", destinatarios=[]
    )
    assert instancia.nome == "x"
