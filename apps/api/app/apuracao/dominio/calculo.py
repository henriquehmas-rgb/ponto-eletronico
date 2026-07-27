"""Horas normais/extras por faixa e fator, intrajornada, interjornada, DSR e
faltas/atrasos/saidas antecipadas (T3 e T4).

`calcular_dia` e a funcao pura que orquestra `pareamento` + `tolerancia` +
`noturno`: recebe os insumos ja resolvidos (pareamento do dia, janela
prevista, configuracao da jornada) e devolve os totais de `apuracoes_dia`
mais a decomposicao em `apuracao_componentes` e as ocorrencias detectadas.
Nao le relogio, nao le banco, nao publica evento -- ADR-004, ponto 1: "funcao
pura de insumos versionados". Quem le banco e publica evento e `servico.py`.

**Decisoes de modelagem desta fase, documentadas para o relatorio da fase**
(o PCF descreve os principios em prosa -- a formalizacao exata e escolha
deste modulo):

1. `trabalhado_minutos` e o total de relogio efetivamente pareado (soma dos
   periodos com entrada e saida), sem qualquer ajuste de tolerancia --
   tolerancia decide se um desvio vira ocorrencia/efeito no calculo, nunca
   se as marcacoes "contam" como trabalhadas.
2. `normais_minutos = min(trabalhado_minutos, previsto_minutos)`;
   `extras_minutos = max(0, trabalhado_minutos - previsto_minutos)`;
   `falta_minutos = max(0, previsto_minutos - trabalhado_minutos -
   abono_minutos)` -- as tres se derivam so de `trabalhado_minutos` vs
   `previsto_minutos`, nunca descontam duas vezes o mesmo desvio.
3. Atraso/saida antecipada sao medidos comparando cada periodo trabalhado ao
   segmento previsto de MESMO INDICE (entrada do dia, volta de cada
   intervalo, ...; ver `_montar_segmentos_previstos`) -- atraso e a soma dos
   atrasos em TODOS os inicios de segmento; saida antecipada e so do ULTIMO
   segmento (chegar atrasado da janta nao e "saida antecipada", e sim mais
   atraso). Os dois desvios (jah tolerancia aplicada) sao os que entram nos
   componentes/ocorrencias -- nunca reduzem `trabalhado_minutos`.
4. Extra noturno (`extras_noturnas_minutos`) e a fatia de `extras_minutos`
   que cai dentro do periodo noturno observado (`noturno_minutos`), limitada
   ao menor dos dois -- aproximacao documentada aqui: nao tenta separar
   "quais minutos exatos, dentro do periodo noturno, sao extra" quando o
   periodo trabalhado tem trechos extra tanto antes quanto depois do
   expediente previsto.
5. `jornadas.fatores_extra` (JSONB) segue o formato
   `{"faixas": [{"ateMinutos": 60, "fator": 1.5}, ..., {"fator": 2.0}]}`:
   cada faixa cobre os minutos ACUMULADOS de extra ate `ateMinutos`
   (a ultima faixa, sem `ateMinutos`, cobre o excedente). Sem configuracao
   (`fatores_extra` nulo/vazio), o fallback e uma unica faixa a
   `Decimal("1.5")` (minimo legal de 50% -- art. 7, XVI da Constituicao),
   documentado aqui por nao haver default de coluna no schema.
6. DSR: dia `tipo_dia == 'dsr'` efetivamente trabalhado credita
   `dsr_credito_minutos` (o trabalho no repouso, fator `Decimal("2.0")`,
   convencao usual de dobra dominical/feriado -- nenhuma coluna de fator
   especifico existe para DSR, entao o valor e fixado aqui e registrado
   como achado no relatorio da fase). A perda de DSR por falta injustificada
   na semana (`dsr_debito_minutos`) depende de contexto de SEMANA INTEIRA
   que este modulo, function pura de UM dia, nao tem -- `servico.py` decide
   `dsr_perdido_por_falta_semana` e passa o valor a debitar
   (`dsr_valor_debito_minutos`); sem informacao (o caso comum hoje, ja que
   nao ha campo de politica para "quais faltas derrubam o DSR" -- PCF secao
   2, achado registrado em `docs/backlog.md`), nao debita nada.
7. Sobreaviso, prontidao e pausas NR-17 (`apuracoes_dia.sobreaviso_minutos`,
   `prontidao_minutos`, `pausas_nr17_minutos`) NAO sao calculados por este
   modulo: o PCF da fase (T2..T4) nunca os lista entre as responsabilidades
   de A1 (eles nascem de turno/jornada especifico e de dispositivo NR-17,
   fora do escopo desta tarefa) -- ficam em zero, documentado no relatorio.
"""

