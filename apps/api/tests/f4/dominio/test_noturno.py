"""Teste de mesa do periodo noturno, hora ficta e prorrogacao (T3)."""

from __future__ import annotations

import datetime as dt

from app.apuracao.dominio.noturno import aplicar_hora_ficta, minutos_no_periodo_noturno

_FUSO = dt.timezone(dt.timedelta(hours=-3))
_NOTURNO_INICIO = dt.time(22, 0)
_NOTURNO_FIM = dt.time(5, 0)


def _dt(dia: int, hora: int, minuto: int = 0) -> dt.datetime:
    return dt.datetime(2026, 7, dia, hora, minuto, tzinfo=_FUSO)


def test_jornada_100_por_cento_diurna_nao_tem_minuto_noturno() -> None:
    minutos = minutos_no_periodo_noturno(
        _dt(20, 8),
        _dt(20, 17),
        noturno_inicio=_NOTURNO_INICIO,
        noturno_fim=_NOTURNO_FIM,
        prorrogacao_noturna=True,
    )
    assert minutos == 0


def test_jornada_cruzando_o_periodo_noturno_sem_prorrogacao() -> None:
    # 20:00 -> 23:00: so a fatia 22:00-23:00 (60 min) e noturna.
    minutos = minutos_no_periodo_noturno(
        _dt(20, 20),
        _dt(20, 23),
        noturno_inicio=_NOTURNO_INICIO,
        noturno_fim=_NOTURNO_FIM,
        prorrogacao_noturna=True,
    )
    assert minutos == 60


def test_jornada_iniciada_no_noturno_e_prorrogada_alem_das_05h_sumula_60() -> None:
    # 22:00 do dia 20 -> 06:00 do dia 21: com prorrogacao, TODO o periodo
    # (480 minutos) e tratado como noturno, mesmo passando das 05:00.
    minutos_com_prorrogacao = minutos_no_periodo_noturno(
        _dt(20, 22),
        _dt(21, 6),
        noturno_inicio=_NOTURNO_INICIO,
        noturno_fim=_NOTURNO_FIM,
        prorrogacao_noturna=True,
    )
    assert minutos_com_prorrogacao == 8 * 60

    # Sem prorrogacao, so 22:00-05:00 (420 minutos) contam; 05:00-06:00 fica
    # de fora.
    minutos_sem_prorrogacao = minutos_no_periodo_noturno(
        _dt(20, 22),
        _dt(21, 6),
        noturno_inicio=_NOTURNO_INICIO,
        noturno_fim=_NOTURNO_FIM,
        prorrogacao_noturna=False,
    )
    assert minutos_sem_prorrogacao == 7 * 60


def test_jornada_iniciada_antes_do_noturno_nao_prorroga_o_inicio() -> None:
    # 20:00 -> 23:30: o periodo COMECOU fora do noturno (as 20:00), entao a
    # prorrogacao (que exige comeco DENTRO da janela) nao se aplica; so
    # 22:00-23:30 (90 min) e noturno de qualquer forma, com ou sem a flag.
    minutos = minutos_no_periodo_noturno(
        _dt(20, 20),
        _dt(20, 23, 30),
        noturno_inicio=_NOTURNO_INICIO,
        noturno_fim=_NOTURNO_FIM,
        prorrogacao_noturna=True,
    )
    assert minutos == 90


def test_hora_ficta_converte_52min30s_em_60_minutos_equivalentes() -> None:
    resultado = aplicar_hora_ficta(52, hora_ficta_noturna=True)
    # 52 minutos de relogio -> round(52 * 8/7) = round(59.43) = 59
    # equivalente; acrescimo de 7.
    assert resultado.noturno_minutos == 52
    assert resultado.noturno_ficta_minutos == 7


def test_hora_ficta_desabilitada_nao_gera_acrescimo() -> None:
    resultado = aplicar_hora_ficta(420, hora_ficta_noturna=False)
    assert resultado.noturno_minutos == 420
    assert resultado.noturno_ficta_minutos == 0


def test_hora_ficta_sem_minuto_noturno_e_neutra() -> None:
    resultado = aplicar_hora_ficta(0, hora_ficta_noturna=True)
    assert resultado.noturno_minutos == 0
    assert resultado.noturno_ficta_minutos == 0


def test_hora_ficta_de_uma_jornada_noturna_completa() -> None:
    # 7 horas de relogio (420 min) dentro do noturno equivalem a 480 min
    # (60/52.5 = 8/7; 420 * 8/7 = 480) -- exatamente 8 horas de jornada.
    resultado = aplicar_hora_ficta(420, hora_ficta_noturna=True)
    assert resultado.noturno_minutos == 420
    assert resultado.noturno_ficta_minutos == 60
