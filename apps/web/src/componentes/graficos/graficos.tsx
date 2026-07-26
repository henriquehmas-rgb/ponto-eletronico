"use client";

import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { formaParaIndice, MarcadorDeForma } from "./marcador-de-forma";
import {
  agregarFatiasAcimaDoLimite,
  agregarSeriesAcimaDoLimite,
  COR_EIXO,
  COR_GRADE,
  COR_ROTULO,
  corDaSerie,
  type FatiaDePizza,
  type SerieDeGrafico,
} from "./paleta";

const ALTURA_PADRAO = 320;

const ESTILO_ROTULO_EIXO = { fill: COR_ROTULO, fontSize: 12 };

export interface GraficoDeCategoriaProps {
  /** Uma linha por ponto do eixo X (ex.: um dia, um mês), com uma propriedade por série. */
  dados: ReadonlyArray<Record<string, unknown>>;
  chaveCategoria: string;
  series: readonly SerieDeGrafico[];
  altura?: number;
  empilhado?: boolean;
}

/** Gráfico de barras. Séries acima de 8 são agregadas em "Outros" automaticamente. */
export function GraficoDeBarras({
  dados,
  chaveCategoria,
  series,
  altura = ALTURA_PADRAO,
  empilhado = false,
}: GraficoDeCategoriaProps) {
  const agregado = agregarSeriesAcimaDoLimite(dados, series);
  return (
    <ResponsiveContainer width="100%" height={altura}>
      <BarChart data={agregado.dados}>
        <CartesianGrid stroke={COR_GRADE} strokeDasharray="3 3" vertical={false} />
        <XAxis dataKey={chaveCategoria} stroke={COR_EIXO} tick={ESTILO_ROTULO_EIXO} />
        <YAxis stroke={COR_EIXO} tick={ESTILO_ROTULO_EIXO} />
        <Tooltip />
        <Legend />
        {agregado.series.map((serie, indice) => (
          <Bar
            key={serie.chave}
            dataKey={serie.chave}
            name={serie.rotulo}
            fill={corDaSerie(indice)}
            {...(empilhado ? { stackId: "pilha" } : {})}
          />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}

/**
 * Gráfico de linha. Cada série leva, além da cor, um marcador de ponto de
 * forma distinta — a cor nunca é o único jeito de diferenciar uma linha da
 * outra.
 */
export function GraficoDeLinha({
  dados,
  chaveCategoria,
  series,
  altura = ALTURA_PADRAO,
}: Omit<GraficoDeCategoriaProps, "empilhado">) {
  const agregado = agregarSeriesAcimaDoLimite(dados, series);
  return (
    <ResponsiveContainer width="100%" height={altura}>
      <LineChart data={agregado.dados}>
        <CartesianGrid stroke={COR_GRADE} strokeDasharray="3 3" vertical={false} />
        <XAxis dataKey={chaveCategoria} stroke={COR_EIXO} tick={ESTILO_ROTULO_EIXO} />
        <YAxis stroke={COR_EIXO} tick={ESTILO_ROTULO_EIXO} />
        <Tooltip />
        <Legend />
        {agregado.series.map((serie, indice) => {
          const cor = corDaSerie(indice);
          const forma = formaParaIndice(indice);
          return (
            <Line
              key={serie.chave}
              type="monotone"
              dataKey={serie.chave}
              name={serie.rotulo}
              stroke={cor}
              strokeWidth={2}
              dot={(propsDoPonto: { cx?: number; cy?: number }) => (
                <MarcadorDeForma
                  key={`${serie.chave}-${propsDoPonto.cx}-${propsDoPonto.cy}`}
                  cx={propsDoPonto.cx}
                  cy={propsDoPonto.cy}
                  forma={forma}
                  cor={cor}
                />
              )}
            />
          );
        })}
      </LineChart>
    </ResponsiveContainer>
  );
}

/** Gráfico de área, empilhado por padrão (comparação de composição ao longo do tempo). */
export function GraficoDeArea({
  dados,
  chaveCategoria,
  series,
  altura = ALTURA_PADRAO,
  empilhado = true,
}: GraficoDeCategoriaProps) {
  const agregado = agregarSeriesAcimaDoLimite(dados, series);
  return (
    <ResponsiveContainer width="100%" height={altura}>
      <AreaChart data={agregado.dados}>
        <CartesianGrid stroke={COR_GRADE} strokeDasharray="3 3" vertical={false} />
        <XAxis dataKey={chaveCategoria} stroke={COR_EIXO} tick={ESTILO_ROTULO_EIXO} />
        <YAxis stroke={COR_EIXO} tick={ESTILO_ROTULO_EIXO} />
        <Tooltip />
        <Legend />
        {agregado.series.map((serie, indice) => {
          const cor = corDaSerie(indice);
          return (
            <Area
              key={serie.chave}
              type="monotone"
              dataKey={serie.chave}
              name={serie.rotulo}
              stroke={cor}
              fill={cor}
              fillOpacity={0.35}
              {...(empilhado ? { stackId: "pilha" } : {})}
            />
          );
        })}
      </AreaChart>
    </ResponsiveContainer>
  );
}

export interface GraficoDePizzaProps {
  fatias: readonly FatiaDePizza[];
  altura?: number;
}

/**
 * Gráfico de pizza. Cada fatia carrega rótulo direto (nome + percentual) além
 * da cor, e a legenda lista todas as fatias por nome. Acima de 8 fatias, o
 * excedente vira "Outros".
 */
export function GraficoDePizza({ fatias, altura = ALTURA_PADRAO }: GraficoDePizzaProps) {
  const agregadas = agregarFatiasAcimaDoLimite(fatias);
  return (
    <ResponsiveContainer width="100%" height={altura}>
      <PieChart>
        <Tooltip />
        <Legend />
        <Pie
          data={agregadas as unknown as Record<string, unknown>[]}
          dataKey="valor"
          nameKey="rotulo"
          label={(propriedades: { rotulo?: string; percent?: number }) =>
            `${propriedades.rotulo ?? ""} (${((propriedades.percent ?? 0) * 100).toFixed(0)}%)`
          }
        >
          {agregadas.map((fatia, indice) => (
            <Cell key={fatia.chave} fill={corDaSerie(indice)} />
          ))}
        </Pie>
      </PieChart>
    </ResponsiveContainer>
  );
}
