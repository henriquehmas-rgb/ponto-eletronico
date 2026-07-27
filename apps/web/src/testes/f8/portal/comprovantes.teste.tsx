import { render, screen, waitFor } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";

import DetalheDeComprovante from "@/app/eu/comprovantes/[comprovanteId]/page";
import ListaDeComprovantes from "@/app/eu/comprovantes/page";

/**
 * O jsdom não faz layout de verdade (`offsetHeight`/`offsetWidth` ficam em
 * 0), e é essa medida que `@tanstack/react-virtual` usa para saber quantas
 * linhas renderizar — sem o stub, `TabelaDeDados` nunca mostra nenhuma linha
 * em teste (mesmo padrão de `src/testes/dominio/tabela-de-dados.teste.tsx`).
 */
beforeAll(() => {
  Object.defineProperty(HTMLElement.prototype, "offsetHeight", { configurable: true, value: 384 });
  Object.defineProperty(HTMLElement.prototype, "offsetWidth", { configurable: true, value: 800 });
});

const useComprovantesMock = vi.fn();
const useComprovanteMock = vi.fn();

vi.mock("@/ganchos/use-comprovantes", () => ({
  useComprovantes: (...args: unknown[]) => useComprovantesMock(...args),
  useComprovante: (...args: unknown[]) => useComprovanteMock(...args),
}));
vi.mock("next/navigation", () => ({
  useParams: () => ({ comprovanteId: "c1" }),
}));

describe("/eu/comprovantes (T4)", () => {
  it("lista mostra número, NSR e link para o detalhe", () => {
    useComprovantesMock.mockReturnValue({
      data: {
        dados: [{ id: "c1", numero: "0001", nsr: 42, datahoraMarcacao: "2026-07-26T08:00:00Z" }],
        paginacao: { temMais: false, limite: 50 },
      },
      isPending: false,
      isError: false,
      error: null,
    });

    render(<ListaDeComprovantes />);

    expect(screen.getByText("0001")).toBeInTheDocument();
    expect(screen.getByText("42")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Ver comprovante" })).toHaveAttribute(
      "href",
      "/eu/comprovantes/c1",
    );
  });

  it("estado vazio mostra mensagem amigável", () => {
    useComprovantesMock.mockReturnValue({
      data: { dados: [], paginacao: { temMais: false, limite: 50 } },
      isPending: false,
      isError: false,
      error: null,
    });

    render(<ListaDeComprovantes />);

    expect(screen.getByText("Nenhum comprovante emitido ainda.")).toBeInTheDocument();
  });

  it("detalhe mostra número, NSR, hash e texto do comprovante", async () => {
    useComprovanteMock.mockReturnValue({
      data: {
        id: "c1",
        numero: "0001",
        nsr: 42,
        hashSha256: "a".repeat(64),
        conteudoTexto: "Comprovante de registro de ponto...",
        datahoraMarcacao: "2026-07-26T08:00:00Z",
        emitidoEm: "2026-07-26T08:00:01Z",
      },
      isPending: false,
      isError: false,
      error: null,
    });

    render(<DetalheDeComprovante />);

    await waitFor(() => expect(screen.getByText("Comprovante 0001")).toBeInTheDocument());
    expect(screen.getByText("a".repeat(64))).toBeInTheDocument();
    expect(screen.getByText("Comprovante de registro de ponto...")).toBeInTheDocument();
  });
});
