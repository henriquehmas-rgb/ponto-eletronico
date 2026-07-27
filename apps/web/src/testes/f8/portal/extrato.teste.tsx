import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ExtratoDoColaborador from "@/app/eu/extrato/page";
import type * as ModuloDaApi from "@/lib/api";

const useSessaoAtualMock = vi.fn();
const useExtratoBancoHorasMock = vi.fn();
const apiGetMock = vi.fn();

vi.mock("@/ganchos/use-sessao", () => ({
  useSessaoAtual: (...args: unknown[]) => useSessaoAtualMock(...args),
}));
vi.mock("@/ganchos/use-banco-de-horas", () => ({
  useExtratoBancoHoras: (...args: unknown[]) => useExtratoBancoHorasMock(...args),
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
      <ExtratoDoColaborador />
    </QueryClientProvider>,
  );
}

describe("/eu/extrato (T3)", () => {
  beforeEach(() => {
    useSessaoAtualMock.mockReturnValue({ data: { colaboradorId: "c1" } });
    apiGetMock.mockResolvedValue({
      data: {
        dados: [
          {
            id: "a1",
            data: "2026-07-01",
            trabalhadoMinutos: 480,
            extrasMinutos: 30,
            noturnoMinutos: 0,
            saldoMinutos: 30,
          },
        ],
        paginacao: { temMais: false, limite: 50 },
      },
      error: undefined,
    });
    useExtratoBancoHorasMock.mockReturnValue({
      data: {
        lancamentos: [
          {
            id: "l1",
            sequencia: 1,
            dataCompetencia: "2026-07-01",
            tipo: "credito",
            origem: "apuracao",
            minutosEquivalentes: 30,
            saldoAposMinutos: 30,
          },
        ],
        paginacao: { temMais: true, proximoCursor: "cursor-2", limite: 50 },
      },
      isPending: false,
      isError: false,
      error: null,
    });
  });

  it("mostra a apuração e o extrato do período, sem termo proibido de banco positivo/negativo", async () => {
    renderizar();

    await waitFor(() => expect(screen.getByText("Apuração do período")).toBeInTheDocument());
    expect(screen.getByText("Extrato de banco de horas")).toBeInTheDocument();

    const corpoDaPagina = document.body.textContent ?? "";
    expect(corpoDaPagina.toLowerCase()).not.toContain("positivo");
    expect(corpoDaPagina.toLowerCase()).not.toContain("negativo");
  });

  it("troca de período (atalho) recarrega a consulta de apuração com as novas datas", async () => {
    const usuarioTeste = userEvent.setup();
    renderizar();

    await waitFor(() => expect(apiGetMock).toHaveBeenCalled());
    apiGetMock.mockClear();

    await usuarioTeste.click(screen.getByText("Mês anterior"));

    await waitFor(() => expect(apiGetMock).toHaveBeenCalled());
    const chamada = apiGetMock.mock.calls.at(-1) as [
      string,
      { params: { query: { de: string; ate: string } } },
    ];
    expect(chamada[1].params.query.de).not.toBe("");
  });

  it("paginação por cursor: clicar em próxima página usa paginacao.proximoCursor", async () => {
    const usuarioTeste = userEvent.setup();
    renderizar();

    await waitFor(() => expect(screen.getByText("Próxima página")).toBeInTheDocument());
    await usuarioTeste.click(screen.getByText("Próxima página"));

    await waitFor(() => {
      const ultimaChamada = useExtratoBancoHorasMock.mock.calls.at(-1) as [{ cursor?: string }];
      expect(ultimaChamada[0].cursor).toBe("cursor-2");
    });
  });

  it('botão "Página anterior" fica desabilitado quando não há cursorAnterior', async () => {
    renderizar();
    await waitFor(() => expect(screen.getByText("Página anterior")).toBeInTheDocument());
    expect(screen.getByText("Página anterior").closest("button")).toBeDisabled();
  });
});
