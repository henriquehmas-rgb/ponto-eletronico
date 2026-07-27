import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";

import PaginaDeEmpresas from "@/app/painel/cadastros/empresas/page";
import type * as ModuloDaApi from "@/lib/api";

/**
 * O jsdom não faz layout de verdade (`offsetHeight`/`offsetWidth` sempre 0),
 * e é essa medida que `@tanstack/react-virtual` usa para saber quantas
 * linhas cabem na janela visível — mesmo stub de
 * `testes/dominio/tabela-de-dados.teste.tsx` (F9a).
 */
beforeAll(() => {
  Object.defineProperty(HTMLElement.prototype, "offsetHeight", { configurable: true, value: 384 });
  Object.defineProperty(HTMLElement.prototype, "offsetWidth", { configurable: true, value: 800 });
});

const useSessaoCompletaMock = vi.fn();
const apiGetMock = vi.fn();

vi.mock("@/ganchos/use-sessao-completa", () => ({
  useSessaoCompleta: () => useSessaoCompletaMock(),
}));
vi.mock("@/lib/api", async (importarOriginal) => {
  const original = await importarOriginal<typeof ModuloDaApi>();
  return {
    ...original,
    api: { ...original.api, GET: (...args: unknown[]) => apiGetMock(...args) },
  };
});

function renderizar() {
  const cliente = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={cliente}>
      <PaginaDeEmpresas />
    </QueryClientProvider>,
  );
}

/**
 * T4 (PCF F9b, "pronto quando"): "cada ação (criar/editar/excluir) só
 * aparece com a permissão correspondente (`empresas.criar`/`editar`/
 * `excluir`)" — RBAC sempre por `sessao.permissoes.includes(x-permissao)`,
 * nunca por papel hardcoded (§6/§9 do PCF).
 */
describe("Empresas (T4 — RBAC por permissão exata)", () => {
  it('sem "empresas.criar", o botão "Nova empresa" não aparece', async () => {
    useSessaoCompletaMock.mockReturnValue({
      sessao: { permissoes: [] },
      carregando: false,
      erro: null,
    });
    apiGetMock.mockResolvedValue({
      data: { dados: [], paginacao: { temMais: false, limite: 200 } },
      error: undefined,
    });

    renderizar();

    expect(screen.queryByRole("button", { name: "Nova empresa" })).not.toBeInTheDocument();
  });

  it('com "empresas.criar", o botão "Nova empresa" aparece', async () => {
    useSessaoCompletaMock.mockReturnValue({
      sessao: { permissoes: ["empresas.criar"] },
      carregando: false,
      erro: null,
    });
    apiGetMock.mockResolvedValue({
      data: { dados: [], paginacao: { temMais: false, limite: 200 } },
      error: undefined,
    });

    renderizar();

    expect(await screen.findByRole("button", { name: "Nova empresa" })).toBeInTheDocument();
  });

  it('sem "empresas.excluir", nenhuma ação de excluir aparece nas linhas da tabela', async () => {
    useSessaoCompletaMock.mockReturnValue({
      sessao: { permissoes: [] },
      carregando: false,
      erro: null,
    });
    apiGetMock.mockResolvedValue({
      data: {
        dados: [
          {
            id: "e1",
            razaoSocial: "SEEG Serviços Ltda",
            cnpj: "12345678000199",
            tipo: "matriz",
            ativo: true,
          },
        ],
        paginacao: { temMais: false, limite: 200 },
      },
      error: undefined,
    });

    renderizar();

    expect(await screen.findByText("SEEG Serviços Ltda")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Excluir" })).not.toBeInTheDocument();
  });
});
