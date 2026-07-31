import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type * as ModuloDaApi from "@/lib/api";

import { useTendenciaMensal } from "./use-dataviz-dashboard";

const apiGetMock = vi.fn();

vi.mock("@/lib/api", async (importarOriginal) => {
  const original = await importarOriginal<typeof ModuloDaApi>();
  return {
    ...original,
    api: { ...original.api, GET: (...args: unknown[]) => apiGetMock(...args) },
  };
});

function envelope(data: unknown) {
  return { data, error: undefined };
}

function envolvedor() {
  const cliente = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return function Envolvedor({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={cliente}>{children}</QueryClientProvider>;
  };
}

describe("useTendenciaMensal (T13 -- forma real de RelatorioExecucao, nunca inventada)", () => {
  beforeEach(() => {
    apiGetMock.mockReset();
    vi.stubGlobal("fetch", vi.fn());
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it("caminho sincrono: execucao ja concluida na primeira resposta busca o artefato direto", async () => {
    apiGetMock.mockImplementation((caminho: string) => {
      if (caminho === "/v1/relatorios/{codigo}/executar") {
        return Promise.resolve(
          envelope({
            id: "exec-1",
            status: "concluido",
            urlDownload: "https://minio.teste/exec-1.json",
          }),
        );
      }
      throw new Error(`chamada inesperada: ${caminho}`);
    });
    vi.mocked(fetch).mockResolvedValue({
      ok: true,
      status: 200,
      json: () =>
        Promise.resolve([
          { mes: "2026-06", totalMinutos: 120 },
          { mes: "2026-05", totalMinutos: 90 },
        ]),
    } as Response);

    const { result } = renderHook(
      () => useTendenciaMensal({ codigo: "horas-extras", chaveValor: "totalMinutos" }),
      { wrapper: envolvedor() },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    // Ordenado por mes ascendente, mesmo vindo fora de ordem do artefato.
    expect(result.current.data).toEqual([
      { mes: "2026-05", valor: 90 },
      { mes: "2026-06", valor: 120 },
    ]);
    expect(fetch).toHaveBeenCalledWith("https://minio.teste/exec-1.json");
  });

  it("caminho assincrono: faz poll de obterExecucaoRelatorio ate concluir", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let chamadasDePool = 0;
    apiGetMock.mockImplementation((caminho: string) => {
      if (caminho === "/v1/relatorios/{codigo}/executar") {
        return Promise.resolve(envelope({ id: "exec-2", status: "enfileirado", progresso: 0 }));
      }
      if (caminho === "/v1/relatorios/execucoes/{execucaoId}") {
        chamadasDePool += 1;
        if (chamadasDePool < 2) {
          return Promise.resolve(envelope({ id: "exec-2", status: "processando", progresso: 50 }));
        }
        return Promise.resolve(
          envelope({
            id: "exec-2",
            status: "concluido",
            progresso: 100,
            urlDownload: "https://minio.teste/exec-2.json",
          }),
        );
      }
      throw new Error(`chamada inesperada: ${caminho}`);
    });
    vi.mocked(fetch).mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve([{ mes: "2026-07", saldoMinutos: 30 }]),
    } as Response);

    const { result } = renderHook(
      () =>
        useTendenciaMensal({
          codigo: "banco-de-horas",
          chaveValor: "saldoMinutos",
          colaboradorId: "colab-1",
        }),
      { wrapper: envolvedor() },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true), { timeout: 8_000 });
    expect(result.current.data).toEqual([{ mes: "2026-07", valor: 30 }]);
    expect(chamadasDePool).toBeGreaterThanOrEqual(2);
  }, 10_000);

  it("execucao concluida sem urlDownload (relatorio sem linhas) devolve lista vazia, nao erro", async () => {
    apiGetMock.mockImplementation((caminho: string) => {
      if (caminho === "/v1/relatorios/{codigo}/executar") {
        return Promise.resolve(envelope({ id: "exec-3", status: "concluido" }));
      }
      throw new Error(`chamada inesperada: ${caminho}`);
    });

    const { result } = renderHook(
      () => useTendenciaMensal({ codigo: "ocorrencias", chaveValor: "total" }),
      { wrapper: envolvedor() },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual([]);
    expect(fetch).not.toHaveBeenCalled();
  });

  it("execucao que falha vira estado de erro do gancho, nunca lista vazia disfarcada", async () => {
    apiGetMock.mockImplementation((caminho: string) => {
      if (caminho === "/v1/relatorios/{codigo}/executar") {
        return Promise.resolve(
          envelope({ id: "exec-4", status: "falhou", erro: "Falha simulada de teste" }),
        );
      }
      throw new Error(`chamada inesperada: ${caminho}`);
    });

    const { result } = renderHook(
      () => useTendenciaMensal({ codigo: "absenteismo", chaveValor: "total" }),
      { wrapper: envolvedor() },
    );

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect((result.current.error as Error).message).toContain("Falha simulada de teste");
  });

  it("desabilitado (habilitado=false) nunca chama a API", async () => {
    const { result } = renderHook(
      () =>
        useTendenciaMensal({
          codigo: "horas-extras",
          chaveValor: "totalMinutos",
          habilitado: false,
        }),
      { wrapper: envolvedor() },
    );

    expect(result.current.isPending).toBe(true);
    expect(apiGetMock).not.toHaveBeenCalled();
  });
});
