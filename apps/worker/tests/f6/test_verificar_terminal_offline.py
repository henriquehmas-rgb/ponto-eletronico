"""T9: deteccao de terminal offline (F6/A1)."""

from __future__ import annotations

from uuid import UUID

import pytest

from tests.f6.conftest import TenantSemeado, criar_terminal_worker
from worker import terminais_saude
from worker.scheduler import verificar_terminal_offline

pytestmark = pytest.mark.asyncio


async def test_terminal_sem_contato_gera_exatamente_um_alerta_mesmo_com_varias_varreduras(
    tenant_worker: TenantSemeado,
) -> None:
    """Pronto quando (T9): mesmo com varias varreduras consecutivas sem
    contato, exatamente UMA publicacao de `terminal.offline`."""
    terminal_id = await criar_terminal_worker(
        tenant_worker, ultimo_contato_em="now() - interval '2 hours'"
    )

    for _ in range(3):
        resultado = await verificar_terminal_offline({"job_id": "teste"})
        assert resultado["terminaisVerificados"] >= 1

    eventos = [
        e
        for e in terminais_saude.BARRAMENTO_INTERNO
        if e["dados"]["terminalId"] == str(terminal_id)
    ]
    assert len(eventos) == 1
    assert eventos[0]["tipo"] == "terminal.offline"


async def test_payload_do_evento_bate_campo_a_campo_com_o_contrato(
    tenant_worker: TenantSemeado,
) -> None:
    terminal_id = await criar_terminal_worker(
        tenant_worker, ultimo_contato_em="now() - interval '2 hours'"
    )
    await verificar_terminal_offline({"job_id": "teste"})

    eventos = [
        e
        for e in terminais_saude.BARRAMENTO_INTERNO
        if e["dados"]["terminalId"] == str(terminal_id)
    ]
    assert len(eventos) == 1
    envelope = eventos[0]
    for campo in ("id", "tipo", "versao", "ocorridoEm", "tenantId", "dados"):
        assert campo in envelope
    dados = envelope["dados"]
    for campo in ("terminalId", "empresaId", "numeroSerie", "ultimoContatoEm", "minutosSemContato"):
        assert campo in dados
    assert UUID(dados["terminalId"]) == terminal_id
    assert envelope["tenantId"] == str(tenant_worker.id)


async def test_terminal_dentro_do_intervalo_nao_gera_alerta(tenant_worker: TenantSemeado) -> None:
    terminal_id = await criar_terminal_worker(
        tenant_worker, ultimo_contato_em="now()", intervalo_push_segundos=30
    )
    await verificar_terminal_offline({"job_id": "teste"})

    eventos = [
        e
        for e in terminais_saude.BARRAMENTO_INTERNO
        if e["dados"]["terminalId"] == str(terminal_id)
    ]
    assert eventos == []


async def test_terminal_que_volta_a_contatar_permite_novo_alerta_na_proxima_queda(
    tenant_worker: TenantSemeado,
) -> None:
    """Uma vez por queda -- nao uma vez para sempre: se o terminal voltar
    (nova amostra `online=true`) e cair de novo, um novo alerta e devido."""
    terminal_id = await criar_terminal_worker(
        tenant_worker, ultimo_contato_em="now() - interval '2 hours'"
    )
    await verificar_terminal_offline({"job_id": "teste"})
    primeira_contagem = len(
        [
            e
            for e in terminais_saude.BARRAMENTO_INTERNO
            if e["dados"]["terminalId"] == str(terminal_id)
        ]
    )
    assert primeira_contagem == 1

    # O terminal "volta": grava uma amostra online manualmente (o catch-up
    # real faria isso via `terminal.online`; aqui simulamos so o efeito em
    # `terminal_saude` que a proxima varredura consulta).
    from worker.config import obter_configuracao

    config = obter_configuracao()
    await terminais_saude.gravar_amostra_saude(
        config, tenant_id=tenant_worker.id, terminal_id=terminal_id, online=True
    )

    await verificar_terminal_offline({"job_id": "teste"})
    segunda_contagem = len(
        [
            e
            for e in terminais_saude.BARRAMENTO_INTERNO
            if e["dados"]["terminalId"] == str(terminal_id)
        ]
    )
    # A varredura re-marca offline (o terminal continua sem contato de
    # verdade) e publica um SEGUNDO alerta, porque a ultima amostra conhecida
    # tinha voltado a `online=true`.
    assert segunda_contagem == 2
