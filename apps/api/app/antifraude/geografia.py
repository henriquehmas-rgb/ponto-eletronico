"""Coerencia geografica e velocidade implicita entre marcacoes (PCF F14 sec 5, A1).

`marcacoes_meta.velocidade_desde_ultima_kmh` existe desde a Fase 0 (F5) mas
nunca foi calculado: o pipeline gravava a coluna sempre `NULL`. Este modulo
calcula o valor de verdade, buscando a marcacao anterior do MESMO colaborador
que tenha posicao registrada, e devolve tanto a velocidade quanto o
"aviso de deslocamento impossivel" que alimenta o motor de composicao
(`app.antifraude.motor`).

Reaproveita `app.organizacao.geocerca._haversine_metros`... na verdade essa
funcao e privada daquele modulo (prefixo `_`), entao esta funcao tem sua
propria copia da formula de haversine -- duplicacao deliberada de uma formula
de ~5 linhas em vez de expor uma funcao privada de outro modulo (mesmo
precedente de `worker/tarefas/importacoes.py` para validadores puros,
registrado em `docs/backlog.md`, 2026-07-26, F6/A2).
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass
from uuid import UUID

import sqlalchemy as sa
from ponto_contracts import Marcacao, MarcacaoMeta
from sqlalchemy.ext.asyncio import AsyncSession

_RAIO_TERRA_METROS = 6_371_000.0

#: Velocidade acima da qual o deslocamento entre duas marcacoes consecutivas
#: do MESMO colaborador e fisicamente implausivel para qualquer meio de
#: transporte civil comum (a velocidade de cruzeiro de um voo comercial gira
#: em torno de 900 km/h; a folga ate 1000 km/h absorve GPS ruidoso perto de
#: aeroportos sem exigir dado de voo real, que este sistema nao tem). Decisao
#: de produto documentada aqui (mesmo padrao de `JANELA_REAUTENTICACAO` em
#: `marcacao/pipeline/ingestao.py`): se um dia precisar ser configuravel por
#: tenant, e achado de backlog, nao invencao silenciosa nesta constante.
VELOCIDADE_IMPOSSIVEL_KMH = 1000.0

#: Teto de armazenamento: `marcacoes_meta.velocidade_desde_ultima_kmh` e
#: `NUMERIC(8,2)` (schema.sql, Fase 0) -- o Postgres rejeita qualquer valor
#: cujo modulo nao caiba em 6 digitos inteiros (`NumericValueOutOfRangeError`,
#: achado real ao rodar `tests/f14/antifraude/
#: test_velocidade_impossivel_entre_marcacoes_consecutivas_aciona_revisao`
#: contra Postgres real: duas marcacoes de teste, sem sleep entre elas,
#: produzem `delta_horas` da ordem de milissegundos e uma velocidade
#: numericamente enorme). O CLAMP so afeta o numero gravado -- a
#: classificacao "impossivel" (`VELOCIDADE_IMPOSSIVEL_KMH`) e decidida ANTES
#: do clamp, contra o valor real, entao a distincao entre "muito rapido" e
#: "impossivelmente rapido" nunca se perde.
_VELOCIDADE_MAXIMA_ARMAZENAVEL_KMH = 999_999.0


@dataclass(frozen=True, slots=True)
class SinalDeslocamento:
    velocidade_kmh: float | None
    """`None` quando nao ha marcacao anterior com posicao para comparar
    (primeira marcacao do dia/do colaborador, ou anterior sem lat/long) --
    nao aplicavel, nunca um valor inventado."""
    impossivel: bool
    """`True` quando `velocidade_kmh` excede `VELOCIDADE_IMPOSSIVEL_KMH`."""


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    f1, f2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(f1) * math.cos(f2) * math.sin(dlambda / 2) ** 2
    return (2 * _RAIO_TERRA_METROS * math.asin(math.sqrt(min(1.0, a)))) / 1000.0


async def calcular_deslocamento(
    sessao: AsyncSession,
    *,
    tenant_id: UUID,
    colaborador_id: UUID | None,
    datahora_atual: dt.datetime,
    latitude_atual: float | None,
    longitude_atual: float | None,
) -> SinalDeslocamento:
    """Velocidade implicita entre a marcacao atual e a anterior do MESMO
    colaborador que tenha latitude/longitude registrada.

    So consulta o banco quando ha posicao atual e colaborador conhecido --
    do contrario devolve "nao aplicavel" sem round-trip.
    """
    if colaborador_id is None or latitude_atual is None or longitude_atual is None:
        return SinalDeslocamento(velocidade_kmh=None, impossivel=False)

    consulta = (
        sa.select(Marcacao.datahora_marcacao, MarcacaoMeta.latitude, MarcacaoMeta.longitude)
        .join(
            MarcacaoMeta,
            sa.and_(MarcacaoMeta.marcacao_id == Marcacao.id, MarcacaoMeta.tenant_id == tenant_id),
        )
        .where(
            Marcacao.tenant_id == tenant_id,
            Marcacao.colaborador_id == colaborador_id,
            Marcacao.datahora_marcacao < datahora_atual,
            MarcacaoMeta.latitude.is_not(None),
            MarcacaoMeta.longitude.is_not(None),
        )
        .order_by(Marcacao.datahora_marcacao.desc())
        .limit(1)
    )
    linha = (await sessao.execute(consulta)).first()
    if linha is None:
        return SinalDeslocamento(velocidade_kmh=None, impossivel=False)

    datahora_anterior, lat_anterior, lon_anterior = linha
    delta_horas = (datahora_atual - datahora_anterior).total_seconds() / 3600.0
    if delta_horas <= 0:
        # Relogio do servidor nao deveria produzir isto (carimba sempre
        # `now()`), mas o fluxo offline preserva o instante real da captura
        # (T7, `pipeline/offline.py`) -- um item fora de ordem por
        # dessincronizacao de relogio de aparelho e sinal de risco, nao
        # divisao por zero: trata como velocidade "impossivel" sem tentar
        # calcular um numero sem sentido.
        return SinalDeslocamento(velocidade_kmh=None, impossivel=True)

    distancia_km = _haversine_km(
        float(lat_anterior), float(lon_anterior), latitude_atual, longitude_atual
    )
    velocidade_kmh = distancia_km / delta_horas
    # Classificacao contra o valor REAL (antes do clamp) -- ver comentario de
    # `_VELOCIDADE_MAXIMA_ARMAZENAVEL_KMH`.
    impossivel = velocidade_kmh > VELOCIDADE_IMPOSSIVEL_KMH
    velocidade_kmh_armazenavel = min(velocidade_kmh, _VELOCIDADE_MAXIMA_ARMAZENAVEL_KMH)
    return SinalDeslocamento(velocidade_kmh=velocidade_kmh_armazenavel, impossivel=impossivel)
