"""Pertencimento de um ponto GPS a geocerca de uma unidade.

Duas formas de geocerca, tratadas de forma independente (`unidades` aceita as
duas ao mesmo tempo; quando o poligono esta presente, ele tem precedencia
sobre o circulo -- ver `packages/contracts/schema.sql`, comentario de
`unidades.geocerca_poligono`):

* **Ponto + raio.** Distancia geodesica (formula de haversine) entre o ponto
  recebido e o centro da geocerca, comparada a `raio + tolerancia`.
* **Poligono.** GeoJSON `Polygon`/`MultiPolygon` em `geocerca_poligono`.
  Pertencimento por *ray casting* (funciona para poligono concavo e convexo
  igualmente; vertice inicial repetido no fim do anel -- convencao comum do
  GeoJSON -- produz uma aresta degenerada que o algoritmo ignora sozinho,
  sem tratamento especial). Quando o ponto cai fora, a tolerancia e aplicada
  como distancia minima ate a borda do poligono (projecao local equiretangular,
  precisa o suficiente para as dezenas de metros que uma geocerca urbana usa).

Este modulo e puro (nenhum acesso a banco): a F7 e a F8 chamam
`dentro_da_geocerca` no momento de bater ponto. Aqui a fase F2 so entrega e
testa a funcao.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

RAIO_TERRA_METROS = 6_371_000.0

#: Limiar documentado para PONTO-GEO-002 (precisao de localizacao
#: insuficiente): quando o GPS informa uma precisao (`precisao_m`, o raio de
#: incerteza devolvido pela API de localizacao do sistema operacional) maior
#: que este multiplo da tolerancia da unidade, a leitura e ruim demais para a
#: decisao "dentro/fora" ser confiavel -- decisao de aplicacao da F2,
#: registrada aqui e em `docs/backlog.md` por nao haver formula fechada no
#: contrato.
FATOR_PRECISAO_INSUFICIENTE = 3.0


@dataclass(frozen=True, slots=True)
class GeocercaUnidade:
    """Os campos de geocerca de uma unidade, desacoplados do model do ORM."""

    geocerca_latitude: float | None = None
    geocerca_longitude: float | None = None
    geocerca_raio_metros: int | None = None
    geocerca_poligono: dict[str, Any] | None = None
    geocerca_obrigatoria: bool = True
    geocerca_tolerancia_metros: int = 50


@dataclass(frozen=True, slots=True)
class ResultadoGeocerca:
    """Resultado do teste de pertencimento."""

    tem_geocerca: bool
    dentro: bool
    """Dentro da forma (circulo ou poligono), ja considerando a tolerancia."""
    distancia_metros: float | None
    """Distancia ate a borda mais proxima. 0.0 quando o ponto esta dentro da
    forma "dura" (antes de aplicar a tolerancia). `None` quando nao ha
    geocerca cadastrada."""
    precisao_insuficiente: bool
    """`True` quando `precisao_m` e grande demais para confiar no resultado."""
    aceitar: bool
    """Decisao final: dentro (com tolerancia) OU geocerca nao obrigatoria."""


def _haversine_metros(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distancia geodesica entre dois pontos em graus decimais WGS84."""
    f1, f2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(f1) * math.cos(f2) * math.sin(dlambda / 2) ** 2
    return 2 * RAIO_TERRA_METROS * math.asin(math.sqrt(min(1.0, a)))


def _anel_para_metros(
    anel: list[list[float]], lat_origem: float, lon_origem: float
) -> list[tuple[float, float]]:
    """Projeta um anel de coordenadas GeoJSON `[lon, lat]` num plano local em
    metros, centrado em `(lat_origem, lon_origem)` (projecao equiretangular:
    precisa o bastante para as dezenas/centenas de metros de uma geocerca)."""
    cos_lat = math.cos(math.radians(lat_origem))
    pontos = []
    for lon, lat in anel:
        x = math.radians(lon - lon_origem) * cos_lat * RAIO_TERRA_METROS
        y = math.radians(lat - lat_origem) * RAIO_TERRA_METROS
        pontos.append((x, y))
    return pontos


def _distancia_ponto_segmento(
    px: float, py: float, ax: float, ay: float, bx: float, by: float
) -> float:
    """Distancia (em metros, no plano local ja projetado) de `(px,py)` ao
    segmento `[(ax,ay),(bx,by)]`."""
    dx, dy = bx - ax, by - ay
    comprimento_quadrado = dx * dx + dy * dy
    if comprimento_quadrado == 0.0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / comprimento_quadrado))
    projecao_x, projecao_y = ax + t * dx, ay + t * dy
    return math.hypot(px - projecao_x, py - projecao_y)


