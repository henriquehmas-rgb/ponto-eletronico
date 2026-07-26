import type { Meta, StoryObj } from "@storybook/nextjs";

import { GraficoDeArea, GraficoDeBarras, GraficoDeLinha, GraficoDePizza } from "./graficos";
import type { FatiaDePizza, SerieDeGrafico } from "./paleta";

const DADOS_MENSAIS = [
  { mes: "Jan", serie1: 40, serie2: 24, serie3: 18, serie4: 12, serie5: 30, serie6: 20, serie7: 8, serie8: 15 },
  { mes: "Fev", serie1: 35, serie2: 28, serie3: 20, serie4: 14, serie5: 25, serie6: 22, serie7: 10, serie8: 12 },
  { mes: "Mar", serie1: 42, serie2: 22, serie3: 24, serie4: 10, serie5: 28, serie6: 18, serie7: 12, serie8: 18 },
];

const OITO_SERIES: SerieDeGrafico[] = [
  { chave: "serie1", rotulo: "Unidade Centro" },
  { chave: "serie2", rotulo: "Unidade Norte" },
  { chave: "serie3", rotulo: "Unidade Sul" },
  { chave: "serie4", rotulo: "Unidade Leste" },
  { chave: "serie5", rotulo: "Unidade Oeste" },
  { chave: "serie6", rotulo: "Filial A" },
  { chave: "serie7", rotulo: "Filial B" },
  { chave: "serie8", rotulo: "Filial C" },
];

const meta: Meta = {
  title: "Gráficos/GráficosBase",
  parameters: { layout: "padded" },
};

export default meta;

export const Barras: StoryObj = {
  render: () => (
    <GraficoDeBarras dados={DADOS_MENSAIS} chaveCategoria="mes" series={OITO_SERIES} altura={360} />
  ),
};

export const Linha: StoryObj = {
  render: () => (
    <GraficoDeLinha dados={DADOS_MENSAIS} chaveCategoria="mes" series={OITO_SERIES} altura={360} />
  ),
};

export const Area: StoryObj = {
  render: () => (
    <GraficoDeArea dados={DADOS_MENSAIS} chaveCategoria="mes" series={OITO_SERIES} altura={360} />
  ),
};

export const Pizza: StoryObj = {
  render: () => {
    const fatias: FatiaDePizza[] = [
      { chave: "terminal", rotulo: "Terminal", valor: 420 },
      { chave: "mobile", rotulo: "Celular", valor: 260 },
      { chave: "web", rotulo: "Web", valor: 90 },
      { chave: "totem", rotulo: "Totem", valor: 55 },
    ];
    return <GraficoDePizza fatias={fatias} altura={360} />;
  },
};

export const OitoSeriesSimultaneas: StoryObj = {
  name: "8 séries simultâneas (limite da paleta)",
  render: () => (
    <GraficoDeLinha dados={DADOS_MENSAIS} chaveCategoria="mes" series={OITO_SERIES} altura={360} />
  ),
};

export const AgregacaoAcimaDeOitoSeries: StoryObj = {
  name: "Agregação em 'Outros' acima de 8 séries",
  render: () => {
    const dadosComDezSeries = DADOS_MENSAIS.map((linha) => ({ ...linha, serie9: 6, serie10: 4 }));
    const dezSeries: SerieDeGrafico[] = [
      ...OITO_SERIES,
      { chave: "serie9", rotulo: "Filial D" },
      { chave: "serie10", rotulo: "Filial E" },
    ];
    return (
      <GraficoDeBarras dados={dadosComDezSeries} chaveCategoria="mes" series={dezSeries} altura={360} />
    );
  },
};
