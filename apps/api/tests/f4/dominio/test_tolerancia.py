"""Teste de mesa da tolerancia de marcacao e da tolerancia diaria (T2, art.
58 par. 1 CLT)."""

from __future__ import annotations

import pytest

from app.apuracao.dominio.tolerancia import aplicar_tolerancia


def test_desvio_dentro_da_tolerancia_nao_gera_atraso_computado() -> None:
    resultado = aplicar_tolerancia(
        (3,),
        tolerancia_marcacao_minutos=5,
        tolerancia_diaria_minutos=10,
        descontar_tudo_se_exceder=False,
    )
    assert resultado.desvios_computados_minutos == (0,)
    assert resultado.tolerancia_aplicada_minutos == 3


def test_soma_diaria_acima_do_teto_descontar_tudo_false_computa_so_excedente() -> None:
    # Tres desvios, cada um dentro da tolerancia por marcacao (5), somando 12
    # -- acima do teto diario de 10.
    resultado = aplicar_tolerancia(
        (5, 5, 2),
        tolerancia_marcacao_minutos=5,
        tolerancia_diaria_minutos=10,
        descontar_tudo_se_exceder=False,
    )
    assert sum(resultado.desvios_computados_minutos) == 2  # 12 - 10
    assert resultado.tolerancia_aplicada_minutos == 10
    # O excedente e atribuido em ordem: o primeiro desvio absorve primeiro.
    assert resultado.desvios_computados_minutos == (2, 0, 0)


def test_soma_diaria_acima_do_teto_descontar_tudo_true_computa_tudo() -> None:
    resultado = aplicar_tolerancia(
        (5, 5, 2),
        tolerancia_marcacao_minutos=5,
        tolerancia_diaria_minutos=10,
        descontar_tudo_se_exceder=True,
    )
    assert resultado.desvios_computados_minutos == (5, 5, 2)
    assert resultado.tolerancia_aplicada_minutos == 0


def test_desvio_maior_que_tolerancia_por_marcacao_e_sempre_computado() -> None:
    # 8 minutos excede sozinho a tolerancia por marcacao (5): nunca entra no
    # "cofre" da tolerancia diaria, mesmo que o teto diario (10) nao tenha
    # sido usado por nenhum outro desvio.
    resultado = aplicar_tolerancia(
        (8,),
        tolerancia_marcacao_minutos=5,
        tolerancia_diaria_minutos=10,
        descontar_tudo_se_exceder=False,
    )
    assert resultado.desvios_computados_minutos == (8,)
    assert resultado.tolerancia_aplicada_minutos == 0


def test_sem_desvio_nenhum_nao_aplica_tolerancia() -> None:
    resultado = aplicar_tolerancia(
        (),
        tolerancia_marcacao_minutos=5,
        tolerancia_diaria_minutos=10,
        descontar_tudo_se_exceder=False,
    )
    assert resultado.desvios_computados_minutos == ()
    assert resultado.tolerancia_aplicada_minutos == 0


def test_desvio_negativo_e_recusado() -> None:
    with pytest.raises(ValueError, match="negativo"):
        aplicar_tolerancia(
            (-1,),
            tolerancia_marcacao_minutos=5,
            tolerancia_diaria_minutos=10,
            descontar_tudo_se_exceder=False,
        )
