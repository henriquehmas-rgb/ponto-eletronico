"use client";

import dynamic from "next/dynamic";
import { useState } from "react";

import { mensagemDeErroApi } from "@/componentes/paineis/cadastros/_shared/erro-amigavel";
import type { GeocercaValor, GeoJsonPoligono } from "@/componentes/paineis/mapa/mapa-de-geocerca";
import { Alerta, AlertaDescricao } from "@/componentes/ui/alert";
import { Botao } from "@/componentes/ui/button";
import { CaixaDeSelecao } from "@/componentes/ui/checkbox";
import { Entrada } from "@/componentes/ui/input";
import { Rotulo } from "@/componentes/ui/label";
import { useAtualizarUnidade } from "@/ganchos/use-unidades";
import type { Esquema } from "@/lib/api";

// Leaflet toca `window` ao montar o mapa — carregado só no cliente, nunca no
// pré-render do servidor (T5, mesmo padrão de qualquer widget baseado em DOM
// do navegador que este projeto já usa para captura de mídia).
const MapaDeGeocerca = dynamic(
  () => import("@/componentes/paineis/mapa/mapa-de-geocerca").then((m) => m.MapaDeGeocerca),
  {
    ssr: false,
    loading: () => (
      <div className="h-[360px] w-full rounded-medio border border-borda-sutil bg-fundo-sutil" />
    ),
  },
);

function valorInicialDeGeocerca(unidade: Esquema<"Unidade">): GeocercaValor {
  if (unidade.geocercaPoligono && Object.keys(unidade.geocercaPoligono).length > 0) {
    return { tipo: "poligonal", poligono: unidade.geocercaPoligono as unknown as GeoJsonPoligono };
  }
  if (
    unidade.geocercaLatitude != null &&
    unidade.geocercaLongitude != null &&
    unidade.geocercaRaioMetros != null
  ) {
    return {
      tipo: "circular",
      latitude: unidade.geocercaLatitude,
      longitude: unidade.geocercaLongitude,
      raioMetros: unidade.geocercaRaioMetros,
    };
  }
  return { tipo: "nenhuma" };
}

interface SecaoGeocercaProps {
  unidade: Esquema<"Unidade">;
}

/**
 * Geocerca de uma unidade já existente (T5). Salva independente do resto do
 * cadastro (`PATCH /v1/unidades/{id}`, atualização parcial) — o campo de
 * geocerca "não bloqueia o resto do formulário" (T4/pronto-quando do PCF).
 */
export function SecaoGeocerca({ unidade }: SecaoGeocercaProps) {
  const [geocerca, setGeocerca] = useState<GeocercaValor>(() => valorInicialDeGeocerca(unidade));
  const [obrigatoria, setObrigatoria] = useState(unidade.geocercaObrigatoria ?? true);
  const [toleranciaMetros, setToleranciaMetros] = useState(
    unidade.geocercaToleranciaMetros != null ? String(unidade.geocercaToleranciaMetros) : "0",
  );
  const atualizar = useAtualizarUnidade();

  function salvar() {
    if (!unidade.id) return;
    const corpo: Esquema<"UnidadeAtualizar"> = {
      geocercaObrigatoria: obrigatoria,
      geocercaToleranciaMetros: Number(toleranciaMetros) || 0,
    };
    if (geocerca.tipo === "circular") {
      corpo.geocercaLatitude = geocerca.latitude;
      corpo.geocercaLongitude = geocerca.longitude;
      corpo.geocercaRaioMetros = geocerca.raioMetros;
    } else if (geocerca.tipo === "poligonal") {
      corpo.geocercaPoligono = geocerca.poligono as unknown as Record<string, unknown>;
    }
    atualizar.mutate({ id: unidade.id, corpo });
  }

  return (
    <div className="flex flex-col gap-4">
      <p className="estilo-legenda text-texto-secundario">
        Desenhe um círculo ou um polígono no mapa (barra de ferramentas no canto superior direito).
        Um novo desenho substitui o anterior — a unidade tem uma única geocerca.
      </p>
      <MapaDeGeocerca key={unidade.id} valor={geocerca} aoMudar={setGeocerca} />

      <div className="flex flex-wrap items-end gap-4">
        <label htmlFor="geocerca-obrigatoria" className="flex cursor-pointer items-center gap-2">
          <CaixaDeSelecao
            id="geocerca-obrigatoria"
            checked={obrigatoria}
            onCheckedChange={(valor) => {
              setObrigatoria(valor === true);
            }}
          />
          <span className="estilo-corpo text-texto-primario">Geocerca obrigatória</span>
        </label>
        <div className="flex flex-col gap-1">
          <Rotulo htmlFor="geocerca-tolerancia">Tolerância (metros)</Rotulo>
          <Entrada
            id="geocerca-tolerancia"
            type="number"
            min={0}
            className="w-32"
            value={toleranciaMetros}
            onChange={(evento) => {
              setToleranciaMetros(evento.target.value);
            }}
          />
        </div>
      </div>

      {atualizar.isError ? (
        <Alerta variant="erro">
          <AlertaDescricao>{mensagemDeErroApi(atualizar.error)}</AlertaDescricao>
        </Alerta>
      ) : null}
      {atualizar.isSuccess ? (
        <Alerta variant="sucesso">
          <AlertaDescricao>Geocerca salva.</AlertaDescricao>
        </Alerta>
      ) : null}

      <div className="flex justify-end">
        <Botao onClick={salvar} disabled={atualizar.isPending || geocerca.tipo === "nenhuma"}>
          {atualizar.isPending ? "Salvando…" : "Salvar geocerca"}
        </Botao>
      </div>
    </div>
  );
}
