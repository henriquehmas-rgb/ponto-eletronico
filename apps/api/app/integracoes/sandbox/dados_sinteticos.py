"""Dados sinteticos puros do tenant de demonstracao (F13/A2, T8).

Nenhuma funcao deste modulo toca banco: sao geradores deterministicos de
`dict`/`dataclass` que `semear.py` consome. Separado de `semear.py` para que
o formato dos dados sinteticos seja testavel sem banco (ver
`apps/api/tests/f13/portal/test_dados_sinteticos.py`).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ColaboradorSintetico:
    """Molde de um colaborador sintetico. `sufixo` entra na matricula/CPF
    para os tres colaboradores nunca colidirem entre si."""

    sufixo: str
    nome_completo: str
    cargo: str


#: Tres colaboradores sinteticos plausiveis. Fixos (nao aleatorios): a
#: semeadura e get-or-create por `matricula`, e matricula precisa ser
#: estavel entre execucoes para o script continuar idempotente.
COLABORADORES_SINTETICOS: tuple[ColaboradorSintetico, ...] = (
    ColaboradorSintetico("01", "Ana Beatriz Sandbox", "Analista de RH"),
    ColaboradorSintetico("02", "Carlos Eduardo Sandbox", "Desenvolvedor"),
    ColaboradorSintetico("03", "Mariana Silva Sandbox", "Coordenadora Financeira"),
)


def matricula_sintetica(colaborador: ColaboradorSintetico) -> str:
    return f"SANDBOX{colaborador.sufixo}"


def cpf_sintetico(colaborador: ColaboradorSintetico) -> str:
    """11 digitos deterministicos (`dom_cpf` so valida formato, sem digito
    verificador -- mesma convencao de `tests/f5/conftest.py`)."""
    return f"111{colaborador.sufixo}22233344"[:11].ljust(11, "0")


def gerar_dias_uteis(*, terminando_em: dt.date, quantidade: int) -> list[dt.date]:
    """`quantidade` dias uteis (segunda a sexta), terminando em
    `terminando_em` (inclusive se for dia util) e andando para tras.
    Deterministico: mesma entrada, mesma saida -- essencial para a
    idempotencia da semeadura (T8, "rodar duas vezes nao duplica")."""
    dias: list[dt.date] = []
    cursor = terminando_em
    while len(dias) < quantidade:
        if cursor.weekday() < 5:  # 0=segunda ... 4=sexta
            dias.append(cursor)
        cursor -= dt.timedelta(days=1)
    dias.reverse()
    return dias


@dataclass(frozen=True, slots=True)
class MarcacaoPlanejada:
    """Um dos quatro batimentos de um dia util: entrada, saida para almoco,
    volta do almoco, saida."""

    data: dt.date
    hora: dt.time
    tipo_registro: str


#: (hora, minuto, tipo_registro) dos quatro batimentos de um dia de trabalho
#: padrao 8h-12h/13h-18h. `tipo_registro` segue o mesmo dominio de
#: `dominio/registro.py::DadosMarcacao.tipo_registro` (default "7", generico
#: -- a REDE de tipos legais especificos, "01".."99" do leiaute AFD/AEJ, e
#: assunto de F12/F5, fora do escopo deste seed).
_BATIMENTOS_DO_DIA: tuple[tuple[int, int], ...] = (
    (8, 0),  # entrada
    (12, 0),  # saida para almoco
    (13, 0),  # volta do almoco
    (18, 0),  # saida
)


def gerar_plano_de_marcacoes(dias: list[dt.date]) -> list[MarcacaoPlanejada]:
    """Quatro batimentos por dia util, sempre `tipo_registro="7"` (generico
    -- ver `DadosMarcacao.tipo_registro`, default do dominio de marcacao)."""
    plano: list[MarcacaoPlanejada] = []
    for dia in dias:
        for hora, minuto in _BATIMENTOS_DO_DIA:
            plano.append(MarcacaoPlanejada(data=dia, hora=dt.time(hora, minuto), tipo_registro="7"))
    return plano
