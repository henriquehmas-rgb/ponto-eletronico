import { render, screen } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";

import type * as ModuloDeDataviz from "@/ganchos/use-dataviz-dashboard";
import type * as ModuloDeIndicadores from "@/ganchos/use-indicadores-dashboard";

import { SecaoBancoDeHoras } from "@/componentes/paineis/dashboard/secao-banco-de-horas";

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

const useSessaoCompletaMock = vi.fn();
vi.mock("@/ganchos/use-sessao-completa", () => ({
  useSessaoCompleta: () => useSessaoCompletaMock(),
}));

const useSaldoBancoHorasAmostraMock = vi.fn();
vi.mock("@/ganchos/use-indicadores-dashboard", async (importarOriginal) => {
  const original = await importarOriginal<typeof ModuloDeIndicadores>();
  return { ...original, useSaldoBancoHorasAmostra: () => useSaldoBancoHorasAmostraMock() };
});

const useTendenciaMensalMock = vi.fn();
vi.mock("@/ganchos/use-dataviz-dashboard", async (importarOriginal) => {
  const original = await importarOriginal<typeof ModuloDeDataviz>();
  return {
    ...original,
    useTendenciaMensal: (...args: unknown[]) => useTendenciaMensalMock(...args),
  };
});

function sessaoComColaborador() {
  return { sessao: { colaboradorId: "colab-1" }, carregando: false };
}

/** T13: mesma prova de "forma real, não inventada" que `secao-apuracao.teste.tsx` já documenta. */
describe("SecaoBancoDeHoras — dataviz de evolução do saldo (T13)", () => {
  it("sem colaboradorId (RH/gestor sem vínculo próprio), a seção inteira não aparece — e a tendência nem é chamada com habilitado=true", () => {
    useSessaoCompletaMock.mockReturnValue({ sessao: undefined, carregando: false });
    useSaldoBancoHorasAmostraMock.mockReturnValue({
      isPending: false,
      isError: false,
      data: undefined,
    });
    useTendenciaMensalMock.mockReturnValue({ isPending: true, isError: false, data: undefined });

    const { container } = render(<SecaoBancoDeHoras />);

    expect(container).toBeEmptyDOMElement();
    expect(useTendenciaMensalMock).toHaveBeenCalledWith(
      expect.objectContaining({ habilitado: false }),
    );
  });

  it("com colaboradorId e saldo carregado, renderiza o cartão de saldo E o gráfico de evolução", () => {
    useSessaoCompletaMock.mockReturnValue(sessaoComColaborador());
    useSaldoBancoHorasAmostraMock.mockReturnValue({
      isPending: false,
      isError: false,
      data: { saldoMinutos: 120 },
    });
    useTendenciaMensalMock.mockReturnValue({
      isPending: false,
      isError: false,
      data: [
        { mes: "2026-05", valor: 60 },
        { mes: "2026-06", valor: 120 },
      ],
    });

    const { container } = render(<SecaoBancoDeHoras />);

    expect(screen.getByText("Evolução do saldo (últimos 6 meses)")).toBeInTheDocument();
    expect(container.querySelectorAll("svg").length).toBeGreaterThan(0);
    expect(useTendenciaMensalMock).toHaveBeenCalledWith(
      expect.objectContaining({
        codigo: "banco-de-horas",
        colaboradorId: "colab-1",
        habilitado: true,
      }),
    );
  });

  it("mostra mensagem de 'sem dado' quando a série de evolução vem vazia", () => {
    useSessaoCompletaMock.mockReturnValue(sessaoComColaborador());
    useSaldoBancoHorasAmostraMock.mockReturnValue({
      isPending: false,
      isError: false,
      data: { saldoMinutos: 0 },
    });
    useTendenciaMensalMock.mockReturnValue({ isPending: false, isError: false, data: [] });

    render(<SecaoBancoDeHoras />);

    expect(
      screen.getByText("Sem dado suficiente no período para montar a evolução."),
    ).toBeInTheDocument();
  });
});
