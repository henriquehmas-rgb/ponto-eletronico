"""Testes de `app.workflow.aprovacoes.delegacoes` (T3, A1)."""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.erros import ErroDeAplicacao
from app.schemas import contrato as esquemas
from app.workflow.aprovacoes import delegacoes
from tests.f10.conftest import ContextoF10


def _corpo(
    contexto: ContextoF10, *, inicio: dt.datetime, fim: dt.datetime
) -> esquemas.DelegacaoCriar:
    return esquemas.DelegacaoCriar.model_validate(
        {
            "deleganteUsuarioId": str(contexto.gestor_usuario_id),
            "delegadoUsuarioId": str(contexto.rh_usuario_id),
            "motivo": "Ferias do gestor.",
            "inicioEm": inicio.isoformat(),
            "fimEm": fim.isoformat(),
        }
    )


async def test_criar_delegacao_recusa_fim_antes_do_inicio(
    sessao_f10: AsyncSession, contexto_f10: ContextoF10
) -> None:
    agora = dt.datetime.now(tz=dt.UTC)
    dados = _corpo(contexto_f10, inicio=agora + dt.timedelta(days=5), fim=agora)
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await delegacoes.criar_delegacao(
            sessao_f10, contexto_f10.tenant_id, dados, usuario_id=contexto_f10.gestor_usuario_id
        )
    assert excinfo.value.codigo == "PONTO-VAL-001"


async def test_criar_delegacao_recusa_delegante_igual_delegado(
    sessao_f10: AsyncSession, contexto_f10: ContextoF10
) -> None:
    agora = dt.datetime.now(tz=dt.UTC)
    dados = esquemas.DelegacaoCriar.model_validate(
        {
            "deleganteUsuarioId": str(contexto_f10.gestor_usuario_id),
            "delegadoUsuarioId": str(contexto_f10.gestor_usuario_id),
            "motivo": "Invalido.",
            "inicioEm": agora.isoformat(),
            "fimEm": (agora + dt.timedelta(days=1)).isoformat(),
        }
    )
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await delegacoes.criar_delegacao(
            sessao_f10, contexto_f10.tenant_id, dados, usuario_id=contexto_f10.gestor_usuario_id
        )
    assert excinfo.value.codigo == "PONTO-VAL-001"


async def test_criar_delegacao_recusa_sobreposicao(
    sessao_f10: AsyncSession, contexto_f10: ContextoF10
) -> None:
    agora = dt.datetime.now(tz=dt.UTC)
    primeira = _corpo(contexto_f10, inicio=agora, fim=agora + dt.timedelta(days=10))
    await delegacoes.criar_delegacao(
        sessao_f10, contexto_f10.tenant_id, primeira, usuario_id=contexto_f10.gestor_usuario_id
    )

    sobreposta = _corpo(
        contexto_f10,
        inicio=agora + dt.timedelta(days=5),
        fim=agora + dt.timedelta(days=15),
    )
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await delegacoes.criar_delegacao(
            sessao_f10,
            contexto_f10.tenant_id,
            sobreposta,
            usuario_id=contexto_f10.gestor_usuario_id,
        )
    assert excinfo.value.codigo == "PONTO-VAL-010"


async def test_listar_delegacoes_filtra_por_vigencia(
    sessao_f10: AsyncSession, contexto_f10: ContextoF10
) -> None:
    agora = dt.datetime.now(tz=dt.UTC)
    dados = _corpo(contexto_f10, inicio=agora, fim=agora + dt.timedelta(days=3))
    criada = await delegacoes.criar_delegacao(
        sessao_f10, contexto_f10.tenant_id, dados, usuario_id=contexto_f10.gestor_usuario_id
    )

    dentro_da_vigencia, _ = await delegacoes.listar_delegacoes(
        sessao_f10,
        contexto_f10.tenant_id,
        vigente_em=agora + dt.timedelta(days=1),
    )
    assert criada.id in {linha.id for linha in dentro_da_vigencia}

    fora_da_vigencia, _ = await delegacoes.listar_delegacoes(
        sessao_f10,
        contexto_f10.tenant_id,
        vigente_em=agora + dt.timedelta(days=30),
    )
    assert criada.id not in {linha.id for linha in fora_da_vigencia}
