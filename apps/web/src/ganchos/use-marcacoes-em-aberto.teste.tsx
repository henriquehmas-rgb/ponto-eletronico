import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type * as ModuloDaApi from "@/lib/api";

import { useMarcacoesEmAberto } from "./use-marcacoes-em-aberto";

const apiGetMock = vi.fn();

vi.mock("@/lib/api", async (importarOriginal) => {
  const original = await importarOriginal<typeof ModuloDaApi>();
  return {
    ...original,
    api: { ...original.api, GET: (...args: unknown[]) => apiGetMock(...args) },
  };
});

function envelopeDeMarcacoes(dados: unknown[]) {
  return { data: { dados, paginacao: { temMais: false, limite: 100 } }, error: undefined };
}
function envelopeDeColaboradores(dados: unknown[]) {
  return { data: { dados, paginacao: { temMais: false, limite: 200 } }, error: undefined };
}

function envolvedor() {
  const cliente = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return function Envolvedor({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={cliente}>{children}</QueryClientProvider>;
  };
}

describe("useMarcacoesEmAberto (T3 — paridade, nunca afirma presença como fato)", () => {
  beforeEach(() => {
    apiGetMock.mockReset();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("paridade PAR (2 marcações) não é listada como em aberto", async () => {
    apiGetMock.mockImplementation((caminho: string) => {
      if (caminho === "/v1/marcacoes") {
        return Promise.resolve(
          envelopeDeMarcacoes([
            {
              id: "m1",
              vinculoId: "v1",
              colaboradorId: "c1",
              datahoraMarcacao: "2026-07-27T08:00:00Z",
              canal: "web",
            },
            {
              id: "m2",
              vinculoId: "v1",
              colaboradorId: "c1",
              datahoraMarcacao: "2026-07-27T12:00:00Z",
              canal: "web",
            },
          ]),
        );
      }
      return Promise.resolve(envelopeDeColaboradores([]));
    });

    const { result } = renderHook(
      () => useMarcacoesEmAberto({ intervaloDeAtualizacaoMs: 999_000 }),
      {
        wrapper: envolvedor(),
      },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual([]);
  });

  it("paridade ÍMPAR (3 marcações) é listada, com o horário da ÚLTIMA marcação", async () => {
    apiGetMock.mockImplementation((caminho: string) => {
      if (caminho === "/v1/marcacoes") {
        return Promise.resolve(
          envelopeDeMarcacoes([
            {
              id: "m1",
              vinculoId: "v1",
              colaboradorId: "c1",
              datahoraMarcacao: "2026-07-27T08:00:00Z",
              canal: "web",
            },
            {
              id: "m2",
              vinculoId: "v1",
              colaboradorId: "c1",
              datahoraMarcacao: "2026-07-27T12:00:00Z",
              canal: "web",
            },
            {
              id: "m3",
              vinculoId: "v1",
              colaboradorId: "c1",
              datahoraMarcacao: "2026-07-27T14:32:00Z",
              canal: "web",
            },
          ]),
        );
      }
      return Promise.resolve(envelopeDeColaboradores([{ id: "c1", nomeCompleto: "Maria Souza" }]));
    });

    const { result } = renderHook(
      () => useMarcacoesEmAberto({ intervaloDeAtualizacaoMs: 999_000 }),
      {
        wrapper: envolvedor(),
      },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toHaveLength(1);
    expect(result.current.data?.[0]).toMatchObject({
      vinculoId: "v1",
      nomeColaborador: "Maria Souza",
      quantidadeMarcacoes: 3,
      ultimaMarcacaoEm: "2026-07-27T14:32:00Z",
    });
  });

  it("vínculos diferentes são contados separadamente (um par, um ímpar)", async () => {
    apiGetMock.mockImplementation((caminho: string) => {
      if (caminho === "/v1/marcacoes") {
        return Promise.resolve(
          envelopeDeMarcacoes([
            {
              id: "m1",
              vinculoId: "v-par",
              colaboradorId: "c1",
              datahoraMarcacao: "2026-07-27T08:00:00Z",
              canal: "web",
            },
            {
              id: "m2",
              vinculoId: "v-par",
              colaboradorId: "c1",
              datahoraMarcacao: "2026-07-27T12:00:00Z",
              canal: "web",
            },
            {
              id: "m3",
              vinculoId: "v-impar",
              colaboradorId: "c2",
              datahoraMarcacao: "2026-07-27T09:00:00Z",
              canal: "web",
            },
          ]),
        );
      }
      return Promise.resolve(envelopeDeColaboradores([]));
    });

    const { result } = renderHook(
      () => useMarcacoesEmAberto({ intervaloDeAtualizacaoMs: 999_000 }),
      {
        wrapper: envolvedor(),
      },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toHaveLength(1);
    expect(result.current.data?.[0]?.vinculoId).toBe("v-impar");
  });

  it("atualiza sozinho dentro do intervalo de polling configurado (vi.useFakeTimers)", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    apiGetMock.mockImplementation((caminho: string) => {
      if (caminho === "/v1/marcacoes") return Promise.resolve(envelopeDeMarcacoes([]));
      return Promise.resolve(envelopeDeColaboradores([]));
    });

    renderHook(() => useMarcacoesEmAberto({ intervaloDeAtualizacaoMs: 30_000 }), {
      wrapper: envolvedor(),
    });

    await vi.waitFor(() => expect(apiGetMock).toHaveBeenCalled());
    const chamadasIniciais = apiGetMock.mock.calls.length;

    await act(async () => {
      await vi.advanceTimersByTimeAsync(30_000);
    });
    await vi.waitFor(() => expect(apiGetMock.mock.calls.length).toBeGreaterThan(chamadasIniciais));
  });
});