from __future__ import annotations

import datetime as dt
import itertools
from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from app.apuracao.dominio.noturno import aplicar_hora_ficta, minutos_no_periodo_noturno
from app.apuracao.dominio.pareamento import ResultadoPareamento, detectar_ocorrencias_pareamento
from app.apuracao.dominio.tolerancia import aplicar_tolerancia

#: Fator padrao de extra quando `jornadas.fatores_extra` esta vazio -- minimo
#: legal (art. 7, XVI da Constituicao). Ver decisao 5 no docstring do modulo.
FATOR_EXTRA_PADRAO = Decimal("1.5")
#: Fator de convencao para trabalho em dia de DSR -- ver decisao 6.
FATOR_DSR_TRABALHADO = Decimal("2.0")


@dataclass(frozen=True, slots=True)
class FaixaExtra:
    """Uma faixa de `jornadas.fatores_extra`. `ate_minutos=None` e a faixa
    final (excedente), sem teto."""

    fator: Decimal
    ate_minutos: int | None = None


@dataclass(frozen=True, slots=True)
class ConfiguracaoCalculo:
    """Subconjunto de `jornadas` necessario ao calculo puro -- extraido do
    ORM por `servico.py`, nunca lido diretamente por este modulo."""

    tolerancia_marcacao_minutos: int
    tolerancia_diaria_minutos: int
    descontar_tudo_se_exceder: bool
    intervalo_minimo_minutos: int | None
    interjornada_minima_minutos: int
    noturno_inicio: dt.time
    noturno_fim: dt.time
    hora_ficta_noturna: bool
    prorrogacao_noturna: bool
    limite_extra_diario_minutos: int
    limite_jornada_diaria_minutos: int
    faixas_extra: tuple[FaixaExtra, ...] = field(
        default_factory=lambda: (FaixaExtra(fator=FATOR_EXTRA_PADRAO),)
    )


def montar_faixas_extra(fatores_extra: dict[str, Any] | None) -> tuple[FaixaExtra, ...]:
    """Converte `jornadas.fatores_extra` (JSONB, formato na decisao 5 do
    docstring do modulo) nas faixas usadas por `_distribuir_extra_por_faixa`.
    """
    if not fatores_extra:
        return (FaixaExtra(fator=FATOR_EXTRA_PADRAO),)
    brutas = fatores_extra.get("faixas")
    if not isinstance(brutas, list) or not brutas:
        return (FaixaExtra(fator=FATOR_EXTRA_PADRAO),)
    faixas: list[FaixaExtra] = []
    for bruta in brutas:
        fator = Decimal(str(bruta["fator"]))
        ate = bruta.get("ateMinutos")
        faixas.append(FaixaExtra(fator=fator, ate_minutos=int(ate) if ate is not None else None))
    return tuple(faixas)


