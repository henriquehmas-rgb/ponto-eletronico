"""T6: `access_log` -> `MarcacaoCriar`. Testes puros (sem rede, sem banco)."""

from __future__ import annotations

from uuid import uuid4

import pytest

from gateway.dominio.conversao import (
    TerminalParaConversao,
    converter_access_log,
    montar_idempotency_key,
)
from gateway.simulador import EVENTOS_ACCESS_LOG, gerar_access_log

TERMINAL = TerminalParaConversao(
    id=uuid4(),
    dispositivo_id=uuid4(),
    empresa_id=uuid4(),
    unidade_id=uuid4(),
    numero_serie="IDF-2026-000417",
)


@pytest.mark.parametrize("codigo_evento", sorted(EVENTOS_ACCESS_LOG))
def test_converter_access_log_cobre_todos_os_eventos_documentados(codigo_evento: int) -> None:
    """Um `access_log` de CADA `event` documentado converte para um
    `MarcacaoCriar` valido, campo a campo."""
    access_log = gerar_access_log(41208, user_id=314, evento=codigo_evento, portal_id=1)

    corpo = converter_access_log(
        access_log, terminal=TERMINAL, matricula="MAT-0314", coletada_offline=True
    )

    assert corpo["canal"] == "terminal"
    assert corpo["matricula"] == "MAT-0314"
    assert corpo["empresaId"] == str(TERMINAL.empresa_id)
    assert corpo["unidadeId"] == str(TERMINAL.unidade_id)
    assert corpo["terminalId"] == str(TERMINAL.id)
    assert corpo["dispositivoId"] == str(TERMINAL.dispositivo_id)
    assert corpo["logExternoId"] == 41208
    assert corpo["coletadaOffline"] is True
    assert corpo["sentidoInformado"] == "indefinido"
    # `datahoraDispositivo` bate com o epoch do access_log (evidencia, nao
    # fonte de verdade -- secao 2 do PCF).
    assert corpo["datahoraDispositivo"].startswith(
        __import__("datetime")
        .datetime.fromtimestamp(access_log["time"], tz=__import__("datetime").UTC)
        .isoformat()[:19]
    )


def test_terminal_sem_unidade_nao_manda_unidade_id() -> None:
    terminal_sem_unidade = TerminalParaConversao(
        id=uuid4(), dispositivo_id=uuid4(), empresa_id=uuid4(), unidade_id=None, numero_serie="X"
    )
    access_log = gerar_access_log(1, user_id=1)
    corpo = converter_access_log(access_log, terminal=terminal_sem_unidade, matricula="M1")
    assert "unidadeId" not in corpo


def test_coletada_offline_padrao_false() -> None:
    access_log = gerar_access_log(2, user_id=1)
    corpo = converter_access_log(access_log, terminal=TERMINAL, matricula="M1")
    assert corpo["coletadaOffline"] is False


def test_idempotency_key_e_deterministica() -> None:
    chave1 = montar_idempotency_key("IDF-2026-000417", 41208)
    chave2 = montar_idempotency_key("IDF-2026-000417", 41208)
    assert chave1 == chave2

    outro_terminal = montar_idempotency_key("IDF-OUTRO", 41208)
    outro_log = montar_idempotency_key("IDF-2026-000417", 99)
    assert chave1 != outro_terminal
    assert chave1 != outro_log


def test_mesmo_access_log_convertido_duas_vezes_produz_a_mesma_chave() -> None:
    """Pronto quando (T6): o mesmo `access_log` convertido duas vezes produz
    a mesma `Idempotency-Key` -- reapresentacao nao pode gerar duas chaves
    diferentes para o mesmo fato."""
    access_log = gerar_access_log(555, user_id=9)
    corpo1 = converter_access_log(access_log, terminal=TERMINAL, matricula="M9")
    corpo2 = converter_access_log(dict(access_log), terminal=TERMINAL, matricula="M9")
    chave1 = montar_idempotency_key(TERMINAL.numero_serie, corpo1["logExternoId"])
    chave2 = montar_idempotency_key(TERMINAL.numero_serie, corpo2["logExternoId"])
    assert chave1 == chave2
    assert corpo1 == corpo2
