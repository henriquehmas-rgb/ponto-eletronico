/**
 * Marcadores de forma distinta para pontos de gráfico de linha. Cor nunca é
 * o único portador (WCAG 1.4.1): cada série de linha também desenha uma
 * forma geométrica diferente no ponto, reconhecível mesmo em escala de
 * cinza ou por quem não distingue as cores.
 */
export type FormaDeMarcador =
  | "circulo"
  | "quadrado"
  | "triangulo"
  | "losango"
  | "triangulo-invertido"
  | "cruz"
  | "estrela"
  | "mais";

const SEQUENCIA_DE_FORMAS: readonly FormaDeMarcador[] = [
  "circulo",
  "quadrado",
  "triangulo",
  "losango",
  "triangulo-invertido",
  "cruz",
  "estrela",
  "mais",
];

export function formaParaIndice(indice: number): FormaDeMarcador {
  return SEQUENCIA_DE_FORMAS[indice % SEQUENCIA_DE_FORMAS.length] ?? "circulo";
}

const RAIO = 5;

export interface MarcadorDeFormaProps {
  cx?: number | undefined;
  cy?: number | undefined;
  forma: FormaDeMarcador;
  cor: string;
}

/** Renderiza o marcador SVG de um ponto do gráfico de linha na forma pedida. */
export function MarcadorDeForma({ cx, cy, forma, cor }: MarcadorDeFormaProps) {
  if (cx === undefined || cy === undefined) return null;

  switch (forma) {
    case "circulo":
      return <circle cx={cx} cy={cy} r={RAIO} fill={cor} />;
    case "quadrado":
      return (
        <rect x={cx - RAIO} y={cy - RAIO} width={RAIO * 2} height={RAIO * 2} fill={cor} />
      );
    case "triangulo":
      return (
        <polygon
          points={`${cx},${cy - RAIO} ${cx + RAIO},${cy + RAIO} ${cx - RAIO},${cy + RAIO}`}
          fill={cor}
        />
      );
    case "triangulo-invertido":
      return (
        <polygon
          points={`${cx - RAIO},${cy - RAIO} ${cx + RAIO},${cy - RAIO} ${cx},${cy + RAIO}`}
          fill={cor}
        />
      );
    case "losango":
      return (
        <polygon
          points={`${cx},${cy - RAIO} ${cx + RAIO},${cy} ${cx},${cy + RAIO} ${cx - RAIO},${cy}`}
          fill={cor}
        />
      );
    case "cruz":
      return (
        <g stroke={cor} strokeWidth={2}>
          <line x1={cx - RAIO} y1={cy - RAIO} x2={cx + RAIO} y2={cy + RAIO} />
          <line x1={cx + RAIO} y1={cy - RAIO} x2={cx - RAIO} y2={cy + RAIO} />
        </g>
      );
    case "mais":
      return (
        <g stroke={cor} strokeWidth={2}>
          <line x1={cx - RAIO} y1={cy} x2={cx + RAIO} y2={cy} />
          <line x1={cx} y1={cy - RAIO} x2={cx} y2={cy + RAIO} />
        </g>
      );
    case "estrela": {
      const pontos = Array.from({ length: 5 }, (_valor, indice) => {
        const anguloExterno = (Math.PI * 2 * indice) / 5 - Math.PI / 2;
        const anguloInterno = anguloExterno + Math.PI / 5;
        const externo = `${cx + RAIO * Math.cos(anguloExterno)},${cy + RAIO * Math.sin(anguloExterno)}`;
        const interno = `${cx + (RAIO / 2.5) * Math.cos(anguloInterno)},${cy + (RAIO / 2.5) * Math.sin(anguloInterno)}`;
        return `${externo} ${interno}`;
      }).join(" ");
      return <polygon points={pontos} fill={cor} />;
    }
  }
}