@dataclass(frozen=True, slots=True)
class ComponenteCalculado:
    """Espelha uma linha de `apuracao_componentes` (sem `id`/`apuracao_dia_id`,
    preenchidos por `servico.py` na persistencia)."""

    codigo: str
    categoria: str
    minutos: int
    fator: Decimal
    minutos_equivalentes: int
    origem: str
    inicio: dt.datetime | None = None
    fim: dt.datetime | None = None
    detalhes: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class OcorrenciaDetectada:
    """Uma ocorrencia que `calcular_dia` detectou. `servico.py` decide se ja
    existe uma ocorrencia aberta igual antes de inserir (idempotencia de
    ocorrencia, ver docstring de `servico.py`)."""

    codigo: str
    severidade: str
    descricao: str
    detalhes: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class ResultadoCalculoDia:
    """Os totais de `apuracoes_dia` que este modulo calcula, mais a
    decomposicao e as ocorrencias. Campos que `apuracoes_dia` tem mas que
    este modulo nao calcula (sobreaviso/prontidao/pausas NR-17, decisao 7)
    ficam de fora deste dataclass -- `servico.py` os grava como zero."""

    trabalhado_minutos: int
    normais_minutos: int
    extras_minutos: int
    extras_noturnas_minutos: int
    noturno_minutos: int
    noturno_ficta_minutos: int
    intervalo_minutos: int
    intervalo_previsto_minutos: int
    intrajornada_suprimida_minutos: int
    interjornada_minutos: int | None
    interjornada_violada: bool
    atraso_minutos: int
    saida_antecipada_minutos: int
    falta_minutos: int
    abono_minutos: int
    tolerancia_aplicada_minutos: int
    dsr_credito_minutos: int
    dsr_debito_minutos: int
    quantidade_marcacoes: int
    marcacoes_impares: bool
    componentes: tuple[ComponenteCalculado, ...]
    ocorrencias: tuple[OcorrenciaDetectada, ...]


def _arredondar_equivalente(minutos: int, fator: Decimal) -> int:
    """`minutos_equivalentes`: minutos multiplicados por fator, arredondado
    ao inteiro mais proximo (`ROUND_HALF_UP`, unica regra de arredondamento
    deste modulo para conversao de fator -- documentado aqui, ADR-004 ponto
    2: fator e `NUMERIC` aplicado sobre inteiro com arredondamento unico)."""
    equivalente = (Decimal(minutos) * fator).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(equivalente)


def _distribuir_extra_por_faixa(
    extras_minutos: int, faixas: Sequence[FaixaExtra]
) -> list[tuple[int, Decimal]]:
    """Distribui `extras_minutos` cumulativamente pelas faixas configuradas.
    Devolve uma lista de `(minutos_da_faixa, fator)`, uma entrada por faixa
    com minutos > 0, na ordem das faixas."""
    partes: list[tuple[int, Decimal]] = []
    restante = extras_minutos
    piso_acumulado = 0
    for faixa in faixas:
        if restante <= 0:
            break
        if faixa.ate_minutos is None:
            capacidade = restante
        else:
            capacidade = max(0, faixa.ate_minutos - piso_acumulado)
            piso_acumulado = faixa.ate_minutos
        minutos_faixa = min(restante, capacidade)
        if minutos_faixa > 0:
            partes.append((minutos_faixa, faixa.fator))
            restante -= minutos_faixa
    return partes


@dataclass(frozen=True, slots=True)
class _Segmento:
    inicio: dt.datetime
    fim: dt.datetime


def _montar_segmentos_previstos(
    entrada_prevista: dt.datetime | None,
    saida_prevista: dt.datetime | None,
    intervalos_previstos: Sequence[tuple[dt.datetime, dt.datetime]],
) -> tuple[_Segmento, ...]:
    """Quebra a janela prevista do dia (entrada -> [intervalos] -> saida) em
    segmentos de trabalho continuo. Sem entrada/saida previstas (dia sem
    horario -- folga/DSR puros), nao ha segmento nenhum."""
    if entrada_prevista is None or saida_prevista is None:
        return ()
    fronteiras: list[dt.datetime] = [entrada_prevista]
    for inicio_intervalo, fim_intervalo in sorted(intervalos_previstos, key=lambda p: p[0]):
        fronteiras.append(inicio_intervalo)
        fronteiras.append(fim_intervalo)
    fronteiras.append(saida_prevista)
    segmentos = []
    for i in range(0, len(fronteiras) - 1, 2):
        inicio, fim = fronteiras[i], fronteiras[i + 1]
        if fim > inicio:
            segmentos.append(_Segmento(inicio=inicio, fim=fim))
    return tuple(segmentos)


