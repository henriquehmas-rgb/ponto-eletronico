"""T3 -- casos de mesa da geocerca: ponto+raio e poligono, incluindo poligono
concavo, vertice inicial repetido, ponto na borda e ponto dentro da
tolerancia. Nenhum teste aqui toca o banco: `dentro_da_geocerca` e pura.
"""

from __future__ import annotations

import math

from app.organizacao.geocerca import GeocercaUnidade, dentro_da_geocerca

# Av. Paulista, 1000 aproximadamente.
_LAT_CENTRO = -23.5613
_LON_CENTRO = -46.6558


def _unidade_ponto_raio(
    raio: int = 100, tolerancia: int = 50, obrigatoria: bool = True
) -> GeocercaUnidade:
    return GeocercaUnidade(
        geocerca_latitude=_LAT_CENTRO,
        geocerca_longitude=_LON_CENTRO,
        geocerca_raio_metros=raio,
        geocerca_obrigatoria=obrigatoria,
        geocerca_tolerancia_metros=tolerancia,
    )


class TestPontoMaisRaio:
    def test_ponto_exatamente_no_centro_esta_dentro(self) -> None:
        resultado = dentro_da_geocerca(_unidade_ponto_raio(), _LAT_CENTRO, _LON_CENTRO)
        assert resultado.dentro is True
        assert resultado.aceitar is True
        assert resultado.distancia_metros == 0.0

    def test_ponto_a_1km_esta_fora(self) -> None:
        # ~1km ao norte (0.009 graus de latitude ~= 1km).
        resultado = dentro_da_geocerca(_unidade_ponto_raio(), _LAT_CENTRO + 0.009, _LON_CENTRO)
        assert resultado.dentro is False
        assert resultado.aceitar is False

    def test_ponto_dentro_da_tolerancia_e_aceito(self) -> None:
        # Raio 100m + tolerancia 50m = 150m. ~120m de deslocamento em latitude.
        deslocamento_graus = 120 / 111_320  # ~1 grau de latitude = 111.32km
        resultado = dentro_da_geocerca(
            _unidade_ponto_raio(raio=100, tolerancia=50),
            _LAT_CENTRO + deslocamento_graus,
            _LON_CENTRO,
        )
        assert resultado.dentro is True
        assert resultado.aceitar is True

    def test_ponto_fora_da_tolerancia_e_recusado(self) -> None:
        deslocamento_graus = 200 / 111_320
        resultado = dentro_da_geocerca(
            _unidade_ponto_raio(raio=100, tolerancia=50),
            _LAT_CENTRO + deslocamento_graus,
            _LON_CENTRO,
        )
        assert resultado.dentro is False

    def test_geocerca_nao_obrigatoria_aceita_ponto_fora(self) -> None:
        resultado = dentro_da_geocerca(
            _unidade_ponto_raio(obrigatoria=False), _LAT_CENTRO + 0.02, _LON_CENTRO
        )
        assert resultado.dentro is False
        assert resultado.aceitar is True

    def test_precisao_insuficiente_e_sinalizada(self) -> None:
        resultado = dentro_da_geocerca(
            _unidade_ponto_raio(tolerancia=50), _LAT_CENTRO, _LON_CENTRO, precisao_m=200
        )
        assert resultado.precisao_insuficiente is True

    def test_precisao_boa_nao_e_sinalizada(self) -> None:
        resultado = dentro_da_geocerca(
            _unidade_ponto_raio(tolerancia=50), _LAT_CENTRO, _LON_CENTRO, precisao_m=20
        )
        assert resultado.precisao_insuficiente is False

    def test_sem_geocerca_cadastrada_aceita_qualquer_ponto(self) -> None:
        resultado = dentro_da_geocerca(GeocercaUnidade(), 0.0, 0.0)
        assert resultado.tem_geocerca is False
        assert resultado.aceitar is True


