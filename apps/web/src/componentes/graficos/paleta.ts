/**
 * Paleta categórica dos gráficos. Consome EXCLUSIVAMENTE
 * `tema.<t>.grafico.serie1..serie8` via `var(--cor-grafico-serieN)` — nunca
 * um hexadecimal escrito à mão. `src/testes/dominio/graficos.teste.tsx` varre
 * este arquivo (e os componentes que o usam) para provar isso.
 */
export const CORES_DE_SERIE: readonly string[] = [
  "var(--cor-grafico-serie1)",
  "var(--cor-grafico-serie2)",
  "var(--cor-grafico-serie3)",
  "var(--cor-grafico-serie4)",
  "var(--cor-grafico-serie5)",
  "var(--cor-grafico-serie6)",
  "var(--cor-grafico-serie7)",
  "var(--cor-grafico-serie8)",
];

export const LIMITE_DE_SERIES = CORES_DE_SERIE.length;

export const COR_GRADE = "var(--cor-grafico-grade)";
export const COR_EIXO = "var(--cor-grafico-eixo)";
export const COR_ROTULO = "var(--cor-grafico-rotulo)";

export function corDaSerie(indice: number): string {
  return CORES_DE_SERIE[indice % CORES_DE_SERIE.length] ?? CORES_DE_SERIE[0]!;
}

export interface SerieDeGrafico {
  chave: string;
  rotulo: string;
}

/**
 * Garante no máximo `limite` séries visíveis (o padrão é 8, o tamanho da
 * paleta): acima disso, soma o excedente numa série sintética "Outros" em vez
 * de repetir ou clarear cor. Puro — não desenha nada.
 */
export function agregarSeriesAcimaDoLimite(
  dados: ReadonlyArray<Record<string, unknown>>,
  series: readonly SerieDeGrafico[],
  limite: number = LIMITE_DE_SERIES,
): { dados: Record<string, unknown>[]; series: SerieDeGrafico[] } {
  if (series.length <= limite) {
    return { dados: dados.map((linha) => ({ ...linha })), series: [...series] };
  }

  const mantidas = series.slice(0, limite - 1);
  const excedentes = series.slice(limite - 1);

  const novosDados = dados.map((linha) => {
    const nova: Record<string, unknown> = {};
    for (const serie of mantidas) {
      nova[serie.chave] = linha[serie.chave];
    }
    let somaOutros = 0;
    for (const serie of excedentes) {
      const valor = linha[serie.chave];
      if (typeof valor === "number") somaOutros += valor;
    }
    nova.outros = somaOutros;
    // Preserva campos que nao sao series (ex.: a chave de categoria do eixo X).
    for (const [chave, valor] of Object.entries(linha)) {
      if (!series.some((serie) => serie.chave === chave)) {
        nova[chave] = valor;
      }
    }
    return nova;
  });

  return { dados: novosDados, series: [...mantidas, { chave: "outros", rotulo: "Outros" }] };
}

export interface FatiaDePizza {
  chave: string;
  rotulo: string;
  valor: number;
}

/** Mesma regra de agregação, para o formato "uma fatia por item" da pizza. */
export function agregarFatiasAcimaDoLimite(
  fatias: readonly FatiaDePizza[],
  limite: number = LIMITE_DE_SERIES,
): FatiaDePizza[] {
  if (fatias.length <= limite) return [...fatias];
  const mantidas = fatias.slice(0, limite - 1);
  const excedentes = fatias.slice(limite - 1);
  const somaOutros = excedentes.reduce((total, fatia) => total + fatia.valor, 0);
  return [...mantidas, { chave: "outros", rotulo: "Outros", valor: somaOutros }];
}
