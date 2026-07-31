import { render, screen } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";

import type * as ModuloDeDataviz from "@/ganchos/use-dataviz-dashboard";
import type * as ModuloDeIndicadores from "@/ganchos/use-indicadores-dashboard";

import { SecaoOcorrencias } from "@/componentes/paineis/dashboard/secao-ocorrencias";

/** Mesmo stub de `ResizeObserver` de `secao-apuracao.teste.tsx`/`graficos.teste.tsx` (F9a). */
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

const useFilaDeOcorrenciasPorSeveridadeMock = vi.fn();
vi.mock("@/ganchos/use-indicadores-dashboard", async (importarOriginal) => {
  const original = await importarOriginal<typeof ModuloDeIndicadores>();
  return {
    ...original,
    useFilaDeOcorrenciasPorSeveridade: () => useFilaDeOcorrenciasPorSeveridadeMock(),
  };
});

const useTendenciaMensalMock = vi.fn();
vi.mock("@/ganchos/use-dataviz-dashboard", async (importarOriginal) => {
  const original = await importarOriginal<typeof ModuloDeDataviz>();
  return {
    ...original,
    useTendenciaMensal: (...args: unknown[]) => useTendenciaMensalMock(...args),
  };
});

function contagensVazias() {
  return [
    { severidade: "info" as const, total: 0, carregando: false },
    { severidade: "atencao" as const, total: 0, carregando: false },
    { severidade: "alta" as const, total: 0, carregando: false },
    { severidade: "critica" as const, total: 0, carregando: false },
  ];
}

/** T13: mesma prova de "forma real, não inventada" que `secao-apuracao.teste.tsx` já documenta. */
describe("SecaoOcorrencias — dataviz de ocorrências por mês (T13)", () => {
  it("renderiza o cartão de fila (pré-existente) E o novo gráfico de série mensal", () => {
    useFilaDeOcorrenciasPorSeveridadeMock.mockReturnValue(contagensVazias());
    useTendenciaMensalMock.mockReturnValue({
      isPending: false,
      isError: false,
      data: [
        { mes: "2026-06", valor: 3 },
        { mes: "2026-07", valor: 5 },
      ],
    });

    const { container } = render(<SecaoOcorrencias escopo={{}} />);

    expect(screen.getByText("Ocorrências abertas")).toBeInTheDocument();
    expect(screen.getByText("Ocorrências por mês (últimos 6 meses)")).toBeInTheDocument();
    expect(container.querySelectorAll("svg").length).toBeGreaterThan(0);
  });

  it("mostra mensagem de erro do gráfico sem afetar o cartão de fila existente", () => {
    useFilaDeOcorrenciasPorSeveridadeMock.mockReturnValue(contagensVazias());
    useTendenciaMensalMock.mockReturnValue({ isPending: false, isError: true, data: undefined });

    render(<SecaoOcorrencias escopo={{}} />);

    expect(
      screen.getByText("Nenhuma ocorrência aberta no escopo selecionado."),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Não foi possível carregar a série mensal de ocorrências."),
    ).toBeInTheDocument();
  });

  it("passa o escopo (empresaId/unidadeId) para useTendenciaMensal", () => {
    useFilaDeOcorrenciasPorSeveridadeMock.mockReturnValue(contagensVazias());
    useTendenciaMensalMock.mockReturnValue({ isPending: true, isError: false, data: undefined });

    render(<SecaoOcorrencias escopo={{ empresaId: "emp-9" }} />);

    expect(useTendenciaMensalMock).toHaveBeenCalledWith(
      expect.objectContaining({ codigo: "ocorrencias", empresaId: "emp-9" }),
    );
  });
});
