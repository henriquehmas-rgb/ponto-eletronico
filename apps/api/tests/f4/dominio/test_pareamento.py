"""Teste de mesa do pareamento de marcacoes (T2)."""

from __future__ import annotations

import datetime as dt
from uuid import uuid4

from app.apuracao.dominio.pareamento import (
    MarcacaoParaPareamento,
    detectar_ocorrencias_pareamento,
    parear_marcacoes,
)

_FUSO = dt.timezone(dt.timedelta(hours=-3))


def _marcacao(
    hora: int, minuto: int, nsr: int, sentido: str | None = None
) -> MarcacaoParaPareamento:
    return MarcacaoParaPareamento(
        id=uuid4(),
        datahora=dt.datetime(2026, 7, 20, hora, minuto, tzinfo=_FUSO),
        nsr=nsr,
        sentido_informado=sentido,  # type: ignore[arg-type]
    )


def test_numero_par_de_marcacoes_pareia_dois_periodos_fechados() -> None:
    marcacoes = [
        _marcacao(8, 0, 1),
        _marcacao(12, 0, 2),
        _marcacao(13, 0, 3),
        _marcacao(17, 0, 4),
    ]
    resultado = parear_marcacoes(marcacoes)

    assert resultado.total_marcacoes == 4
    assert resultado.marcacao_impar is False
    assert len(resultado.periodos) == 2
    assert resultado.periodos[0].saida is not None
    assert resultado.periodos[1].saida is not None
    assert resultado.periodos[0].entrada.marcacao.nsr == 1
    assert resultado.periodos[0].saida.marcacao.nsr == 2
    assert resultado.periodos[1].entrada.marcacao.nsr == 3
    assert resultado.periodos[1].saida.marcacao.nsr == 4


def test_numero_impar_de_marcacoes_deixa_ultimo_periodo_aberto() -> None:
    marcacoes = [_marcacao(8, 0, 1), _marcacao(12, 0, 2), _marcacao(13, 0, 3)]
    resultado = parear_marcacoes(marcacoes)

    assert resultado.total_marcacoes == 3
    assert resultado.marcacao_impar is True
    assert len(resultado.periodos) == 2
    assert resultado.periodos[0].saida is not None
    assert resultado.periodos[1].saida is None
    assert resultado.periodos[1].entrada.marcacao.nsr == 3

    codigos = detectar_ocorrencias_pareamento(resultado, tipo_dia="util")
    assert "marcacao_impar" in codigos


def test_sem_marcacao_em_dia_util_gera_ocorrencia() -> None:
    resultado = parear_marcacoes([])
    assert resultado.total_marcacoes == 0
    assert resultado.marcacao_impar is False

    codigos = detectar_ocorrencias_pareamento(resultado, tipo_dia="util")
    assert codigos == ("sem_marcacao",)


def test_sem_marcacao_em_dia_de_folga_nao_gera_ocorrencia() -> None:
    resultado = parear_marcacoes([])
    assert detectar_ocorrencias_pareamento(resultado, tipo_dia="folga") == ()
    assert detectar_ocorrencias_pareamento(resultado, tipo_dia="dsr") == ()


def test_sentido_informado_presente_e_coerente() -> None:
    marcacoes = [
        _marcacao(8, 0, 1, sentido="entrada"),
        _marcacao(17, 0, 2, sentido="saida"),
    ]
    resultado = parear_marcacoes(marcacoes)
    entrada = resultado.periodos[0].entrada
    saida = resultado.periodos[0].saida
    assert saida is not None
    assert entrada.sentido_coerente is True
    assert saida.sentido_coerente is True


def test_sentido_informado_incoerente_nao_altera_pareamento_por_ordem() -> None:
    # O coletor informou o sentido errado (por exemplo um totem mal
    # configurado) -- o pareamento definitivo continua sendo por ordem, so a
    # coerencia observada muda.
    marcacoes = [
        _marcacao(8, 0, 1, sentido="saida"),
        _marcacao(17, 0, 2, sentido="entrada"),
    ]
    resultado = parear_marcacoes(marcacoes)
    entrada = resultado.periodos[0].entrada
    saida = resultado.periodos[0].saida
    assert saida is not None
    assert entrada.sentido_atribuido == "entrada"
    assert entrada.sentido_coerente is False
    assert saida.sentido_atribuido == "saida"
    assert saida.sentido_coerente is False


def test_sentido_informado_ausente_pareia_so_por_ordem() -> None:
    marcacoes = [_marcacao(8, 0, 1), _marcacao(17, 0, 2)]
    resultado = parear_marcacoes(marcacoes)
    entrada = resultado.periodos[0].entrada
    saida = resultado.periodos[0].saida
    assert saida is not None
    assert entrada.sentido_coerente is None
    assert saida.sentido_coerente is None


def test_ordenacao_estavel_por_datahora_e_nsr() -> None:
    # Duas marcacoes no mesmo instante: o NSR desempata de forma
    # deterministica (ADR-004).
    mesmo_instante = dt.datetime(2026, 7, 20, 8, 0, tzinfo=_FUSO)
    marcacoes = [
        MarcacaoParaPareamento(id=uuid4(), datahora=mesmo_instante, nsr=5),
        MarcacaoParaPareamento(id=uuid4(), datahora=mesmo_instante, nsr=2),
    ]
    resultado = parear_marcacoes(marcacoes)
    assert resultado.periodos[0].entrada.marcacao.nsr == 2
    saida = resultado.periodos[0].saida
    assert saida is not None
    assert saida.marcacao.nsr == 5
