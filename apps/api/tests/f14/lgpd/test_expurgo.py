"""Testes de `app.lgpd.expurgo` (F14/A3).

Cobre o aceite mais concreto de A3 para a rotina de retencao: "politica com
prazo curto sintetico, registro vencido, rotina roda, registro tratado
conforme `acao`" -- testado contra banco real, para as entidades com
implementacao de verdade (`biometria`, `sessao`, `notificacao`) -- e a
blindagem inegociavel de `marcacao`/`auditoria` (nunca antes do prazo legal,
e nesta fase nunca automaticamente mesmo depois).
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Awaitable, Callable
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from ponto_contracts import (
    Biometria,
    BiometriaTemplate,
    Marcacao,
    Notificacao,
    PoliticaRetencao,
    Sessao,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.lgpd import expurgo as servico
from tests.f14.lgpd.conftest import ContextoOrganizacional

pytestmark = pytest.mark.asyncio


async def _politica(sessao: AsyncSession, politica_id: UUID) -> PoliticaRetencao:
    return (
        await sessao.execute(sa.select(PoliticaRetencao).where(PoliticaRetencao.id == politica_id))
    ).scalar_one()


# =============================================================================
# Blindagem de marcacao/auditoria -- nunca antes do prazo legal, nunca
# automaticamente nesta fase mesmo depois.
# =============================================================================


async def test_marcacao_com_prazo_curto_mal_configurado_nunca_e_tocada(
    sessao_f14: AsyncSession,
    contexto_organizacional: ContextoOrganizacional,
    criar_colaborador: Callable[..., Awaitable[UUID]],
    criar_vinculo: Callable[..., Awaitable[UUID]],
    criar_marcacao: Callable[..., Awaitable[UUID]],
    criar_politica_retencao: Callable[..., Awaitable[UUID]],
) -> None:
    colaborador_id = await criar_colaborador()
    vinculo_id = await criar_vinculo(colaborador_id=colaborador_id)
    await criar_marcacao(colaborador_id=colaborador_id, vinculo_id=vinculo_id, cpf="99988877766")
    await sessao_f14.flush()

    # Politica mal configurada: 1 dia, MUITO abaixo dos 1825 dias legais.
    politica_id = await criar_politica_retencao(entidade="marcacao", prazo_dias=1, acao="eliminar")
    await sessao_f14.flush()

    total_antes = await _contar_marcacoes(sessao_f14, colaborador_id)

    resultados = await servico.aplicar_politicas_vencidas(
        sessao_f14, tenant_id=contexto_organizacional.tenant_id, politica_id=politica_id
    )
    assert len(resultados) == 1
    resultado = resultados[0]
    assert resultado.executado is False
    assert resultado.registros_afetados == 0
    assert "1825" in resultado.motivo or "guarda legal" in resultado.motivo

    total_depois = await _contar_marcacoes(sessao_f14, colaborador_id)
    assert total_depois == total_antes  # nada foi apagado
    assert total_depois == 1

    politica = await _politica(sessao_f14, politica_id)
    assert politica.ultima_execucao_em is not None  # rodou e decidiu nao agir
    assert politica.registros_ultima_execucao == 0


async def test_marcacao_com_prazo_legal_cumprido_ainda_assim_nao_e_tocada(
    sessao_f14: AsyncSession,
    contexto_organizacional: ContextoOrganizacional,
    criar_politica_retencao: Callable[..., Awaitable[UUID]],
) -> None:
    """Mesmo com prazo_dias >= 1825 (guarda legal tecnicamente cumprida), o
    motor nao executa nada sobre marcacao nesta fase -- append-only com
    gatilho de banco, procedimento manual supervisionado pendente."""
    politica_id = await criar_politica_retencao(
        entidade="marcacao", prazo_dias=1825, acao="arquivar"
    )
    await sessao_f14.flush()

    resultados = await servico.aplicar_politicas_vencidas(
        sessao_f14, tenant_id=contexto_organizacional.tenant_id, politica_id=politica_id
    )
    assert resultados[0].executado is False
    assert resultados[0].registros_afetados == 0
    assert "append-only" in resultados[0].motivo


async def test_auditoria_recebe_a_mesma_blindagem(
    sessao_f14: AsyncSession,
    contexto_organizacional: ContextoOrganizacional,
    criar_politica_retencao: Callable[..., Awaitable[UUID]],
) -> None:
    politica_id = await criar_politica_retencao(
        entidade="auditoria", prazo_dias=30, acao="eliminar"
    )
    await sessao_f14.flush()

    resultados = await servico.aplicar_politicas_vencidas(
        sessao_f14, tenant_id=contexto_organizacional.tenant_id, politica_id=politica_id
    )
    assert resultados[0].executado is False
    assert resultados[0].registros_afetados == 0


# =============================================================================
# Biometria -- expurgo REAL do template, com prazo curto sintetico.
# =============================================================================


async def test_biometria_vencida_e_expurgada_de_verdade(
    sessao_f14: AsyncSession,
    contexto_organizacional: ContextoOrganizacional,
    criar_colaborador: Callable[..., Awaitable[UUID]],
    criar_biometria_com_template: Callable[..., Awaitable[UUID]],
    criar_politica_retencao: Callable[..., Awaitable[UUID]],
) -> None:
    colaborador_id = await criar_colaborador()
    biometria_id = await criar_biometria_com_template(
        colaborador_id=colaborador_id, status="revogada"
    )
    # Forca a credencial a parecer vencida ha 5 dias.
    biometria = (
        await sessao_f14.execute(sa.select(Biometria).where(Biometria.id == biometria_id))
    ).scalar_one()
    biometria.revogada_em = dt.datetime.now(tz=dt.UTC) - dt.timedelta(days=5)
    await sessao_f14.flush()

    # Prazo curto SINTETICO: 1 dia (bem menor que qualquer prazo real de
    # produto) -- exatamente o padrao pedido pelo aceite de A3.
    politica_id = await criar_politica_retencao(entidade="biometria", prazo_dias=1, acao="eliminar")
    await sessao_f14.flush()

    resultados = await servico.aplicar_politicas_vencidas(
        sessao_f14, tenant_id=contexto_organizacional.tenant_id, politica_id=politica_id
    )
    assert resultados[0].executado is True
    assert resultados[0].registros_afetados == 1

    total_templates = (
        await sessao_f14.execute(
            sa.select(sa.func.count(BiometriaTemplate.id)).where(
                BiometriaTemplate.biometria_id == biometria_id
            )
        )
    ).scalar_one()
    assert total_templates == 0

    await sessao_f14.refresh(biometria)
    assert biometria.status == "expirada"

    politica = await _politica(sessao_f14, politica_id)
    assert politica.registros_ultima_execucao == 1
    assert politica.proxima_execucao_em is not None


async def test_biometria_ainda_nao_vencida_nao_e_tocada(
    sessao_f14: AsyncSession,
    contexto_organizacional: ContextoOrganizacional,
    criar_colaborador: Callable[..., Awaitable[UUID]],
    criar_biometria_com_template: Callable[..., Awaitable[UUID]],
    criar_politica_retencao: Callable[..., Awaitable[UUID]],
) -> None:
    colaborador_id = await criar_colaborador()
    biometria_id = await criar_biometria_com_template(
        colaborador_id=colaborador_id, status="revogada"
    )
    biometria = (
        await sessao_f14.execute(sa.select(Biometria).where(Biometria.id == biometria_id))
    ).scalar_one()
    biometria.revogada_em = dt.datetime.now(tz=dt.UTC)  # revogada AGORA
    await sessao_f14.flush()

    # Prazo de 30 dias: a revogacao de agora ainda nao venceu.
    politica_id = await criar_politica_retencao(
        entidade="biometria", prazo_dias=30, acao="eliminar"
    )
    await sessao_f14.flush()

    resultados = await servico.aplicar_politicas_vencidas(
        sessao_f14, tenant_id=contexto_organizacional.tenant_id, politica_id=politica_id
    )
    assert resultados[0].registros_afetados == 0

    total_templates = (
        await sessao_f14.execute(
            sa.select(sa.func.count(BiometriaTemplate.id)).where(
                BiometriaTemplate.biometria_id == biometria_id
            )
        )
    ).scalar_one()
    assert total_templates == 1  # intacto


async def test_biometria_acao_arquivar_nao_suportada(
    sessao_f14: AsyncSession,
    contexto_organizacional: ContextoOrganizacional,
    criar_politica_retencao: Callable[..., Awaitable[UUID]],
) -> None:
    politica_id = await criar_politica_retencao(entidade="biometria", prazo_dias=1, acao="arquivar")
    await sessao_f14.flush()
    resultados = await servico.aplicar_politicas_vencidas(
        sessao_f14, tenant_id=contexto_organizacional.tenant_id, politica_id=politica_id
    )
    assert resultados[0].executado is False
    assert "arquivar" in resultados[0].motivo


# =============================================================================
# Sessao e notificacao -- delecao generica por coluna de tempo.
# =============================================================================


async def test_sessao_vencida_e_removida(
    sessao_f14: AsyncSession,
    contexto_organizacional: ContextoOrganizacional,
    criar_colaborador: Callable[..., Awaitable[UUID]],
    criar_politica_retencao: Callable[..., Awaitable[UUID]],
) -> None:
    colaborador_id = await criar_colaborador()
    usuario_id = await _criar_usuario_minimo(sessao_f14, contexto_organizacional, colaborador_id)

    agora = dt.datetime.now(tz=dt.UTC)
    sessao_encerrada = Sessao(
        tenant_id=contexto_organizacional.tenant_id,
        usuario_id=usuario_id,
        canal="web",
        iniciada_em=agora - dt.timedelta(days=10),
        ultima_atividade_em=agora - dt.timedelta(days=9),
        expira_em=agora - dt.timedelta(days=9),
        encerrada_em=agora - dt.timedelta(days=9),
        motivo_encerramento="logout",
    )
    sessao_f14.add(sessao_encerrada)
    await sessao_f14.flush()
    sessao_id = sessao_encerrada.id

    politica_id = await criar_politica_retencao(entidade="sessao", prazo_dias=1, acao="eliminar")
    await sessao_f14.flush()

    resultados = await servico.aplicar_politicas_vencidas(
        sessao_f14, tenant_id=contexto_organizacional.tenant_id, politica_id=politica_id
    )
    assert resultados[0].executado is True
    assert resultados[0].registros_afetados == 1

    restante = (
        await sessao_f14.execute(sa.select(sa.func.count(Sessao.id)).where(Sessao.id == sessao_id))
    ).scalar_one()
    assert restante == 0


async def test_notificacao_vencida_e_removida(
    sessao_f14: AsyncSession,
    contexto_organizacional: ContextoOrganizacional,
    criar_colaborador: Callable[..., Awaitable[UUID]],
    criar_politica_retencao: Callable[..., Awaitable[UUID]],
) -> None:
    colaborador_id = await criar_colaborador()
    agora = dt.datetime.now(tz=dt.UTC)
    notificacao = Notificacao(
        tenant_id=contexto_organizacional.tenant_id,
        colaborador_id=colaborador_id,
        canal="in_app",
        evento="teste.evento",
        titulo="Titulo de teste",
        corpo="Corpo de teste",
        status="lida",
        criado_em=agora - dt.timedelta(days=10),
    )
    sessao_f14.add(notificacao)
    await sessao_f14.flush()

    politica_id = await criar_politica_retencao(
        entidade="notificacao", prazo_dias=1, acao="eliminar"
    )
    await sessao_f14.flush()

    resultados = await servico.aplicar_politicas_vencidas(
        sessao_f14, tenant_id=contexto_organizacional.tenant_id, politica_id=politica_id
    )
    assert resultados[0].executado is True
    assert resultados[0].registros_afetados == 1

    restante = (
        await sessao_f14.execute(
            sa.select(sa.func.count(Notificacao.id)).where(Notificacao.id == notificacao.id)
        )
    ).scalar_one()
    assert restante == 0


# =============================================================================
# Entidades reconhecidas sem implementacao, e filtro de politicas vencidas.
# =============================================================================


async def test_entidade_nao_implementada_devolve_motivo_explicito_sem_excecao(
    sessao_f14: AsyncSession,
    contexto_organizacional: ContextoOrganizacional,
    criar_politica_retencao: Callable[..., Awaitable[UUID]],
) -> None:
    politica_id = await criar_politica_retencao(
        entidade="documento", prazo_dias=30, acao="eliminar"
    )
    await sessao_f14.flush()

    resultados = await servico.aplicar_politicas_vencidas(
        sessao_f14, tenant_id=contexto_organizacional.tenant_id, politica_id=politica_id
    )
    assert resultados[0].executado is False
    assert "sem implementacao" in resultados[0].motivo.lower()


async def test_politica_nao_vencida_nao_e_aplicada(
    sessao_f14: AsyncSession,
    contexto_organizacional: ContextoOrganizacional,
    criar_politica_retencao: Callable[..., Awaitable[UUID]],
) -> None:
    futuro = dt.datetime.now(tz=dt.UTC) + dt.timedelta(days=30)
    await criar_politica_retencao(
        entidade="sessao", prazo_dias=1, acao="eliminar", proxima_execucao_em=futuro
    )
    await sessao_f14.flush()

    resultados = await servico.aplicar_politicas_vencidas(
        sessao_f14, tenant_id=contexto_organizacional.tenant_id
    )
    assert resultados == []


async def test_politica_inativa_nao_e_aplicada(
    sessao_f14: AsyncSession,
    contexto_organizacional: ContextoOrganizacional,
    criar_politica_retencao: Callable[..., Awaitable[UUID]],
) -> None:
    await criar_politica_retencao(entidade="sessao", prazo_dias=1, acao="eliminar", ativo=False)
    await sessao_f14.flush()

    resultados = await servico.aplicar_politicas_vencidas(
        sessao_f14, tenant_id=contexto_organizacional.tenant_id
    )
    assert resultados == []


async def _contar_marcacoes(sessao: AsyncSession, colaborador_id: UUID) -> int:
    resultado = await sessao.execute(
        sa.select(sa.func.count(Marcacao.id)).where(Marcacao.colaborador_id == colaborador_id)
    )
    return resultado.scalar_one()


async def _criar_usuario_minimo(
    sessao: AsyncSession, contexto: ContextoOrganizacional, colaborador_id: UUID
) -> UUID:
    usuario_id = uuid4()
    await sessao.execute(
        sa.text(
            "INSERT INTO usuarios (id, tenant_id, colaborador_id, email, nome_completo, status) "
            "VALUES (:id, :tenant_id, :colaborador_id, :email, :nome, 'ativo')"
        ),
        {
            "id": usuario_id,
            "tenant_id": contexto.tenant_id,
            "colaborador_id": colaborador_id,
            "email": f"{usuario_id}@teste.local",
            "nome": "Usuario de Teste F14 LGPD",
        },
    )
    await sessao.flush()
    return usuario_id
