import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type * as ModuloDaApi from "@/lib/api";

import { GradeVisualDeEscala } from "@/componentes/paineis/escalas/grade-visual";

const apiGetMock = vi.fn();

vi.mock("@/lib/api", async (importarOriginal) => {
  const original = await importarOriginal<typeof ModuloDaApi>();
  return {
    ...original,
    api: { ...original.api, GET: (...args: unknown[]) => apiGetMock(...args) },
  };
});

// RBAC não é o assunto deste teste — bypassa a dependência de sessão (T1, A1)
// para exercitar só a lógica de dados de T13 (divisão apurações × resolvedor).
vi.mock("@/lib/permissoes", () => ({
  PortaoDePermissao: ({ children }: { children: ReactNode }) => children,
}));

function envelope(dados: unknown[], temMais = false) {
  return { data: { dados, paginacao: { temMais, limite: 200 } }, error: undefined };
}

function envolvedor() {
  const cliente = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return function Envolvedor({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={cliente}>{children}</QueryClientProvider>;
  };
}

// "Hoje" fixado em 15/jul/2026 — mês inteiro (1..31) tem dias passados
// (1..15) e futuros (16..31) na mesma tela, sem depender do relógio real.
const HOJE = new Date(2026, 6, 15, 10, 0, 0);

describe("GradeVisualDeEscala (T13 — previsto × realizado: apurações vs. resolvedor)", () => {
  beforeEach(() => {
    apiGetMock.mockReset();
    // `shouldAdvanceTime`: fixa `new Date()`/`Date.now()` em HOJE mas deixa os
    // temporizadores reais (usados pelo `waitFor` do Testing Library por
    // baixo) avançarem normalmente — sem isso `waitFor` trava esperando um
    // `setTimeout` que o relógio falso nunca dispara.
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.setSystemTime(HOJE);
    apiGetMock.mockImplementation(
      (caminho: string, opcoes: { params?: { query?: Record<string, unknown> } }) => {
        if (caminho === "/v1/vinculos") {
          return Promise.resolve(
            envelope([{ id: "v1", colaboradorId: "c1", empresaId: "e1", status: "ativo" }]),
          );
        }
        if (caminho === "/v1/colaboradores") {
          return Promise.resolve(envelope([{ id: "c1", nomeCompleto: "Maria Souza" }]));
        }
        if (caminho === "/v1/turnos") {
          return Promise.resolve(
            envelope([
              {
                id: "t1",
                nome: "Manhã",
                cor: "#2563EB",
                codigo: "T1",
                tipo: "diurno",
                ativo: true,
              },
            ]),
          );
        }
        if (caminho === "/v1/apuracoes") {
          return Promise.resolve(
            envelope([
              {
                vinculoId: "v1",
                colaboradorId: "c1",
                data: String(opcoes.params?.query?.de ?? ""),
                tipoDia: "util",
                turnoId: "t1",
                previstoMinutos: 480,
                trabalhadoMinutos: 480,
              },
            ]),
          );
        }
        if (caminho === "/v1/jornadas/resolver") {
          return Promise.resolve({
            data: {
              vinculoId: "v1",
              colaboradorId: "c1",
              data: String(opcoes.params?.query?.data ?? ""),
              tipoDia: "util",
              turnoId: "t1",
              posicaoCiclo: 1,
            },
            error: undefined,
          });
        }
        return Promise.resolve(envelope([]));
      },
    );
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("usa GET /v1/apuracoes só para o intervalo <= hoje, nunca ultrapassando a data corrente", async () => {
    render(<GradeVisualDeEscala />, { wrapper: envolvedor() });

    await waitFor(() => {
      const chamadasDeApuracoes = apiGetMock.mock.calls.filter(
        ([caminho]) => caminho === "/v1/apuracoes",
      );
      expect(chamadasDeApuracoes.length).toBeGreaterThan(0);
    });

    const chamadasDeApuracoes = apiGetMock.mock.calls.filter(
      ([caminho]) => caminho === "/v1/apuracoes",
    );
    for (const [, opcoes] of chamadasDeApuracoes) {
      const query = (opcoes as { params: { query: { de: string; ate: string } } }).params.query;
      expect(query.de <= "2026-07-15").toBe(true);
      expect(query.ate <= "2026-07-15").toBe(true);
    }
  });

  it("NUNCA chama resolverJornadaDoDia para uma data <= hoje (apuração já disponível)", async () => {
    render(<GradeVisualDeEscala />, { wrapper: envolvedor() });

    await waitFor(() => {
      const chamadasDeResolucao = apiGetMock.mock.calls.filter(
        ([caminho]) => caminho === "/v1/jornadas/resolver",
      );
      expect(chamadasDeResolucao.length).toBeGreaterThan(0);
    });

    const chamadasDeResolucao = apiGetMock.mock.calls.filter(
      ([caminho]) => caminho === "/v1/jornadas/resolver",
    );
    for (const [, opcoes] of chamadasDeResolucao) {
      const data = (opcoes as { params: { query: { data: string } } }).params.query.data;
      expect(data > "2026-07-15").toBe(true);
    }
  });

  it("chama resolverJornadaDoDia para TODAS as datas futuras do período visível (16..31/jul)", async () => {
    render(<GradeVisualDeEscala />, { wrapper: envolvedor() });

    await waitFor(() => {
      const datas = new Set(
        apiGetMock.mock.calls
          .filter(([caminho]) => caminho === "/v1/jornadas/resolver")
          .map(
            ([, opcoes]) => (opcoes as { params: { query: { data: string } } }).params.query.data,
          ),
      );
      expect(datas.size).toBe(16); // 16 a 31 de julho, inclusive
    });
  });
});
