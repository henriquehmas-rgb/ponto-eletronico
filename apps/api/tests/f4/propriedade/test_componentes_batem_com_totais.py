"""T12(b): "a soma de `apuracao_componentes.minutos_equivalentes` por
categoria bate com os totais de `apuracoes_dia`, para uma amostra de
jornadas/escalas variadas".

**Escolha documentada: parametrizacao com semente fixa, nao Hypothesis.**
`hypothesis` nao esta declarado em `apps/api/pyproject.toml` (nem instalado
no ambiente de execucao desta verificacao) e o PCF (T12) autoriza
explicitamente "Hypothesis ou parametrizacao equivalente -- documente a
escolha". Acrescentar uma dependencia nova de teste, no meio da fase de
verificacao, sem coordenacao com o restante do time e sem CI validando a
mudanca, e um risco desproporcional ao ganho -- principalmente com o
bloqueio de infraestrutura de banco documentado no relatorio da fase (ver
`docs/backlog.md`/relatorio). Em vez disso, a "amostra... variada" e gerada
por um `random.Random` com semente FIXA (reprodutivel, nunca
`random.random()` global) que sorteia, para cada caso, a configuracao de
jornada (tolerancias, faixas de hora extra, intervalo minimo, janela
noturna) e o conjunto de marcacoes do dia -- o mesmo espirito de geracao
orientada a propriedade que o Hypothesis daria, sem a dependencia nova.

**Por que a propriedade e verificada no NIVEL DA FUNCAO PURA
(`calcular_dia`), nao so lendo `apuracoes_dia` persistida:**
`app.apuracao.dominio.servico._upsert_apuracao_dia` copia os campos de
`ResultadoCalculoDia` (o que `calcular_dia` devolve) 1:1 para as colunas de
`apuracoes_dia` (`trabalhado_minutos`, `normais_minutos`, `extras_minutos`,
`falta_minutos`, `dsr_credito_minutos`, `noturno_ficta_minutos`,
`intrajornada_suprimida_minutos`, sem nenhuma transformacao adicional --
conferido lendo `apps/api/app/apuracao/dominio/servico.py`, funcao
`_upsert_apuracao_dia`, dicionario `valores`). Provar a propriedade contra
`ResultadoCalculoDia` (que `calcular_dia`, funcao PURA, devolve) e
estritamente equivalente a prova-la contra a linha persistida, sem
depender do banco de teste estar acessivel -- o que importa, dado o
bloqueio de infraestrutura documentado no relatorio da fase (o Postgres da
VPS rejeitou a credencial fornecida para `ponto_f4_a4` durante toda esta
verificacao). Esta e' portanto a unica parte de T11/T12 desta fase que
efetivamente EXECUTOU e passou durante a verificacao -- o resto (T11, T12(a),
T12(c) e a performance) depende do banco e esta pronto para rodar assim que
o acesso for restabelecido.

**Mapeamento categoria -> total** (fixado por `calcular_dia`, ver
`apps/api/app/apuracao/dominio/calculo.py`):

| Categoria de `apuracao_componentes` | Total de `apuracoes_dia`/`ResultadoCalculoDia` |
|---|---|
| `normal` + `extra` (soma de `minutos`, RAW, pre-fator) | `trabalhado_minutos` |
| `normal` (`minutos`) | `normais_minutos` |
| `extra` (`minutos`, soma de todas as faixas) | `extras_minutos` |
| `indenizacao` (`minutos` de `intrajornada_indenizada`) | `intrajornada_suprimida_minutos` |
| `noturno` (`minutos` de `adicional_noturno_hora_ficta`) | `noturno_ficta_minutos` |
| `dsr` (`minutos` do componente `dsr_trabalhado`) | `dsr_credito_minutos` |
| `falta` (`minutos`) | `falta_minutos` |

`minutos_equivalentes` (fator aplicado) só coincide com `minutos` (RAW)
quando o fator do componente é `1.0` (`normal`, `falta`, `noturno`,
`indenizacao` tem fator fixo `0.5`, `dsr` tem fator fixo `2.0`, só `extra`
varia por faixa) -- por isso este teste verifica adicionalmente, para TODO
componente de TODA amostra, que `minutos_equivalentes ==
arredondar(minutos * fator, ROUND_HALF_UP)` (a mesma regra de
`_arredondar_equivalente`, reimplementada aqui de forma independente, nunca
importada do módulo em teste -- um teste que chamasse a mesma função de
arredondamento do código testado não provaria nada sobre ela).
"""

