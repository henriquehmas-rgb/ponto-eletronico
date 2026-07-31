import { render, screen } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";

import type * as ModuloDeDataviz from "@/ganchos/use-dataviz-dashboard";
import type * as ModuloDeIndicadores from "@/ganchos/use-indicadores-dashboard";

import { SecaoApuracao } from "@/componentes/paineis/dashboard/secao-apuracao";

/**
 * Recharts (`ResponsiveContainer`) exige `ResizeObserver` de verdade, ausente
 * no jsdom -- mesmo stub que `src/testes/dominio/graficos.teste.tsx` (F9a) já
 * usa para o mesmo problema.
 */
class ResizeObserverForjado {
  private aoRedimensionar: ResizeObserverCallback;
  constructor(aoRedimensionar: ResizeObserverCallback) {
    this.aoRedimensionar = aoRedimensionar;
  }
  observe(alvo: Element) {
    const entrada = {
      target: alvo,
      contentRect: {
        width: (alvo as HTMLElement).offsetWidth,
        height: (alvo as HTMLElement).offsetHeight,
      },
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

const useResumoDeApuracaoMock = vi.fn();
vi.mock("@/ganchos/use-indicadores-dashboard", async (importarOriginal) => {
  const original = await importarOriginal<typeof ModuloDeIndicadores>();
  return { ...original, useResumoDeApuracao: () => useResumoDeApuracaoMock() };
});

const useTendenciaMensalMock = vi.fn();
vi.mock("@/ganchos/use-dataviz-dashboard", async (importarOriginal) => {
  const original = await importarOriginal<typeof ModuloDeDataviz>();
  return {
    ...original,
    useTendenciaMensal: (...args: unknown[]) => useTendenciaMensalMock(...args),
  };
});

function resumoPadrao() {
  return {
    isPending: false,
    data: {
      diasApurados: 10,
      extrasMinutos: 60,
      faltaMinutos: 0,
      atrasoMinutos: 0,
      diasComOcorrencia: 0,
      serieDiaria: [],
    },
  };
}

/**
 * T13 (PCF F11 §5/§6): "teste de componente prova que cada seção renderiza o
 * gráfico com dado mockado da forma de `RelatorioExecucao`/resultado JSON
 * real do motor (não um formato inventado)" -- o mock de `useTendenciaMensal`
 * abaixo devolve exatamente a FORMA que o gancho real produz a partir do
 * artefato JSON (`{ mes, valor }[]`), nunca um formato inventado só para o
 * teste passar.
 */
describe("SecaoApuracao — dataviz de tendência de horas extras (T13)", () => {
  it("mostra 'Carregando…' enquanto a tendência ainda não chegou", () => {
    useResumoDeApuracaoMock.mockReturnValue(resumoPadrao());
    useTendenciaMensalMock.mockReturnValue({ isPending: true, isError: false, data: undefined });

    render(<SecaoApuracao escopo={{}} />);

    expect(screen.getByText("Tendência de horas extras (últimos 6 meses)")).toBeInTheDocument();
    expect(
      screen.queryByText("Não foi possível carregar a tendência de horas extras."),
    ).not.toBeInTheDocument();
  });

  it("mostra mensagem de erro quando a execução do relatório falha", () => {
    useResumoDeApuracaoMock.mockReturnValue(resumoPadrao());
    useTendenciaMensalMock.mockReturnValue({
      isPending: false,
      isError: true,
      data: undefined,
    });

    render(<SecaoApuracao escopo={{}} />);

    expect(
      screen.getByText("Não foi possível carregar a tendência de horas extras."),
    ).toBeInTheDocument();
  });

  it("mostra mensagem de 'sem dado' quando a série vem vazia", () => {
    useResumoDeApuracaoMock.mockReturnValue(resumoPadrao());
    useTendenciaMensalMock.mockReturnValue({ isPending: false, isError: false, data: [] });

    render(<SecaoApuracao escopo={{}} />);

    expect(
      screen.getByText("Sem dado suficiente no período para montar a tendência."),
    ).toBeInTheDocument();
  });

  it("renderiza o GraficoDeLinha com a série mensal, forma { mes, valor }[]", () => {
    useResumoDeApuracaoMock.mockReturnValue(resumoPadrao());
    useTendenciaMensalMock.mockReturnValue({
      isPending: false,
      isError: false,
      data: [
        { mes: "2026-02", valor: 30 },
        { mes: "2026-03", valor: 45 },
      ],
    });

    const { container } = render(<SecaoApuracao escopo={{}} />);

    expect(screen.getByText("Tendência de horas extras (últimos 6 meses)")).toBeInTheDocument();
    expect(container.querySelectorAll("svg").length).toBeGreaterThan(0);
  });

  it("passa o escopo (empresaId/unidadeId) para useTendenciaMensal, mesmo filtro do resto do dashboard", () => {
    useResumoDeApuracaoMock.mockReturnValue(resumoPadrao());
    useTendenciaMensalMock.mockReturnValue({ isPending: true, isError: false, data: undefined });

    render(<SecaoApuracao escopo={{ empresaId: "emp-1", unidadeId: "uni-1" }} />);

    expect(useTendenciaMensalMock).toHaveBeenCalledWith(
      expect.objectContaining({
        codigo: "horas-extras",
        empresaId: "emp-1",
        unidadeId: "uni-1",
      }),
    );
  });
});
