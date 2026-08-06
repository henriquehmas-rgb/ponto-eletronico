"""Fila de revisao do gestor (`app.antifraude.fila`), contra Postgres real.

Chamada direta ao servico (nao HTTP): nao existe rota ainda para isto -- ver
RFC (`docs/rfc/`) e docstring de `app.antifraude.fila`. Mesmo padrao ja usado
pela suite inteira de F5 (`tests/f5/pipeline/test_ingestao.py` chama
`registrar_marcacao` direto).
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.antifraude import fila
from app.core.erros import ErroDeAplicacao
from app.core.seguranca import Sujeito
from app.marcacao.pipeline import ingestao
from app.schemas import contrato
from tests.f14.antifraude.conftest import (
    GEOCERCA_LATITUDE,
    GEOCERCA_LONGITUDE,
    ContextoF14A1,
    gerar_idempotency_key,
)


def _sujeito(contexto: ContextoF14A1) -> Sujeito:
    return Sujeito(
        usuario_id=uuid.uuid4(),
        tenant_id=contexto.tenant_id,
        autenticado=True,
        permissoes=frozenset({"marcacoes.criar"}),
    )


async def _registrar_marcacao_suspeita(
    sessao: AsyncSession, contexto: ContextoF14A1
) -> contrato.MarcacaoCriada:
    """Registra uma marcacao com dispositivo de reputacao pessima -- cai na
    faixa de revisao (`revisao_status='pendente'`), sem sinal decisivo."""
    await sessao.execute(
        sql_text("UPDATE dispositivos SET status = 'bloqueado' WHERE id = :id"),
        {"id": str(contexto.dispositivo_id)},
    )
    # Sem vinculo de dispositivo ativo bloqueado -> mobile falharia em
    # `_verificar_dispositivo_pessoal` (PONTO-DISP-002); usa canal `web` (sem
    # checagem de vinculo de dispositivo) para chegar na composicao do score
    # mesmo com o dispositivo "sujo" -- mas dispositivoId ainda e informado
    # para a REPUTACAO ser calculada (o campo nao exige vinculo fora do
    # canal mobile).
    usuario_id = uuid.uuid4()
    await sessao.execute(
        sql_text(
            "INSERT INTO usuarios (id, tenant_id, email, nome_completo, status) "
            "VALUES (:id, :tenant_id, :email, 'Usuario de Teste F14/A1', 'ativo') "
            "ON CONFLICT DO NOTHING"
        ),
        {
            "id": usuario_id,
            "tenant_id": contexto.tenant_id,
            "email": f"{usuario_id}@teste.f14a1.local",
        },
    )
    await sessao.execute(
        sql_text(
            "INSERT INTO sessoes "
            "(id, tenant_id, usuario_id, canal, iniciada_em, ultima_atividade_em, expira_em, "
            " reautenticado_em) "
            "VALUES (:id, :tenant_id, :usuario_id, 'web', now(), now(), "
            " now() + interval '1 hour', now())"
        ),
        {"id": uuid.uuid4(), "tenant_id": contexto.tenant_id, "usuario_id": usuario_id},
    )
    await sessao.flush()

    corpo = contrato.MarcacaoCriar.model_validate(
        {
            "colaboradorId": str(contexto.colaborador_id),
            "empresaId": str(contexto.empresa_id),
            "unidadeId": str(contexto.unidade_id),
            "canal": "web",
            "dispositivoId": str(contexto.dispositivo_id),
            "latitude": GEOCERCA_LATITUDE,
            "longitude": GEOCERCA_LONGITUDE,
            "precisaoMetros": 5.0,
        }
    )
    sujeito = Sujeito(
        usuario_id=usuario_id,
        tenant_id=contexto.tenant_id,
        autenticado=True,
        permissoes=frozenset({"marcacoes.criar"}),
    )
    resultado = await ingestao.registrar_marcacao(
        sessao,
        tenant_id=contexto.tenant_id,
        corpo=corpo,
        idempotency_key=gerar_idempotency_key(),
        sujeito=sujeito,
        ip_origem="203.0.113.10",
    )
    return resultado.resposta


async def test_listar_pendentes_encontra_marcacao_sinalizada(
    sessao_f14a1: AsyncSession, contexto_f14a1: ContextoF14A1
) -> None:
    resposta = await _registrar_marcacao_suspeita(sessao_f14a1, contexto_f14a1)
    assert resposta.revisao_requerida is True

    pendentes = await fila.listar_pendentes(sessao_f14a1, tenant_id=contexto_f14a1.tenant_id)
    ids = {item.marcacao_id for item in pendentes}
    assert resposta.marcacao.id in ids
    item = next(i for i in pendentes if i.marcacao_id == resposta.marcacao.id)
    assert item.classificacao_confianca in ("media", "baixa")
    assert "_antifraude" in item.flags_integridade


async def test_decidir_revisao_aprovada_marca_status_e_autor(
    sessao_f14a1: AsyncSession, contexto_f14a1: ContextoF14A1
) -> None:
    resposta = await _registrar_marcacao_suspeita(sessao_f14a1, contexto_f14a1)
    revisor_id = uuid.uuid4()

    atualizado = await fila.decidir_revisao(
        sessao_f14a1,
        tenant_id=contexto_f14a1.tenant_id,
        marcacao_id=resposta.marcacao.id,
        decisao="aprovada",
        observacao="Verificado com o colaborador, falso positivo.",
        usuario_id=revisor_id,
    )
    assert atualizado.revisao_status == "aprovada"
    assert atualizado.revisado_por == revisor_id
    assert atualizado.revisado_em is not None

    pendentes = await fila.listar_pendentes(sessao_f14a1, tenant_id=contexto_f14a1.tenant_id)
    assert resposta.marcacao.id not in {i.marcacao_id for i in pendentes}


async def test_decidir_revisao_marcacao_nao_altera_marcacao_em_si(
    sessao_f14a1: AsyncSession, contexto_f14a1: ContextoF14A1
) -> None:
    """ADR-002: revisao produz TRATAMENTO (fora do escopo deste modulo),
    nunca altera a marcacao. Prova indireta: o NSR/hash da marcacao (nucleo
    legal) continuam identicos antes e depois da decisao."""
    resposta = await _registrar_marcacao_suspeita(sessao_f14a1, contexto_f14a1)
    nsr_antes = resposta.marcacao.nsr
    hash_antes = resposta.marcacao.hash_registro

    await fila.decidir_revisao(
        sessao_f14a1,
        tenant_id=contexto_f14a1.tenant_id,
        marcacao_id=resposta.marcacao.id,
        decisao="rejeitada",
        observacao="Fraude confirmada, abrir tratamento.",
        usuario_id=uuid.uuid4(),
    )

    from sqlalchemy import text

    linha = (
        await sessao_f14a1.execute(
            text("SELECT nsr, hash_registro FROM marcacoes WHERE id = :id"),
            {"id": str(resposta.marcacao.id)},
        )
    ).one()
    assert linha.nsr == nsr_antes
    assert linha.hash_registro == hash_antes


async def test_decidir_revisao_ja_decidida_nao_pode_ser_decidida_de_novo(
    sessao_f14a1: AsyncSession, contexto_f14a1: ContextoF14A1
) -> None:
    resposta = await _registrar_marcacao_suspeita(sessao_f14a1, contexto_f14a1)
    await fila.decidir_revisao(
        sessao_f14a1,
        tenant_id=contexto_f14a1.tenant_id,
        marcacao_id=resposta.marcacao.id,
        decisao="aprovada",
        observacao=None,
        usuario_id=uuid.uuid4(),
    )
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await fila.decidir_revisao(
            sessao_f14a1,
            tenant_id=contexto_f14a1.tenant_id,
            marcacao_id=resposta.marcacao.id,
            decisao="rejeitada",
            observacao=None,
            usuario_id=uuid.uuid4(),
        )
    assert excinfo.value.codigo == "PONTO-CONF-003"


async def test_decidir_revisao_decisao_invalida(
    sessao_f14a1: AsyncSession, contexto_f14a1: ContextoF14A1
) -> None:
    resposta = await _registrar_marcacao_suspeita(sessao_f14a1, contexto_f14a1)
    with pytest.raises(ErroDeAplicacao) as excinfo:
        await fila.decidir_revisao(
            sessao_f14a1,
            tenant_id=contexto_f14a1.tenant_id,
            marcacao_id=resposta.marcacao.id,
            decisao="ignorada",
            observacao=None,
            usuario_id=uuid.uuid4(),
        )
    assert excinfo.value.codigo == "PONTO-VAL-001"
