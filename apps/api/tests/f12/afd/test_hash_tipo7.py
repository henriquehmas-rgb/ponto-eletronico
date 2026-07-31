"""T3 -- hash SHA-256 encadeado do registro tipo "7" (ADR-012).

**Esta fórmula é melhor esforço (ADR-012) e NÃO é verificada contra um AFD
de referência externo** -- a norma não especifica o formato exato de
concatenação (`docs/leiaute-afd-aej.md` §8.2, Lacuna nº 1). Estes testes
provam determinismo e sensibilidade ao encadeamento, nunca conformidade
byte a byte contra um sistema já homologado. Ver
`docs/adr/ADR-012-formula-hash-registro-tipo-7-afd-nao-confirmada.md`.
"""

from __future__ import annotations

import datetime as dt

import pytest

from app.fiscal.afd.hash_tipo7 import InsumosHashTipo7, calcular_hash_tipo7

_FUSO = dt.timezone(dt.timedelta(hours=-3))


def _insumos(**sobrescreve: object) -> InsumosHashTipo7:
    base: dict[str, object] = {
        "nsr": 1,
        "tipo_registro": "7",
        "datahora_marcacao": dt.datetime(2026, 7, 1, 8, 0, 0, tzinfo=_FUSO),
        "cpf": "12345678901",
        "datahora_gravacao": dt.datetime(2026, 7, 1, 8, 0, 5, tzinfo=_FUSO),
        "identificador_coletor": "04",
        "indicador_offline": "0",
    }
    base.update(sobrescreve)
    return InsumosHashTipo7(**base)  # type: ignore[arg-type]


def test_determinismo() -> None:
    """Mesma entrada, sempre o mesmo hash -- o requisito mínimo de uma
    função de hash usada numa cadeia legal."""
    insumos = _insumos()
    assert calcular_hash_tipo7(insumos, None) == calcular_hash_tipo7(insumos, None)
    assert calcular_hash_tipo7(insumos, "a" * 64) == calcular_hash_tipo7(insumos, "a" * 64)


def test_e_um_sha256_hexadecimal_de_64_caracteres() -> None:
    resultado = calcular_hash_tipo7(_insumos(), None)
    assert len(resultado) == 64
    assert all(c in "0123456789abcdef" for c in resultado)


def test_primeiro_registro_sem_hash_anterior_difere_de_com_hash_anterior() -> None:
    """ADR-012, decisão 1: o primeiro registro da cadeia (sem hash anterior)
    omite o 8º insumo inteiramente -- produz um resultado DIFERENTE de um
    registro idêntico em tudo mais, mas com um hash anterior não vazio."""
    insumos = _insumos()
    sem_anterior = calcular_hash_tipo7(insumos, None)
    com_anterior = calcular_hash_tipo7(insumos, "b" * 64)
    assert sem_anterior != com_anterior


def test_string_vazia_equivale_a_none_para_hash_anterior() -> None:
    """`None` e string vazia produzem o mesmo resultado (os dois significam
    "omitir o 8o insumo", ADR-012)."""
    insumos = _insumos()
    assert calcular_hash_tipo7(insumos, None) == calcular_hash_tipo7(insumos, "")


def test_hash_anterior_diferente_produz_hash_diferente() -> None:
    """A cadeia é sensível ao elo anterior -- é o que torna a adulteração de
    um registro no meio da cadeia detectável (mesma propriedade documentada
    para a cadeia de F5, aplicada aqui à cadeia do ADR-012)."""
    insumos = _insumos()
    h1 = calcular_hash_tipo7(insumos, "c" * 64)
    h2 = calcular_hash_tipo7(insumos, "d" * 64)
    assert h1 != h2


@pytest.mark.parametrize(
    "campo,valor",
    [
        ("nsr", 2),
        ("datahora_marcacao", dt.datetime(2026, 7, 1, 9, 0, 0, tzinfo=_FUSO)),
        ("cpf", "98765432100"),
        ("datahora_gravacao", dt.datetime(2026, 7, 1, 9, 0, 5, tzinfo=_FUSO)),
        ("identificador_coletor", "01"),
        ("indicador_offline", "1"),
    ],
)
def test_cada_insumo_influencia_o_hash(campo: str, valor: object) -> None:
    """Muda cada um dos 6 primeiros insumos, um de cada vez, e confirma que
    o hash muda -- prova que nenhum campo é ignorado silenciosamente pela
    fórmula."""
    base = calcular_hash_tipo7(_insumos(), None)
    alterado = calcular_hash_tipo7(_insumos(**{campo: valor}), None)
    assert base != alterado


def test_nunca_reutiliza_marcacoes_hash_registro() -> None:
    """Prova estática mínima (complementa a análise de código do critério de
    aceite 8 do PCF): a fórmula do ADR-012 é auto-contida em
    `app.fiscal.afd.hash_tipo7`, sem nenhuma dependência de
    `app.marcacao.dominio.nsr.calcular_hash`/`canonicalizar_registro` (a
    fórmula de F5, 7 campos com separador 0x1F) -- os dois módulos calculam
    hashes de propósitos diferentes, de forma independente."""
    import app.fiscal.afd.hash_tipo7 as modulo

    assert not hasattr(modulo, "canonicalizar_registro")
    assert not hasattr(modulo, "calcular_hash")
