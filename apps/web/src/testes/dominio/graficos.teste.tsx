import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { render } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";

import {
  GraficoDeArea,
  GraficoDeBarras,
  GraficoDeLinha,
  GraficoDePizza,
} from "@/componentes/graficos/graficos";
import {
  agregarFatiasAcimaDoLimite,
  agregarSeriesAcimaDoLimite,
  type FatiaDePizza,
  type SerieDeGrafico,
} from "@/componentes/graficos/paleta";

/**
 * Recharts (`ResponsiveContainer`) também depende de medida de layout real —
 * ausente no jsdom — e, diferente do `@tanstack/react-virtual`, exige que
 * `ResizeObserver` exista de verdade (não faz fallback silencioso).
 */
class ResizeObserverForjado {
  private aoRedimensionar: ResizeObserverCallback;

  constructor(aoRedimensionar: ResizeObserverCallback) {
    this.aoRedimensionar = aoRedimensionar;
  }

  observe(alvo: Element) {
    // O ResizeObserver de verdade chama o callback uma vez, de imediato, com
    // o tamanho atual — e disso que o ResponsiveContainer do recharts
    // depende para saber a largura/altura antes de desenhar o SVG.
    const entrada = {
      target: alvo,
      contentRect: { width: (alvo as HTMLElement).offsetWidth, height: (alvo as HTMLElement).offsetHeight },
    } as ResizeObserverEntry;
    this.aoRedimensionar([entrada], this as unknown as ResizeObserver);
  }

  unobserve() {}
  disconnect() {}
}

beforeAll(() => {
  vi.stubGlobal("ResizeObserver", ResizeObserverForjado);
  Object.defineProperty(HTMLElement.prototype, "offsetHeight", {
    configurable: true,
    value: 320,
  });
  Object.defineProperty(HTMLElement.prototype, "offsetWidth", {
    configurable: true,
    value: 640,
  });
});

const DADOS_MENSAIS = [
  { mes: "Jan", serie1: 10, serie2: 20, serie3: 5 },
  { mes: "Fev", serie1: 15, serie2: 18, serie3: 8 },
];

const SERIES_TRES: SerieDeGrafico[] = [
  { chave: "serie1", rotulo: "Normais" },
  { chave: "serie2", rotulo: "Extras" },
  { chave: "serie3", rotulo: "Noturno" },
];

describe("componentes de grafico — renderizacao basica", () => {
  it("renderiza GraficoDeBarras sem lancar erro", () => {
    const { container } = render(
      <GraficoDeBarras dados={DADOS_MENSAIS} chaveCategoria="mes" series={SERIES_TRES} />,
    );
    expect(container.querySelector("svg")).toBeInTheDocument();
  });

  it("renderiza GraficoDeLinha sem lancar erro", () => {
    const { container } = render(
      <GraficoDeLinha dados={DADOS_MENSAIS} chaveCategoria="mes" series={SERIES_TRES} />,
    );
    expect(container.querySelector("svg")).toBeInTheDocument();
  });

  it("renderiza GraficoDeArea sem lancar erro", () => {
    const { container } = render(
      <GraficoDeArea dados={DADOS_MENSAIS} chaveCategoria="mes" series={SERIES_TRES} />,
    );
    expect(container.querySelector("svg")).toBeInTheDocument();
  });

  it("renderiza GraficoDePizza sem lancar erro", () => {
    const fatias: FatiaDePizza[] = [
      { chave: "a", rotulo: "Terminal", valor: 40 },
      { chave: "b", rotulo: "Mobile", valor: 60 },
    ];
    const { container } = render(<GraficoDePizza fatias={fatias} />);
    expect(container.querySelector("svg")).toBeInTheDocument();
  });
});

describe("agregarSeriesAcimaDoLimite", () => {
  it("nao mexe quando ha 8 series ou menos", () => {
    const series: SerieDeGrafico[] = Array.from({ length: 8 }, (_valor, indice) => ({
      chave: `s${indice}`,
      rotulo: `Serie ${indice}`,
    }));
    const dados = [Object.fromEntries(series.map((serie) => [serie.chave, 1]))];
    const resultado = agregarSeriesAcimaDoLimite(dados, series);
    expect(resultado.series).toHaveLength(8);
    expect(resultado.series.map((serie) => serie.chave)).not.toContain("outros");
  });

  it("agrega o excedente em 'Outros' quando ha mais de 8 series", () => {
    const series: SerieDeGrafico[] = Array.from({ length: 10 }, (_valor, indice) => ({
      chave: `s${indice}`,
      rotulo: `Serie ${indice}`,
    }));
    const dados = [Object.fromEntries(series.map((serie) => [serie.chave, 10]))];
    const resultado = agregarSeriesAcimaDoLimite(dados, series);

    expect(resultado.series).toHaveLength(8);
    const ultima = resultado.series.at(-1);
    expect(ultima).toEqual({ chave: "outros", rotulo: "Outros" });
    // s7, s8, s9 (3 series excedentes) somam 30 no bucket "outros".
    expect(resultado.dados[0]?.outros).toBe(30);
  });
});

describe("agregarFatiasAcimaDoLimite", () => {
  it("agrega fatias excedentes de pizza em 'Outros'", () => {
    const fatias: FatiaDePizza[] = Array.from({ length: 9 }, (_valor, indice) => ({
      chave: `f${indice}`,
      rotulo: `Fatia ${indice}`,
      valor: 10,
    }));
    const resultado = agregarFatiasAcimaDoLimite(fatias);
    expect(resultado).toHaveLength(8);
    expect(resultado.at(-1)).toEqual({ chave: "outros", rotulo: "Outros", valor: 20 });
  });
});

describe("nenhuma cor de serie e escrita literalmente no codigo", () => {
  const REGEX_HEX = /#[0-9A-Fa-f]{3,8}\b/;
  const arquivos = [
    "src/componentes/graficos/paleta.ts",
    "src/componentes/graficos/graficos.tsx",
    "src/componentes/graficos/marcador-de-forma.tsx",
  ];

  it.each(arquivos)("%s nao contem hexadecimal literal de cor", (caminhoRelativo) => {
    const conteudo = readFileSync(resolve(process.cwd(), caminhoRelativo), "utf-8");
    expect(REGEX_HEX.test(conteudo)).toBe(false);
  });

  it("as series usam somente var(--cor-grafico-serieN)", () => {
    const conteudo = readFileSync(resolve(process.cwd(), "src/componentes/graficos/paleta.ts"), "utf-8");
    const cores = conteudo.match(/var\(--cor-grafico-serie\d\)/g) ?? [];
    expect(cores.length).toBe(8);
  });
});