def _aneis_do_poligono(geometria: dict[str, Any]) -> list[list[list[float]]]:
    """Extrai os aneis externos de um `Polygon` ou `MultiPolygon` GeoJSON.

    Buracos internos (aneis a partir do segundo, em `Polygon`, ou dentro de
    cada elemento de `MultiPolygon`) nao ocorrem no cadastro de unidade desta
    fase (uma unidade nao tem geocerca com buraco); so o anel externo de cada
    poligono e considerado.
    """
    tipo = geometria.get("type")
    coordenadas = geometria.get("coordinates") or []
    if tipo == "Polygon":
        return [coordenadas[0]] if coordenadas else []
    if tipo == "MultiPolygon":
        return [poligono[0] for poligono in coordenadas if poligono]
    return []


def _ponto_dentro_do_anel(lat: float, lon: float, anel: list[list[float]]) -> bool:
    """*Ray casting* padrao (algoritmo de Jordan). `anel` e uma lista de
    `[longitude, latitude]`. Funciona para poligono concavo e convexo, e o
    vertice inicial repetido no fim (fechamento comum do GeoJSON) produz uma
    aresta de comprimento zero que nunca cruza o raio -- nao exige tratamento
    especial."""
    dentro = False
    quantidade = len(anel)
    if quantidade < 3:
        return False
    j = quantidade - 1
    for i in range(quantidade):
        xi, yi = anel[i][0], anel[i][1]
        xj, yj = anel[j][0], anel[j][1]
        intercepta = ((yi > lat) != (yj > lat)) and (lon < (xj - xi) * (lat - yi) / (yj - yi) + xi)
        if intercepta:
            dentro = not dentro
        j = i
    return dentro


def _distancia_ate_poligono_metros(lat: float, lon: float, anel: list[list[float]]) -> float:
    """Menor distancia (metros) do ponto ate a borda do anel, projetando tudo
    num plano local centrado no proprio ponto."""
    pontos = _anel_para_metros(anel, lat_origem=lat, lon_origem=lon)
    menor = math.inf
    quantidade = len(pontos)
    for i in range(quantidade):
        ax, ay = pontos[i]
        bx, by = pontos[(i + 1) % quantidade]
        menor = min(menor, _distancia_ponto_segmento(0.0, 0.0, ax, ay, bx, by))
    return menor


def dentro_da_geocerca(
    unidade: GeocercaUnidade,
    latitude: float,
    longitude: float,
    precisao_m: float | None = None,
) -> ResultadoGeocerca:
    """Testa se `(latitude, longitude)` esta dentro da geocerca da unidade.

    Poligono tem precedencia sobre ponto+raio quando os dois estao presentes.
    Unidade sem nenhuma geocerca cadastrada devolve `tem_geocerca=False` e
    `aceitar=True` (nao ha o que verificar).
    """
    precisao_insuficiente = (
        precisao_m is not None
        and precisao_m > unidade.geocerca_tolerancia_metros * FATOR_PRECISAO_INSUFICIENTE
    )

    if unidade.geocerca_poligono is not None:
        aneis = _aneis_do_poligono(unidade.geocerca_poligono)
        dentro_duro = any(_ponto_dentro_do_anel(latitude, longitude, anel) for anel in aneis)
        if dentro_duro:
            distancia = 0.0
        else:
            distancia = min(
                (_distancia_ate_poligono_metros(latitude, longitude, anel) for anel in aneis),
                default=math.inf,
            )
        dentro = dentro_duro or distancia <= unidade.geocerca_tolerancia_metros
        aceitar = dentro or not unidade.geocerca_obrigatoria
        return ResultadoGeocerca(
            tem_geocerca=True,
            dentro=dentro,
            distancia_metros=distancia,
            precisao_insuficiente=precisao_insuficiente,
            aceitar=aceitar,
        )

    if (
        unidade.geocerca_latitude is not None
        and unidade.geocerca_longitude is not None
        and unidade.geocerca_raio_metros is not None
    ):
        distancia_ao_centro = _haversine_metros(
            latitude, longitude, unidade.geocerca_latitude, unidade.geocerca_longitude
        )
        limite = unidade.geocerca_raio_metros + unidade.geocerca_tolerancia_metros
        distancia_a_borda = max(0.0, distancia_ao_centro - unidade.geocerca_raio_metros)
        dentro = distancia_ao_centro <= limite
        aceitar = dentro or not unidade.geocerca_obrigatoria
        return ResultadoGeocerca(
            tem_geocerca=True,
            dentro=dentro,
            distancia_metros=distancia_a_borda,
            precisao_insuficiente=precisao_insuficiente,
            aceitar=aceitar,
        )

    return ResultadoGeocerca(
        tem_geocerca=False,
        dentro=True,
        distancia_metros=None,
        precisao_insuficiente=precisao_insuficiente,
        aceitar=True,
    )