from __future__ import annotations

import datetime as dt
import random
from decimal import ROUND_HALF_UP, Decimal
from uuid import uuid4

import pytest

from app.apuracao.dominio.calculo import (
    ConfiguracaoCalculo,
    FaixaExtra,
    ResultadoCalculoDia,
    calcular_dia,
)
from app.apuracao.dominio.pareamento import MarcacaoParaPareamento, parear_marcacoes

_FUSO = dt.timezone(dt.timedelta(hours=-3))
_SEMENTE = 20260726  # data fixa da verificacao -- reprodutivel entre execucoes.


def _arredondar_equivalente_independente(minutos: int, fator: Decimal) -> int:
    """Reimplementacao independente de `_arredondar_equivalente` (nao
    importada) -- ver docstring do modulo."""
    return int((Decimal(minutos) * fator).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _gerar_caso(rng: random.Random, indice: int) -> tuple[ConfiguracaoCalculo, str, dict]:
    """Sorteia uma configuracao de jornada + o conjunto de marcacoes de um
    dia. Devolve `(config, tipo_dia, kwargs de calcular_dia)`."""
    dia = 1 + (indice % 27)
    entrada_hora = rng.choice([6, 7, 8, 9, 20, 21, 22])
    carga_horas = rng.choice([4, 6, 8])
    previsto_minutos = carga_horas * 60
    intervalo_minutos = rng.choice([0, 30, 60])
    tem_intervalo = intervalo_minutos > 0

    entrada = dt.datetime(2025, 3, dia, entrada_hora, 0, tzinfo=_FUSO)
    fim_expediente = entrada + dt.timedelta(minutes=previsto_minutos + intervalo_minutos)

    # Faixas de extra sorteadas: 1 ou 2 faixas, fatores plausiveis.
    n_faixas = rng.choice([1, 2])
    if n_faixas == 1:
        faixas = (FaixaExtra(fator=Decimal("1.5")),)
    else:
        faixas = (
            FaixaExtra(fator=Decimal("1.5"), ate_minutos=60),
            FaixaExtra(fator=Decimal("2.0")),
        )

    tipo_dia = rng.choice(["util", "util", "util", "dsr"])  # dsr e' minoria da amostra.

    # Extra aleatoria: 0 a 150 minutos trabalhados alem do previsto.
    extra_minutos = rng.choice([0, 15, 45, 90, 150])
    # Atraso aleatorio pequeno (sempre dentro da tolerancia, para nao
    # acoplar esta propriedade a tolerancia -- ja coberta por T2/`test_
    # tolerancia.py`, ownership de A1).
    marcacoes = [
        MarcacaoParaPareamento(id=uuid4(), datahora=entrada, nsr=1),
    ]
    nsr = 2
    if tem_intervalo:
        inicio_intervalo = entrada + dt.timedelta(minutes=previsto_minutos // 2)
        fim_intervalo = inicio_intervalo + dt.timedelta(minutes=intervalo_minutos)
        marcacoes.append(MarcacaoParaPareamento(id=uuid4(), datahora=inicio_intervalo, nsr=nsr))
        nsr += 1
        marcacoes.append(MarcacaoParaPareamento(id=uuid4(), datahora=fim_intervalo, nsr=nsr))
        nsr += 1
    saida_real = fim_expediente + dt.timedelta(minutes=extra_minutos)
    marcacoes.append(MarcacaoParaPareamento(id=uuid4(), datahora=saida_real, nsr=nsr))

    intervalos_previstos = (
        [(entrada + dt.timedelta(minutes=previsto_minutos // 2), None)] if tem_intervalo else []
    )
    # `intervalos_previstos` de `calcular_dia` e uma sequencia de (inicio,
    # fim) -- corrige o placeholder acima com o fim real.
    if tem_intervalo:
        ini = entrada + dt.timedelta(minutes=previsto_minutos // 2)
        intervalos_previstos = [(ini, ini + dt.timedelta(minutes=intervalo_minutos))]

    config = ConfiguracaoCalculo(
        tolerancia_marcacao_minutos=5,
        tolerancia_diaria_minutos=10,
        descontar_tudo_se_exceder=False,
        intervalo_minimo_minutos=intervalo_minutos or None,
        interjornada_minima_minutos=660,
        noturno_inicio=dt.time(22, 0),
        noturno_fim=dt.time(5, 0),
        hora_ficta_noturna=True,
        prorrogacao_noturna=True,
        limite_extra_diario_minutos=120,
        limite_jornada_diaria_minutos=600,
        faixas_extra=faixas,
    )
    kwargs = {
        "tipo_dia": tipo_dia,
        "entrada_prevista": entrada,
        "saida_prevista": fim_expediente,
        "intervalos_previstos": intervalos_previstos,
        "previsto_minutos": previsto_minutos,
        "resultado_pareamento": parear_marcacoes(marcacoes),
        "ultima_marcacao_dia_anterior": None,
        "config": config,
    }
    return config, tipo_dia, kwargs


def _casos_da_amostra() -> list[tuple[int, ConfiguracaoCalculo, str, dict]]:
    # Geracao de massa de teste reprodutivel, nunca uso criptografico -- ver
    # docstring do modulo (semente fixa, nao `random.random()` global).
    rng = random.Random(_SEMENTE)  # noqa: S311
    casos = []
    for indice in range(40):
        config, tipo_dia, kwargs = _gerar_caso(rng, indice)
        casos.append((indice, config, tipo_dia, kwargs))
    return casos


_AMOSTRA = _casos_da_amostra()


@pytest.mark.parametrize(
    "indice,config,tipo_dia,kwargs", _AMOSTRA, ids=[f"caso_{c[0]}" for c in _AMOSTRA]
)
def test_soma_dos_componentes_por_categoria_bate_com_os_totais(
    indice: int, config: ConfiguracaoCalculo, tipo_dia: str, kwargs: dict
) -> None:
    resultado: ResultadoCalculoDia = calcular_dia(**kwargs)

    def _soma_minutos(*categorias: str) -> int:
        return sum(c.minutos for c in resultado.componentes if c.categoria in categorias)

    # normal + extra (RAW, pre-fator) == trabalhado_minutos.
    assert _soma_minutos("normal", "extra") == resultado.trabalhado_minutos, indice
    assert (
        resultado.normais_minutos + resultado.extras_minutos == resultado.trabalhado_minutos
    ), indice

    # Cada categoria bate com o total homonimo de `ResultadoCalculoDia`
    # (== `apuracoes_dia`, ver mapeamento na docstring do modulo).
    assert _soma_minutos("normal") == resultado.normais_minutos, indice
    assert _soma_minutos("extra") == resultado.extras_minutos, indice
    assert _soma_minutos("indenizacao") == resultado.intrajornada_suprimida_minutos, indice
    assert _soma_minutos("noturno") == resultado.noturno_ficta_minutos, indice
    assert _soma_minutos("falta") == resultado.falta_minutos, indice
    if tipo_dia == "dsr":
        assert _soma_minutos("dsr") == resultado.dsr_credito_minutos, indice

    # `minutos_equivalentes` de TODO componente e o arredondamento
    # documentado de `minutos * fator` -- verificado com uma
    # implementacao de arredondamento independente (nao importada).
    for componente in resultado.componentes:
        esperado = _arredondar_equivalente_independente(componente.minutos, componente.fator)
        assert componente.minutos_equivalentes == esperado, (indice, componente.codigo)
