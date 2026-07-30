"""Testes puros (sem banco) de `app.notificacao.preferencias.
dentro_da_janela`/`proxima_janela` (T10)."""

from __future__ import annotations

import datetime as dt

from app.notificacao import preferencias


def test_sem_janela_configurada_sempre_dentro() -> None:
    assert preferencias.dentro_da_janela(dt.time(3, 0), None, None) is True
    assert preferencias.dentro_da_janela(dt.time(23, 59), None, None) is True


def test_janela_normal_dentro_e_fora() -> None:
    inicio, fim = dt.time(8, 0), dt.time(18, 0)
    assert preferencias.dentro_da_janela(dt.time(9, 0), inicio, fim) is True
    assert preferencias.dentro_da_janela(dt.time(8, 0), inicio, fim) is True
    assert preferencias.dentro_da_janela(dt.time(18, 0), inicio, fim) is True
    assert preferencias.dentro_da_janela(dt.time(7, 59), inicio, fim) is False
    assert preferencias.dentro_da_janela(dt.time(18, 1), inicio, fim) is False


def test_janela_atravessando_meia_noite() -> None:
    # Janela de silencio (aceita notificar) das 22h as 6h -- atravessa a
    # virada do dia.
    inicio, fim = dt.time(22, 0), dt.time(6, 0)
    assert preferencias.dentro_da_janela(dt.time(23, 0), inicio, fim) is True
    assert preferencias.dentro_da_janela(dt.time(2, 0), inicio, fim) is True
    assert preferencias.dentro_da_janela(dt.time(22, 0), inicio, fim) is True
    assert preferencias.dentro_da_janela(dt.time(6, 0), inicio, fim) is True
    assert preferencias.dentro_da_janela(dt.time(12, 0), inicio, fim) is False
    assert preferencias.dentro_da_janela(dt.time(21, 59), inicio, fim) is False


def test_proxima_janela_ainda_nao_passou_hoje() -> None:
    agora = dt.datetime(2026, 7, 28, 8, 0, tzinfo=dt.UTC)
    proximo = preferencias.proxima_janela(agora, dt.time(9, 0))
    assert proximo == dt.datetime(2026, 7, 28, 9, 0, tzinfo=dt.UTC)


def test_proxima_janela_ja_passou_vai_para_amanha() -> None:
    agora = dt.datetime(2026, 7, 28, 10, 0, tzinfo=dt.UTC)
    proximo = preferencias.proxima_janela(agora, dt.time(9, 0))
    assert proximo == dt.datetime(2026, 7, 29, 9, 0, tzinfo=dt.UTC)


def test_proxima_janela_exatamente_agora_vai_para_amanha() -> None:
    # `candidato <= agora` empurra para o dia seguinte -- o instante exato
    # do limite não deveria reagendar para "agora mesmo" de novo.
    agora = dt.datetime(2026, 7, 28, 9, 0, tzinfo=dt.UTC)
    proximo = preferencias.proxima_janela(agora, dt.time(9, 0))
    assert proximo == dt.datetime(2026, 7, 29, 9, 0, tzinfo=dt.UTC)
