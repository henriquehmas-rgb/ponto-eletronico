"""Pareamento de marcacoes do dia (T2).

O REP-P **nao registra sentido legalmente** (`marcacoes.sentido_informado` so
vem preenchido quando o coletor informa, e nunca e verdade cega quando ausente
ou incoerente -- comentario da coluna em `schema.sql`, secao 8, e PCF da fase,
secao 2). **O pareamento definitivo e feito aqui**: ordena as marcacoes do dia
(e das bordas, quando a jornada cruza a meia-noite) por
`(datahora_marcacao, nsr)` -- ordenacao estavel exigida pelo ADR-004 -- e
alterna entrada/saida a partir da primeira marcacao do dia. `sentido_informado`
e conferido apenas como pista de coerencia (nunca reordena nem decide o
pareamento por si so): a funcao devolve, para cada marcacao emparelhada, se o
sentido informado (quando presente) bateu com a posicao esperada pela
alternancia, para que quem for montar `apuracao_componentes.detalhes` possa
expor essa evidencia sem recalcular nada.

Numero impar de marcacoes nunca e corrigido silenciosamente: o ultimo periodo
fica "aberto" (sem par de saida) e `ResultadoPareamento.marcacao_impar` sinaliza
a inconsistencia -- quem chama abre a ocorrencia `marcacao_impar` (este modulo
so detecta, nunca grava nada).
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

#: `sentido_informado` aceito pelo coletor (`marcacoes.sentido_informado`,
#: `indefinido` incluido pelo `CHECK` do schema mas tratado aqui como
#: "sem pista", igual a ausente).
Sentido = Literal["entrada", "saida"]


@dataclass(frozen=True, slots=True)
class MarcacaoParaPareamento:
    """Entrada minima e generica do pareamento.

    Deliberadamente NAO e o modelo ORM `Marcacao`: uma marcacao ficticia de
    tratamento `inclusao_marcacao` (categoria de `tipos_tratamento`, aplicada
    em `servico.py`) entra no pareamento exatamente como uma marcacao real,
    mas nunca vira uma linha de `marcacoes` (PCF, secao 2) -- por isso o
    pareamento so precisa dos quatro campos abaixo, nunca do registro inteiro.
    """

    id: UUID | None
    datahora: dt.datetime
    nsr: int
    sentido_informado: Sentido | None = None
    origem: Literal["marcacao", "tratamento"] = "marcacao"


@dataclass(frozen=True, slots=True)
class MarcacaoPareada:
    """Uma marcacao ja associada a posicao que a alternancia lhe atribuiu."""

    marcacao: MarcacaoParaPareamento
    sentido_atribuido: Sentido
    sentido_coerente: bool | None
    """`None` quando `sentido_informado` esta ausente (sem pista para
    conferir); `True`/`False` quando presente, conforme bateu ou nao com
    `sentido_atribuido`."""


@dataclass(frozen=True, slots=True)
class PeriodoTrabalhado:
    """Um par entrada/saida. `saida` e `None` quando o periodo ficou aberto
    (ultima marcacao do dia, numero impar -- `marcacao_impar`)."""

    entrada: MarcacaoPareada
    saida: MarcacaoPareada | None


@dataclass(frozen=True, slots=True)
class ResultadoPareamento:
    """Assinatura fixada pelo PCF da fase (T2): `parear_marcacoes(marcacoes:
    Sequence[Marcacao]) -> ResultadoPareamento`."""

    periodos: tuple[PeriodoTrabalhado, ...]
    marcacao_impar: bool
    total_marcacoes: int


def parear_marcacoes(marcacoes: Sequence[MarcacaoParaPareamento]) -> ResultadoPareamento:
    """Pareia as marcacoes de um dia (mais as bordas, ja incluidas pelo
    chamador quando a jornada cruza a meia-noite).

    Ordena por `(datahora, nsr)` -- ordenacao estavel do ADR-004, para que
    duas marcacoes no mesmo instante tenham ordem definida e determinística
    -- e alterna entrada/saida a partir da primeira. `sentido_informado` e
    conferido, nunca usado para decidir a alternancia (comentario da coluna
    em `schema.sql`: "o pareamento definitivo e feito na apuracao").

    Um numero impar de marcacoes deixa o ultimo periodo aberto (`saida=None`)
    e sinaliza `marcacao_impar=True`; a decisao de abrir ocorrencia e de quem
    chama (`detectar_ocorrencias_pareamento`), nao desta funcao.
    """
    ordenadas = sorted(marcacoes, key=lambda m: (m.datahora, m.nsr))
    total = len(ordenadas)

    periodos: list[PeriodoTrabalhado] = []
    indice = 0
    while indice < total:
        bruta_entrada = ordenadas[indice]
        entrada = MarcacaoPareada(
            marcacao=bruta_entrada,
            sentido_atribuido="entrada",
            sentido_coerente=_coerencia(bruta_entrada.sentido_informado, "entrada"),
        )
        if indice + 1 < total:
            bruta_saida = ordenadas[indice + 1]
            saida = MarcacaoPareada(
                marcacao=bruta_saida,
                sentido_atribuido="saida",
                sentido_coerente=_coerencia(bruta_saida.sentido_informado, "saida"),
            )
        else:
            saida = None
        periodos.append(PeriodoTrabalhado(entrada=entrada, saida=saida))
        indice += 2

    return ResultadoPareamento(
        periodos=tuple(periodos),
        marcacao_impar=(total % 2 == 1),
        total_marcacoes=total,
    )


def _coerencia(sentido_informado: Sentido | None, sentido_atribuido: Sentido) -> bool | None:
    if sentido_informado is None:
        return None
    return sentido_informado == sentido_atribuido


#: Codigos de ocorrencia que este modulo pode detectar (subconjunto do
#: `CHECK` de `ocorrencias.codigo`, schema.sql secao 9).
CODIGO_MARCACAO_IMPAR = "marcacao_impar"
CODIGO_SEM_MARCACAO = "sem_marcacao"

#: `jornada_dias`/`escala_ciclos` -- tipos de dia que NAO esperam marcacao
#: (folga e DSR sao dispensados de bater ponto). Demais tipos (`util`,
#: `feriado`, `ponto_facultativo`, `compensado`, `afastamento`) esperam
#: trabalho e por isso geram `sem_marcacao` quando o dia nao tem nenhuma
#: marcacao -- decisao documentada aqui porque o PCF (secao 2) so cita
#: "tipo_dia != folga/dsr" em prosa, sem enumerar a lista completa.
_TIPOS_DIA_SEM_TRABALHO_ESPERADO = frozenset({"folga", "dsr"})


def detectar_ocorrencias_pareamento(
    resultado: ResultadoPareamento, *, tipo_dia: str
) -> tuple[str, ...]:
    """Codigos de ocorrencia que o pareamento por si so basta para detectar.

    `marcacao_impar`: numero impar de marcacoes, qualquer que seja o tipo do
    dia (uma marcacao orfa e sempre uma inconsistencia).
    `sem_marcacao`: nenhuma marcacao num dia que esperava trabalho (tipo do
    dia fora de `_TIPOS_DIA_SEM_TRABALHO_ESPERADO`).
    """
    codigos: list[str] = []
    if resultado.marcacao_impar:
        codigos.append(CODIGO_MARCACAO_IMPAR)
    if resultado.total_marcacoes == 0 and tipo_dia not in _TIPOS_DIA_SEM_TRABALHO_ESPERADO:
        codigos.append(CODIGO_SEM_MARCACAO)
    return tuple(codigos)