def calcular_dia(
    *,
    tipo_dia: str,
    entrada_prevista: dt.datetime | None,
    saida_prevista: dt.datetime | None,
    intervalos_previstos: Sequence[tuple[dt.datetime, dt.datetime]],
    previsto_minutos: int,
    resultado_pareamento: ResultadoPareamento,
    ultima_marcacao_dia_anterior: dt.datetime | None,
    config: ConfiguracaoCalculo,
    abono_minutos: int = 0,
    dsr_perdido_por_falta_semana: bool = False,
    dsr_valor_debito_minutos: int = 0,
) -> ResultadoCalculoDia:
    """Funcao pura central desta fase (T3+T4). Ver docstring do modulo para
    as decisoes de modelagem numeradas 1..7."""
    componentes: list[ComponenteCalculado] = []
    ocorrencias: list[OcorrenciaDetectada] = []

    periodos = resultado_pareamento.periodos
    periodos_fechados = [p for p in periodos if p.saida is not None]

    trabalhado_minutos = sum(
        int((p.saida.marcacao.datahora - p.entrada.marcacao.datahora).total_seconds() // 60)
        for p in periodos_fechados
        if p.saida is not None
    )

    # --- Intrajornada -----------------------------------------------------
    intervalo_observado = 0
    for anterior, proximo in itertools.pairwise(periodos_fechados):
        if anterior.saida is None:
            continue
        gap = int(
            (proximo.entrada.marcacao.datahora - anterior.saida.marcacao.datahora).total_seconds()
            // 60
        )
        if gap > 0:
            intervalo_observado += gap
    intervalo_previsto_minutos = sum(
        int((fim - inicio).total_seconds() // 60) for inicio, fim in intervalos_previstos
    )
    intrajornada_suprimida = 0
    if config.intervalo_minimo_minutos is not None and periodos_fechados:
        intrajornada_suprimida = max(0, config.intervalo_minimo_minutos - intervalo_observado)
        if intrajornada_suprimida > 0:
            indenizacao_fator = Decimal("0.5")
            componentes.append(
                ComponenteCalculado(
                    codigo="intrajornada_indenizada",
                    categoria="indenizacao",
                    minutos=intrajornada_suprimida,
                    fator=indenizacao_fator,
                    minutos_equivalentes=_arredondar_equivalente(
                        intrajornada_suprimida, indenizacao_fator
                    ),
                    origem="regra",
                )
            )
            ocorrencias.append(
                OcorrenciaDetectada(
                    codigo="intrajornada_suprimida",
                    severidade="alta",
                    descricao=(
                        f"Intervalo intrajornada suprimido em {intrajornada_suprimida} minuto(s)."
                    ),
                    detalhes={
                        "intervaloMinimoMinutos": config.intervalo_minimo_minutos,
                        "intervaloObservadoMinutos": intervalo_observado,
                    },
                )
            )

    # --- Interjornada -------------------------------------------------------
    interjornada_minutos: int | None = None
    interjornada_violada = False
    if ultima_marcacao_dia_anterior is not None and periodos:
        primeira_entrada = periodos[0].entrada.marcacao.datahora
        interjornada_minutos = int(
            (primeira_entrada - ultima_marcacao_dia_anterior).total_seconds() // 60
        )
        if interjornada_minutos < config.interjornada_minima_minutos:
            interjornada_violada = True
            ocorrencias.append(
                OcorrenciaDetectada(
                    codigo="interjornada_violada",
                    severidade="alta",
                    descricao=(
                        f"Interjornada de {interjornada_minutos} minuto(s), "
                        f"abaixo do minimo de {config.interjornada_minima_minutos}."
                    ),
                    detalhes={"interjornadaMinimaMinutos": config.interjornada_minima_minutos},
                )
            )

    # --- Atraso / saida antecipada (com tolerancia) ------------------------
    segmentos = _montar_segmentos_previstos(entrada_prevista, saida_prevista, intervalos_previstos)
    atraso_bruto = 0
    saida_antecipada_bruta = 0
    total_pares = min(len(segmentos), len(periodos))
    for indice in range(total_pares):
        segmento = segmentos[indice]
        periodo = periodos[indice]
        entrada_real = periodo.entrada.marcacao.datahora
        if entrada_real > segmento.inicio:
            atraso_bruto += int((entrada_real - segmento.inicio).total_seconds() // 60)
        if indice == total_pares - 1 and periodo.saida is not None:
            saida_real = periodo.saida.marcacao.datahora
            if saida_real < segmento.fim:
                saida_antecipada_bruta += int((segmento.fim - saida_real).total_seconds() // 60)

    resultado_tolerancia = aplicar_tolerancia(
        (atraso_bruto, saida_antecipada_bruta),
        tolerancia_marcacao_minutos=config.tolerancia_marcacao_minutos,
        tolerancia_diaria_minutos=config.tolerancia_diaria_minutos,
        descontar_tudo_se_exceder=config.descontar_tudo_se_exceder,
    )
    atraso_minutos, saida_antecipada_minutos = resultado_tolerancia.desvios_computados_minutos
    if atraso_minutos > 0:
        ocorrencias.append(
            OcorrenciaDetectada(
                codigo="atraso",
                severidade="atencao",
                descricao=f"Atraso de {atraso_minutos} minuto(s) apos a tolerancia.",
            )
        )
    if saida_antecipada_minutos > 0:
        ocorrencias.append(
            OcorrenciaDetectada(
                codigo="saida_antecipada",
                severidade="atencao",
                descricao=f"Saida antecipada de {saida_antecipada_minutos} minuto(s).",
            )
        )

    # --- Normais / extras ---------------------------------------------------
    normais_minutos = min(trabalhado_minutos, previsto_minutos)
    extras_minutos = max(0, trabalhado_minutos - previsto_minutos)
    if normais_minutos > 0:
        componentes.append(
            ComponenteCalculado(
                codigo="normal",
                categoria="normal",
                minutos=normais_minutos,
                fator=Decimal("1.0"),
                minutos_equivalentes=normais_minutos,
                origem="marcacao",
            )
        )
    for indice, (minutos_faixa, fator) in enumerate(
        _distribuir_extra_por_faixa(extras_minutos, config.faixas_extra), start=1
    ):
        componentes.append(
            ComponenteCalculado(
                codigo=f"he_faixa_{indice}",
                categoria="extra",
                minutos=minutos_faixa,
                fator=fator,
                minutos_equivalentes=_arredondar_equivalente(minutos_faixa, fator),
                origem="marcacao",
            )
        )
    if extras_minutos > config.limite_extra_diario_minutos:
        ocorrencias.append(
            OcorrenciaDetectada(
                codigo="extra_excedida",
                severidade="alta",
                descricao=(
                    f"Hora extra de {extras_minutos} minuto(s) excede o limite diario de "
                    f"{config.limite_extra_diario_minutos}."
                ),
            )
        )
    if trabalhado_minutos > config.limite_jornada_diaria_minutos:
        ocorrencias.append(
            OcorrenciaDetectada(
                codigo="jornada_excedida",
                severidade="critica",
                descricao=(
                    f"Jornada de {trabalhado_minutos} minuto(s) excede o limite diario de "
                    f"{config.limite_jornada_diaria_minutos}."
                ),
            )
        )

    # --- Noturno + hora ficta ------------------------------------------------
    minutos_relogio_noturno = sum(
        minutos_no_periodo_noturno(
            p.entrada.marcacao.datahora,
            p.saida.marcacao.datahora,
            noturno_inicio=config.noturno_inicio,
            noturno_fim=config.noturno_fim,
            prorrogacao_noturna=config.prorrogacao_noturna,
        )
        for p in periodos_fechados
        if p.saida is not None
    )
    hora_ficta = aplicar_hora_ficta(
        minutos_relogio_noturno, hora_ficta_noturna=config.hora_ficta_noturna
    )
    if hora_ficta.noturno_ficta_minutos > 0:
        componentes.append(
            ComponenteCalculado(
                codigo="adicional_noturno_hora_ficta",
                categoria="noturno",
                minutos=hora_ficta.noturno_ficta_minutos,
                fator=Decimal("1.0"),
                minutos_equivalentes=hora_ficta.noturno_ficta_minutos,
                origem="regra",
                detalhes={"minutosRelogioNoturno": hora_ficta.noturno_minutos},
            )
        )
    # Extra noturno: fatia de extras_minutos que cai no periodo noturno
    # observado -- decisao 4 do docstring do modulo (aproximacao pelo menor
    # dos dois totais, sem separar minuto a minuto).
    extras_noturnas_minutos = min(extras_minutos, hora_ficta.noturno_minutos)

    # --- DSR -----------------------------------------------------------------
    dsr_credito_minutos = 0
    dsr_debito_minutos = 0
    if tipo_dia == "dsr" and trabalhado_minutos > 0:
        dsr_credito_minutos = trabalhado_minutos
        componentes.append(
            ComponenteCalculado(
                codigo="dsr_trabalhado",
                categoria="dsr",
                minutos=trabalhado_minutos,
                fator=FATOR_DSR_TRABALHADO,
                minutos_equivalentes=_arredondar_equivalente(
                    trabalhado_minutos, FATOR_DSR_TRABALHADO
                ),
                origem="regra",
            )
        )
        ocorrencias.append(
            OcorrenciaDetectada(
                codigo="dsr_violado",
                severidade="atencao",
                descricao=f"Trabalho de {trabalhado_minutos} minuto(s) em dia de DSR.",
            )
        )
    if tipo_dia == "dsr" and dsr_perdido_por_falta_semana and dsr_valor_debito_minutos > 0:
        dsr_debito_minutos = dsr_valor_debito_minutos

    # --- Falta ------------------------------------------------------------
    falta_minutos = max(0, previsto_minutos - trabalhado_minutos - abono_minutos)
    if falta_minutos > 0:
        componentes.append(
            ComponenteCalculado(
                codigo="falta",
                categoria="falta",
                minutos=falta_minutos,
                fator=Decimal("1.0"),
                minutos_equivalentes=falta_minutos,
                origem="regra",
            )
        )
        ocorrencias.append(
            OcorrenciaDetectada(
                codigo="falta",
                severidade="alta",
                descricao=f"Falta de {falta_minutos} minuto(s) nao coberta por abono.",
            )
        )

    ocorrencias_pareamento = detectar_ocorrencias_pareamento(
        resultado_pareamento, tipo_dia=tipo_dia
    )
    for codigo in ocorrencias_pareamento:
        if codigo == "marcacao_impar":
            ocorrencias.append(
                OcorrenciaDetectada(
                    codigo=codigo,
                    severidade="alta",
                    descricao="Numero impar de marcacoes no dia; falta o par de saida.",
                )
            )
        else:
            ocorrencias.append(
                OcorrenciaDetectada(
                    codigo=codigo,
                    severidade="alta",
                    descricao="Nenhuma marcacao registrada em dia que esperava trabalho.",
                )
            )

    return ResultadoCalculoDia(
        trabalhado_minutos=trabalhado_minutos,
        normais_minutos=normais_minutos,
        extras_minutos=extras_minutos,
        extras_noturnas_minutos=extras_noturnas_minutos,
        noturno_minutos=hora_ficta.noturno_minutos,
        noturno_ficta_minutos=hora_ficta.noturno_ficta_minutos,
        intervalo_minutos=intervalo_observado,
        intervalo_previsto_minutos=intervalo_previsto_minutos,
        intrajornada_suprimida_minutos=intrajornada_suprimida,
        interjornada_minutos=interjornada_minutos,
        interjornada_violada=interjornada_violada,
        atraso_minutos=atraso_minutos,
        saida_antecipada_minutos=saida_antecipada_minutos,
        falta_minutos=falta_minutos,
        abono_minutos=abono_minutos,
        tolerancia_aplicada_minutos=resultado_tolerancia.tolerancia_aplicada_minutos,
        dsr_credito_minutos=dsr_credito_minutos,
        dsr_debito_minutos=dsr_debito_minutos,
        quantidade_marcacoes=resultado_pareamento.total_marcacoes,
        marcacoes_impares=resultado_pareamento.marcacao_impar,
        componentes=tuple(componentes),
        ocorrencias=tuple(ocorrencias),
    )
