import { render, screen } from "@testing-library/react";
import { beforeAll, describe, expect, it } from "vitest";

import { TabelaDeDados, type ColunaDeTabela } from "@/componentes/dominio/tabela-de-dados";

/**
 * Ver `tabela-de-dados.teste.tsx` para a explicação: sem este stub o jsdom
 * mede a área rolável como 0×0 (não faz layout de verdade e não implementa
 * `ResizeObserver`), e `@tanstack/react-virtual` nunca renderiza uma linha.
 */
beforeAll(() => {
  Object.defineProperty(HTMLElement.prototype, "offsetHeight", {
    configurable: true,
    value: 384,
  });
  Object.defineProperty(HTMLElement.prototype, "offsetWidth", {
    configurable: true,
    value: 800,
  });
});

interface LinhaDeBenchmark {
  id: string;
  colaborador: string;
  saldoMinutos: number;
}

const TOTAL_LINHAS = 10_000;
const LIMITE_LINHAS_NO_DOM = 100;
const LIMITE_MONTAGEM_MS = 1000;

function gerarLinhas(total: number): LinhaDeBenchmark[] {
  return Array.from({ length: total }, (_valor, indice) => ({
    id: `linha-${indice}`,
    colaborador: `Colaborador ${indice}`,
    saldoMinutos: indice % 2 === 0 ? indice : -indice,
  }));
}

const COLUNAS: ColunaDeTabela<LinhaDeBenchmark>[] = [
  { id: "colaborador", cabecalho: "Colaborador", renderizarCelula: (linha) => linha.colaborador },
  { id: "saldo", cabecalho: "Saldo (min)", renderizarCelula: (linha) => String(linha.saldoMinutos) },
];

describe("TabelaDeDados — desempenho com 10.000 linhas", () => {
  it("virtualiza (menos de 100 linhas no DOM) e monta abaixo do limite de tempo", () => {
    const linhas = gerarLinhas(TOTAL_LINHAS);

    const inicio = performance.now();
    render(
      <TabelaDeDados
        linhas={linhas}
        colunas={COLUNAS}
        obterId={(linha) => linha.id}
        alturaContainerPx={384}
      />,
    );
    const duracaoMs = performance.now() - inicio;

    // "role=row" inclui a linha de cabecalho; o teste conta so as linhas de
    // dado (dentro do segundo rowgroup) para nao confundir cabecalho com dado.
    const linhasNoDom = document.querySelectorAll('[role="rowgroup"] [role="row"]').length;

    console.warn(
      `[benchmark TabelaDeDados] ${TOTAL_LINHAS} linhas fornecidas, ${linhasNoDom} linhas no DOM, montagem em ${duracaoMs.toFixed(2)}ms`,
    );

    expect(linhasNoDom).toBeLessThan(LIMITE_LINHAS_NO_DOM);
    expect(duracaoMs).toBeLessThan(LIMITE_MONTAGEM_MS);

    // Confere que os dados sao mesmo os 10.000, so a apresentacao e que virtualiza.
    expect(screen.getByRole("grid")).toHaveAttribute("aria-rowcount", String(TOTAL_LINHAS));
  });
});
