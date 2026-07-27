"use client";

import "leaflet/dist/leaflet.css";
import "leaflet-draw/dist/leaflet.draw.css";

import * as L from "leaflet";
// Efeito colateral: estende `L` com `L.Control.Draw`/`L.Draw.Event` — mesma
// instância de `leaflet` importada acima (resolução de módulo do Node/bundler
// garante isso), então a extensão fica visível no `L` usado neste arquivo.
import "leaflet-draw";
import { useEffect, useRef } from "react";
import { MapContainer, TileLayer, useMap } from "react-leaflet";

/**
 * `MapaDeGeocerca` — T5.
 *
 * Encapsula `leaflet` + `react-leaflet` (decisão fixada no PCF §2) com
 * `leaflet-draw` para desenhar/editar a geocerca circular ou poligonal de
 * uma unidade, refletindo exatamente os dois formatos que o contrato usa
 * (`Unidade.geocercaLatitude/Longitude/RaioMetros` e `geocercaPoligono`
 * GeoJSON `Polygon`/`MultiPolygon`, poligono com precedência). Sem chave de
 * API nem custo por tenant — tiles do servidor público do OpenStreetMap
 * (produção fica para F15, registrado em `docs/backlog.md`).
 *
 * Único desenho por vez: criar um novo apaga o anterior do grupo, porque o
 * contrato só guarda UMA geocerca por unidade — nunca "geocerca 1 e 2".
 *
 * z-index: todo empilhamento aqui vem do que o Leaflet já usa por padrão
 * (`camada.mapPane` etc., valores baixos, 200–700) — nenhum `z-index` literal
 * é escrito neste arquivo. A escala `camada` do contrato (`dialogo` = 900)
 * fica acima de qualquer parte do mapa sem precisar de ajuste manual.
 */

/** GeoJSON solto (`additionalProperties: true` no contrato) — só o suficiente para desenhar. */
export interface GeoJsonPoligono {
  type: "Polygon" | "MultiPolygon";
  coordinates: unknown;
}

export type GeocercaValor =
  | { tipo: "circular"; latitude: number; longitude: number; raioMetros: number }
  | { tipo: "poligonal"; poligono: GeoJsonPoligono }
  | { tipo: "nenhuma" };

interface MapaDeGeocercaProps {
  valor: GeocercaValor;
  aoMudar: (valor: GeocercaValor) => void;
}

/** Ponto de partida do mapa quando ainda não há geocerca cadastrada (Brasília — não é um valor de domínio). */
const CENTRO_PADRAO: [number, number] = [-15.793889, -47.882778];
const ZOOM_PADRAO = 15;
const ZOOM_SEM_GEOCERCA = 4;

function emitirValorDaCamada(camada: L.Layer, aoMudar: (valor: GeocercaValor) => void): void {
  if (camada instanceof L.Circle) {
    const centro = camada.getLatLng();
    aoMudar({
      tipo: "circular",
      latitude: centro.lat,
      longitude: centro.lng,
      raioMetros: Math.round(camada.getRadius()),
    });
    return;
  }
  if (camada instanceof L.Polygon) {
    const geoJson = camada.toGeoJSON();
    aoMudar({ tipo: "poligonal", poligono: geoJson.geometry as GeoJsonPoligono });
  }
}

/** Componente interno: só monta os controles de desenho sobre o `map` já criado pelo `MapContainer`. */
function ControleDeDesenho({ valor, aoMudar }: MapaDeGeocercaProps) {
  const map = useMap();
  const valorInicialRef = useRef(valor);

  useEffect(() => {
    const grupo = new L.FeatureGroup();
    map.addLayer(grupo);

    const valorInicial = valorInicialRef.current;
    if (valorInicial.tipo === "circular") {
      const circulo = L.circle([valorInicial.latitude, valorInicial.longitude], {
        radius: valorInicial.raioMetros,
      });
      grupo.addLayer(circulo);
      map.fitBounds(circulo.getBounds());
    } else if (valorInicial.tipo === "poligonal") {
      const camadaGeoJson = L.geoJSON(valorInicial.poligono as unknown as GeoJSON.GeoJsonObject);
      camadaGeoJson.eachLayer((camada) => grupo.addLayer(camada));
      const limites = camadaGeoJson.getBounds();
      if (limites.isValid()) map.fitBounds(limites);
    }

    const controle = new L.Control.Draw({
      position: "topright",
      draw: {
        polyline: false,
        rectangle: false,
        marker: false,
        circlemarker: false,
        polygon: { showArea: false, allowIntersection: false },
        circle: { showRadius: true, metric: true },
      },
      edit: { featureGroup: grupo, remove: true },
    });
    map.addControl(controle);

    function aoDesenhar(evento: L.LeafletEvent): void {
      const criado = evento as L.DrawEvents.Created;
      // Só uma geocerca por unidade: o novo desenho substitui o anterior.
      grupo.clearLayers();
      grupo.addLayer(criado.layer);
      emitirValorDaCamada(criado.layer, aoMudar);
    }

    function aoEditar(evento: L.LeafletEvent): void {
      const editado = evento as L.DrawEvents.Edited;
      editado.layers.eachLayer((camada) => {
        emitirValorDaCamada(camada, aoMudar);
      });
    }

    function aoApagar(): void {
      aoMudar({ tipo: "nenhuma" });
    }

    map.on(L.Draw.Event.CREATED, aoDesenhar);
    map.on(L.Draw.Event.EDITED, aoEditar);
    map.on(L.Draw.Event.DELETED, aoApagar);

    return () => {
      map.off(L.Draw.Event.CREATED, aoDesenhar);
      map.off(L.Draw.Event.EDITED, aoEditar);
      map.off(L.Draw.Event.DELETED, aoApagar);
      map.removeControl(controle);
      map.removeLayer(grupo);
    };
    // Só depende de `map`/`aoMudar`: o valor inicial vem de `valorInicialRef`
    // (ref, não reativo por natureza) — reagir a mudanças de `valor` vindas do
    // próprio desenho criaria um laço. Trocar de registro (outra unidade)
    // recria o mapa inteiro via `key` no componente pai.
  }, [map, aoMudar]);

  return null;
}

export function MapaDeGeocerca({ valor, aoMudar }: MapaDeGeocercaProps) {
  const centro: [number, number] =
    valor.tipo === "circular" ? [valor.latitude, valor.longitude] : CENTRO_PADRAO;
  const zoom = valor.tipo === "nenhuma" ? ZOOM_SEM_GEOCERCA : ZOOM_PADRAO;

  return (
    <div className="h-[360px] w-full overflow-hidden rounded-medio border border-borda-padrao">
      <MapContainer center={centro} zoom={zoom} style={{ height: "100%", width: "100%" }}>
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <ControleDeDesenho valor={valor} aoMudar={aoMudar} />
      </MapContainer>
    </div>
  );
}
