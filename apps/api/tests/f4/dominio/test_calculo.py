"""Teste de mesa de `calcular_dia` (T3 e T4): normais/extras por faixa e
fator, adicional noturno com hora ficta e prorrogacao, intrajornada,
interjornada, DSR e falta/atraso/saida antecipada."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from uuid import uuid4

from app.apuracao.dominio.calculo import ConfiguracaoCalculo, FaixaExtra, calcular_dia
from app.apuracao.dominio.pareamento import MarcacaoParaPareamento, parear_marcacoes

_FUSO = dt.timezone(dt.timedelta(hours=-3))
_NOTURNO_INICIO = dt.time(22, 0)
_NOTURNO_FIM = dt.time(5, 0)


def _dt(dia: int, hora: int, minuto: int = 0) -> dt.datetime:
    return dt.datetime(2026, 7, dia, hora, minuto, tzinfo=_FUSO)


def _marcacao(quando: dt.datetime, nsr: int) -> MarcacaoParaPareamento:
    return MarcacaoParaPareamento(id=uuid4(), datahora=quando, nsr=nsr)


def _config(**overrides: object) -> ConfiguracaoCalculo:
    base: dict[str, object] = {
        "tolerancia_marcacao_minutos": 5,
        "tolerancia_diaria_minutos": 10,
        "descontar_tudo_se_exceder": False,
        "intervalo_minimo_minutos": None,
        "interjornada_minima_minutos": 660,
        "noturno_inicio": _NOTURNO_INICIO,
        "noturno_fim": _NOTURNO_FIM,
        "hora_ficta_noturna": True,
        "prorrogacao_noturna": True,
        "limite_extra_diario_minutos": 120,
        "limite_jornada_diaria_minutos": 600,
    }
    base.update(overrides)
    return ConfiguracaoCalculo(**base)  # type: ignore[arg-type]


def test_jornada_100_por_cento_diurna() -> None:
    marcacoes = [
        _marcacao(_dt(20, 8), 1),
        _marcacao(_dt(20, 12), 2),
        _marcacao(_dt(20, 13), 3),
        _marcacao(_dt(20, 17), 4),
    ]
    resultado = calcular_dia(
        tipo_dia="util",
        entrada_prevista=_dt(20, 8),
        saida_prevista=_dt(20, 17),
        intervalos_previstos=[(_dt(20, 12), _dt(20, 13))],
        previsto_minutos=480,
        resultado_pareamento=parear_marcacoes(marcacoes),
        ultima_marcacao_dia_anterior=None,
        config=_config(),
    )
    assert resultado.trabalhado_minutos == 480
    assert resultado.normais_minutos == 480
    assert resultado.extras_minutos == 0
    assert resultado.noturno_minutos == 0
    assert resultado.noturno_ficta_minutos == 0
    assert resultado.atraso_minutos == 0
    assert resultado.saida_antecipada_minutos == 0
    assert resultado.falta_minutos == 0
    assert not resultado.ocorrencias


def test_jornada_cruzando_periodo_noturno_sem_prorrogacao_relevante() -> None:
    # 18:00 -> 02:00 (8h). O periodo entra na janela noturna as 22:00 e
    # termina as 02:00, ANTES do fim da janela (05:00): a prorrogacao nunca
    # chega a ser acionada, com ou sem a flag o resultado e o mesmo.
    marcacoes = [_marcacao(_dt(20, 18), 1), _marcacao(_dt(21, 2), 2)]
    resolucao_comum = {
        "tipo_dia": "util",
        "entrada_prevista": _dt(20, 18),
        "saida_prevista": _dt(21, 2),
        "intervalos_previstos": [],
        "previsto_minutos": 480,
        "resultado_pareamento": parear_marcacoes(marcacoes),
        "ultima_marcacao_dia_anterior": None,
    }
    com_prorrogacao = calcular_dia(**resolucao_comum, config=_config(prorrogacao_noturna=True))  # type: ignore[arg-type]
    sem_prorrogacao = calcular_dia(**resolucao_comum, config=_config(prorrogacao_noturna=False))  # type: ignore[arg-type]

    assert com_prorrogacao.noturno_minutos == 240
    assert sem_prorrogacao.noturno_minutos == 240


def test_jornada_iniciada_no_noturno_prorrogada_alem_das_05h() -> None:
    # 22:00 -> 06:00 (8h). Comeca DENTRO da janela noturna e continua alem
    # das 05:00 -- Sumula 60, II TST.
    marcacoes = [_marcacao(_dt(20, 22), 1), _marcacao(_dt(21, 6), 2)]
    resolucao_comum = {
        "tipo_dia": "util",
        "entrada_prevista": _dt(20, 22),
        "saida_prevista": _dt(21, 6),
        "intervalos_previstos": [],
        "previsto_minutos": 480,
        "resultado_pareamento": parear_marcacoes(marcacoes),
        "ultima_marcacao_dia_anterior": None,
    }
    com_prorrogacao = calcular_dia(**resolucao_comum, config=_config(prorrogacao_noturna=True))  # type: ignore[arg-type]
    sem_prorrogacao = calcular_dia(**resolucao_comum, config=_config(prorrogacao_noturna=False))  # type: ignore[arg-type]

    assert com_prorrogacao.noturno_minutos == 480
    assert com_prorrogacao.noturno_ficta_minutos == (480 * 16 + 7) // 14 - 480
    assert sem_prorrogacao.noturno_minutos == 420


def test_extra_acima_do_limite_diario_gera_ocorrencias() -> None:
    # 08:00 -> 21:00 com 1h de almoco: 12h trabalhadas (720 min), previsto
    # 480 -> 240 min de extra, acima do limite diario de extra (120) e a
    # jornada total (720) acima do limite diario de jornada (600).
    marcacoes = [
        _marcacao(_dt(20, 8), 1),
        _marcacao(_dt(20, 12), 2),
        _marcacao(_dt(20, 13), 3),
        _marcacao(_dt(20, 21), 4),
    ]
    resultado = calcular_dia(
        tipo_dia="util",
        entrada_prevista=_dt(20, 8),
        saida_prevista=_dt(20, 17),
        intervalos_previstos=[(_dt(20, 12), _dt(20, 13))],
        previsto_minutos=480,
        resultado_pareamento=parear_marcacoes(marcacoes),
        ultima_marcacao_dia_anterior=None,
        config=_config(),
    )
    assert resultado.trabalhado_minutos == 720
    assert resultado.normais_minutos == 480
    assert resultado.extras_minutos == 240
    assert resultado.atraso_minutos == 0
    assert resultado.saida_antecipada_minutos == 0
    codigos = {o.codigo for o in resultado.ocorrencias}
    assert "extra_excedida" in codigos
    assert "jornada_excedida" in codigos
    # Fator padrao (sem `fatores_extra` configurado) e 1.5.
    componentes_extra = [c for c in resultado.componentes if c.categoria == "extra"]
    assert sum(c.minutos for c in componentes_extra) == 240
    assert sum(c.minutos_equivalentes for c in componentes_extra) == 360


def test_soma_dos_componentes_bate_com_os_totais_agregados() -> None:
    marcacoes = [
        _marcacao(_dt(20, 8), 1),
        _marcacao(_dt(20, 12), 2),
        _marcacao(_dt(20, 13), 3),
        _marcacao(_dt(20, 19), 4),
    ]
    resultado = calcular_dia(
        tipo_dia="util",
        entrada_prevista=_dt(20, 8),
        saida_prevista=_dt(20, 17),
        intervalos_previstos=[(_dt(20, 12), _dt(20, 13))],
        previsto_minutos=480,
        resultado_pareamento=parear_marcacoes(marcacoes),
        ultima_marcacao_dia_anterior=None,
        config=_config(),
    )
    minutos_normais_e_extras = sum(
        c.minutos for c in resultado.componentes if c.categoria in ("normal", "extra")
    )
    assert minutos_normais_e_extras == resultado.trabalhado_minutos
    assert resultado.normais_minutos + resultado.extras_minutos == resultado.trabalhado_minutos


def test_faixas_extra_configuradas_distribuem_cumulativamente() -> None:
    faixas = (
        FaixaExtra(fator=Decimal("1.5"), ate_minutos=60),
        FaixaExtra(fator=Decimal("2.0")),
    )
    marcacoes = [
        _marcacao(_dt(20, 8), 1),
        _marcacao(_dt(20, 12), 2),
        _marcacao(_dt(20, 13), 3),
        _marcacao(_dt(20, 19), 4),
    ]
    resultado = calcular_dia(
        tipo_dia="util",
        entrada_prevista=_dt(20, 8),
        saida_prevista=_dt(20, 17),
        intervalos_previstos=[(_dt(20, 12), _dt(20, 13))],
        previsto_minutos=480,
        resultado_pareamento=parear_marcacoes(marcacoes),
        ultima_marcacao_dia_anterior=None,
        config=_config(faixas_extra=faixas),
    )
    # 120 min de extra: 60 na primeira faixa (1.5x = 90) + 60 na segunda (2x = 120).
    assert resultado.extras_minutos == 120
    componentes_extra = [c for c in resultado.componentes if c.categoria == "extra"]
    assert [c.minutos for c in componentes_extra] == [60, 60]
    assert [c.minutos_equivalentes for c in componentes_extra] == [90, 120]


def test_intrajornada_suprimida_gera_indenizacao_e_ocorrencia() -> None:
    # Intervalo minimo de 60 min, mas so 15 foram usufruidos -> suprimida 45.
    marcacoes = [
        _marcacao(_dt(20, 8), 1),
        _marcacao(_dt(20, 12), 2),
        _marcacao(_dt(20, 12, 15), 3),
        _marcacao(_dt(20, 16, 15), 4),
    ]
    resultado = calcular_dia(
        tipo_dia="util",
        entrada_prevista=_dt(20, 8),
        saida_prevista=_dt(20, 17),
        intervalos_previstos=[(_dt(20, 12), _dt(20, 13))],
        previsto_minutos=480,
        resultado_pareamento=parear_marcacoes(marcacoes),
        ultima_marcacao_dia_anterior=None,
        config=_config(intervalo_minimo_minutos=60),
    )
    assert resultado.intervalo_minutos == 15
    assert resultado.intrajornada_suprimida_minutos == 45
    codigos = {o.codigo for o in resultado.ocorrencias}
    assert "intrajornada_suprimida" in codigos
    indenizacoes = [c for c in resultado.componentes if c.categoria == "indenizacao"]
    assert len(indenizacoes) == 1
    assert indenizacoes[0].minutos == 45
    assert indenizacoes[0].minutos_equivalentes == 23  # round(45 * 0.5) = 22.5 -> 23 (half up)


def test_interjornada_violada_olhando_o_dia_anterior() -> None:
    # Saida do dia anterior as 23:00; entrada de hoje as 07:00 -- so 8h de
    # descanso, abaixo do minimo de 11h (660 min).
    ultima_marcacao_ontem = _dt(19, 23)
    marcacoes = [_marcacao(_dt(20, 7), 1), _marcacao(_dt(20, 16), 2)]
    resultado = calcular_dia(
        tipo_dia="util",
        entrada_prevista=_dt(20, 7),
        saida_prevista=_dt(20, 16),
        intervalos_previstos=[],
        previsto_minutos=540,
        resultado_pareamento=parear_marcacoes(marcacoes),
        ultima_marcacao_dia_anterior=ultima_marcacao_ontem,
        config=_config(interjornada_minima_minutos=660),
    )
    assert resultado.interjornada_minutos == 8 * 60
    assert resultado.interjornada_violada is True
    codigos = {o.codigo for o in resultado.ocorrencias}
    assert "interjornada_violada" in codigos


def test_interjornada_respeitada_nao_gera_ocorrencia() -> None:
    ultima_marcacao_ontem = _dt(19, 17)
    marcacoes = [_marcacao(_dt(20, 8), 1), _marcacao(_dt(20, 17), 2)]
    resultado = calcular_dia(
        tipo_dia="util",
        entrada_prevista=_dt(20, 8),
        saida_prevista=_dt(20, 17),
        intervalos_previstos=[],
        previsto_minutos=540,
        resultado_pareamento=parear_marcacoes(marcacoes),
        ultima_marcacao_dia_anterior=ultima_marcacao_ontem,
        config=_config(interjornada_minima_minutos=660),
    )
    assert resultado.interjornada_minutos == 15 * 60
    assert resultado.interjornada_violada is False
    assert "interjornada_violada" not in {o.codigo for o in resultado.ocorrencias}


def test_vinculo_sem_marcacao_em_dia_util_gera_falta_e_ocorrencias() -> None:
    resultado = calcular_dia(
        tipo_dia="util",
        entrada_prevista=_dt(20, 8),
        saida_prevista=_dt(20, 17),
        intervalos_previstos=[(_dt(20, 12), _dt(20, 13))],
        previsto_minutos=480,
        resultado_pareamento=parear_marcacoes([]),
        ultima_marcacao_dia_anterior=None,
        config=_config(),
    )
    assert resultado.trabalhado_minutos == 0
    assert resultado.falta_minutos == 480
    codigos = {o.codigo for o in resultado.ocorrencias}
    assert "sem_marcacao" in codigos
    assert "falta" in codigos


def test_falta_abonada_nao_gera_ocorrencia_de_falta() -> None:
    resultado = calcular_dia(
        tipo_dia="util",
        entrada_prevista=_dt(20, 8),
        saida_prevista=_dt(20, 17),
        intervalos_previstos=[(_dt(20, 12), _dt(20, 13))],
        previsto_minutos=480,
        resultado_pareamento=parear_marcacoes([]),
        ultima_marcacao_dia_anterior=None,
        config=_config(),
        abono_minutos=480,
    )
    assert resultado.falta_minutos == 0
    assert "falta" not in {o.codigo for o in resultado.ocorrencias}


def test_dsr_trabalhado_credita_com_fator_de_dobra() -> None:
    marcacoes = [_marcacao(_dt(20, 8), 1), _marcacao(_dt(20, 12), 2)]
    resultado = calcular_dia(
        tipo_dia="dsr",
        entrada_prevista=None,
        saida_prevista=None,
        intervalos_previstos=[],
        previsto_minutos=0,
        resultado_pareamento=parear_marcacoes(marcacoes),
        ultima_marcacao_dia_anterior=None,
        config=_config(),
    )
    assert resultado.trabalhado_minutos == 240
    assert resultado.dsr_credito_minutos == 240
    assert "dsr_violado" in {o.codigo for o in resultado.ocorrencias}
    dsr_componentes = [c for c in resultado.componentes if c.categoria == "dsr"]
    assert len(dsr_componentes) == 1
    assert dsr_componentes[0].minutos_equivalentes == 480  # fator 2.0


def test_atraso_dentro_da_tolerancia_nao_gera_ocorrencia() -> None:
    marcacoes = [
        _marcacao(_dt(20, 8, 3), 1),  # 3 min de atraso, tolerado
        _marcacao(_dt(20, 17), 2),
    ]
    resultado = calcular_dia(
        tipo_dia="util",
        entrada_prevista=_dt(20, 8),
        saida_prevista=_dt(20, 17),
        intervalos_previstos=[],
        previsto_minutos=540,
        resultado_pareamento=parear_marcacoes(marcacoes),
        ultima_marcacao_dia_anterior=None,
        config=_config(),
    )
    assert resultado.atraso_minutos == 0
    assert resultado.tolerancia_aplicada_minutos == 3
    assert "atraso" not in {o.codigo for o in resultado.ocorrencias}


def test_atraso_acima_da_tolerancia_por_marcacao_gera_ocorrencia() -> None:
    marcacoes = [
        _marcacao(_dt(20, 8, 8), 1),  # 8 min, acima da tolerancia por marcacao (5)
        _marcacao(_dt(20, 17), 2),
    ]
    resultado = calcular_dia(
        tipo_dia="util",
        entrada_prevista=_dt(20, 8),
        saida_prevista=_dt(20, 17),
        intervalos_previstos=[],
        previsto_minutos=540,
        resultado_pareamento=parear_marcacoes(marcacoes),
        ultima_marcacao_dia_anterior=None,
        config=_config(),
    )
    assert resultado.atraso_minutos == 8
    assert "atraso" in {o.codigo for o in resultado.ocorrencias}


def test_saida_antecipada_gera_ocorrencia() -> None:
    marcacoes = [
        _marcacao(_dt(20, 8), 1),
        _marcacao(_dt(20, 16, 30), 2),  # saiu 30 min antes do previsto
    ]
    resultado = calcular_dia(
        tipo_dia="util",
        entrada_prevista=_dt(20, 8),
        saida_prevista=_dt(20, 17),
        intervalos_previstos=[],
        previsto_minutos=540,
        resultado_pareamento=parear_marcacoes(marcacoes),
        ultima_marcacao_dia_anterior=None,
        config=_config(),
    )
    assert resultado.saida_antecipada_minutos == 30
    assert "saida_antecipada" in {o.codigo for o in resultado.ocorrencias}