class TestPoligono:
    def _quadrado(self, tolerancia: int = 50) -> GeocercaUnidade:
        # Quadrado de ~200m de lado em volta do centro.
        delta_lat = 100 / 111_320
        delta_lon = 100 / (111_320 * math.cos(math.radians(_LAT_CENTRO)))
        return GeocercaUnidade(
            geocerca_poligono={
                "type": "Polygon",
                "coordinates": [
                    [
                        [_LON_CENTRO - delta_lon, _LAT_CENTRO - delta_lat],
                        [_LON_CENTRO + delta_lon, _LAT_CENTRO - delta_lat],
                        [_LON_CENTRO + delta_lon, _LAT_CENTRO + delta_lat],
                        [_LON_CENTRO - delta_lon, _LAT_CENTRO + delta_lat],
                        # Vertice inicial repetido no fim -- convencao GeoJSON.
                        [_LON_CENTRO - delta_lon, _LAT_CENTRO - delta_lat],
                    ]
                ],
            },
            geocerca_tolerancia_metros=tolerancia,
        )

    def test_ponto_no_centro_esta_dentro(self) -> None:
        unidade = self._quadrado()
        resultado = dentro_da_geocerca(unidade, _LAT_CENTRO, _LON_CENTRO)
        assert resultado.dentro is True
        assert resultado.distancia_metros == 0.0

    def test_ponto_bem_fora_e_recusado(self) -> None:
        unidade = self._quadrado()
        resultado = dentro_da_geocerca(unidade, _LAT_CENTRO + 0.05, _LON_CENTRO)
        assert resultado.dentro is False
        assert resultado.aceitar is False

    def test_ponto_dentro_da_tolerancia_da_borda_e_aceito(self) -> None:
        unidade = self._quadrado(tolerancia=50)
        # Um pouco alem da borda norte (100m do centro), dentro dos 50m de tolerancia.
        delta_lat_extra = 130 / 111_320
        resultado = dentro_da_geocerca(unidade, _LAT_CENTRO + delta_lat_extra, _LON_CENTRO)
        assert resultado.dentro is True

    def test_ponto_muito_alem_da_tolerancia_e_recusado(self) -> None:
        unidade = self._quadrado(tolerancia=50)
        delta_lat_extra = 300 / 111_320
        resultado = dentro_da_geocerca(unidade, _LAT_CENTRO + delta_lat_extra, _LON_CENTRO)
        assert resultado.dentro is False

    def test_poligono_concavo_forma_de_l(self) -> None:
        """Um poligono em L: o ponto no "reentrante" deve estar FORA mesmo
        estando dentro do retangulo delimitador (bounding box)."""
        # L: quadrado 0..10 menos o quadrado 5..10 x 5..10 (canto superior direito vazio).
        anel_l = [
            [0.0, 0.0],
            [10.0, 0.0],
            [10.0, 5.0],
            [5.0, 5.0],
            [5.0, 10.0],
            [0.0, 10.0],
            [0.0, 0.0],
        ]
        unidade = GeocercaUnidade(
            geocerca_poligono={"type": "Polygon", "coordinates": [anel_l]},
            geocerca_tolerancia_metros=0,
        )
        # (7, 7) esta no bounding box mas no "buraco" do L -> fora.
        resultado_fora = dentro_da_geocerca(unidade, 7.0, 7.0)
        assert resultado_fora.dentro is False
        # (2, 2) esta na perna do L -> dentro.
        resultado_dentro = dentro_da_geocerca(unidade, 2.0, 2.0)
        assert resultado_dentro.dentro is True

    def test_poligono_precede_ponto_mais_raio_quando_ambos_presentes(self) -> None:
        delta = 100 / 111_320
        unidade = GeocercaUnidade(
            geocerca_latitude=_LAT_CENTRO,
            geocerca_longitude=_LON_CENTRO,
            geocerca_raio_metros=10,  # raio bem pequeno
            geocerca_poligono={
                "type": "Polygon",
                "coordinates": [
                    [
                        [_LON_CENTRO - delta, _LAT_CENTRO - delta],
                        [_LON_CENTRO + delta, _LAT_CENTRO - delta],
                        [_LON_CENTRO + delta, _LAT_CENTRO + delta],
                        [_LON_CENTRO - delta, _LAT_CENTRO + delta],
                    ]
                ],
            },
            geocerca_tolerancia_metros=0,
        )
        # A ~50m do centro: fora do raio de 10m, mas dentro do poligono maior.
        resultado = dentro_da_geocerca(unidade, _LAT_CENTRO + 50 / 111_320, _LON_CENTRO)
        assert resultado.dentro is True
