import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import { GradeDeApuracao } from "@/componentes/paineis/apuracao/grade-de-apuracao";
import type * as ModuloDaApi from "@/lib/api";

/**
 * Benchmark oficial de T9 (PCF F9b §6/§8): 500 vínculos × 31 dias
 * (15.500 células) precisa navegar fluida, com o DOM mantendo a
 * virtualização (menos de 100 linhas simultâneas — mesmo padrão que
 * `src/testes/dominio/tabela-de-dados.desempenho.teste.tsx`, F9a, já provou
 * para 10.000 linhas) e a montagem/rolagem sem travar.
 *
 * Dado SINTÉTICO (autorizado pelo "pronto quando" de T9): `GET /v1/apuracoes`
 * é interceptado e devolve 500 × 31 `ApuracaoDia` de uma vez, para o mesmo
 * `GradeDeApuracao` real que a tela usa — não é uma réplica paralela da
 * grade, é o componente de produção sob dado de escala.
 */

const apiGetMock = vi.fn();

vi.mock("@/lib/api", async (importarOriginal) => {
  const original = await importarOriginal<typeof ModuloDaApi>();
  return {
    ...original,
    api: { ...original.api, GET: (...args: unknown[]) => apiGetMock(...args) },
  };
});

// RBAC não é o assunto deste benchmark — bypassa a dependência de sessão
// (T1, A1) para exercitar só a virtualização da grade (T9), mesmo padrão que
// `grade-visual.teste.tsx` (A4) já usa para o mesmo problema.
vi.mock("@/lib/permissoes", () => ({
  PortaoDePermissao: ({ children }: { children: ReactNode }) => children,
}));

// Sem isto o jsdom mede a área rolável como 0×0 (não faz layout de verdade e
// não implementa `ResizeObserver`), e `@tanstack/react-virtual` nunca
// renderiza uma linha — mesmo stub que o benchmark da F9a usa.
beforeAll(() => {
  Object.defineProperty(HTMLElement.prototype, "offsetHeight", {
    configurable: true,
    value: 560,
  });
  Object.defineProperty(HTMLElement.prototype, "offsetWidth", {
    configurable: true,
    value: 1200,
  });
});

const TOTAL_VINCULOS = 500;
const LIMITE_LINHAS_NO_DOM = 100;
const LIMITE_MONTAGEM_MS = 5000;

// Julho tem 31 dias — fixa "hoje" para que `mesAtualComoPeriodo()` (padrão da
// grade) resolva exatamente ao intervalo de 31 dias que T9 especifica.
const HOJE = new Date(2026, 6, 15, 10, 0, 0);

const TIPOS_DIA = ["util", "util", "util", "util", "util", "dsr", "folga"] as const;
const STATUS = ["apurado", "pendente", "com_ocorrencia", "fechado", "reaberto"] as const;

function paraIso(data: Date): string {
  return data.toISOString().slice(0, 10);
}

function diasDoIntervalo(de: string, ate: string): string[] {
  const dias: string[] = [];
  const cursor = new Date(`${de}T12:00:00`);
  const fim = new Date(`${ate}T12:00:00`);
  while (cursor.getTime() <= fim.getTime()) {
    dias.push(paraIso(cursor));
    cursor.setDate(cursor.getDate() + 1);
  }
  return dias;
}

function gerarApuracoesSinteticas(de: string, ate: string) {
  const dias = diasDoIntervalo(de, ate);
  const linhas: Record<string, unknown>[] = [];
  for (let vinculo = 0; vinculo < TOTAL_VINCULOS; vinculo += 1) {
    for (let indiceDia = 0; indiceDia < dias.length; indiceDia += 1) {
      const indiceCombinado = vinculo + indiceDia;
      linhas.push({
        id: `apuracao-${vinculo}-${indiceDia}`,
        vinculoId: `vinculo-${vinculo}`,
        colaboradorId: `colaborador-${vinculo}`,
        data: dias[indiceDia],
        tipoDia: TIPOS_DIA[indiceCombinado % TIPOS_DIA.length],
        status: STATUS[indiceCombinado % STATUS.length],
        previstoMinutos: 480,
        trabalhadoMinutos: 470,
        marcacoesImpares: indiceCombinado % 17 === 0,
      });
    }
  }
  return { linhas, totalDias: dias.length };
}

function envelopeVazio() {
  return {
    data: { dados: [], paginacao: { temMais: false, limite: 200, total: 0 } },
    error: undefined,
  };
}

describe("GradeDeApuracao — desempenho com 500 vínculos × 31 dias (T9)", () => {
  beforeEach(() => {
    apiGetMock.mockReset();
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.setSystemTime(HOJE);

    apiGetMock.mockImplementation(
      (caminho: string, opcoes: { params?: { query?: Record<string, unknown> } }) => {
        if (caminho === "/v1/apuracoes") {
          const cursor = opcoes.params?.query?.cursor;
          if (cursor) return Promise.resolve(envelopeVazio());
          const de = String(opcoes.params?.query?.de ?? "2026-07-01");
          const ate = String(opcoes.params?.query?.ate ?? "2026-07-31");
          const { linhas } = gerarApuracoesSinteticas(de, ate);
          return Promise.resolve({
            data: {
              dados: linhas,
              paginacao: { temMais: false, limite: 200, total: linhas.length },
            },
            error: undefined,
          });
        }
        return Promise.resolve(envelopeVazio());
      },
    );
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("monta 15.500 células virtualizadas (menos de 100 linhas no DOM) e rola sem travar", async () => {
    // Timeout do PRÓPRIO teste (vitest, 5s por padrão) — maior que o `waitFor`
    // interno E que `LIMITE_MONTAGEM_MS`, para nunca ser o teto que decide o
    // resultado: quem decide "passou"/"falhou" é a métrica registrada abaixo,
    // não o relógio do executor de testes.
    const cliente = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    const inicioMontagem = performance.now();
    render(
      <QueryClientProvider client={cliente}>
        <GradeDeApuracao />
      </QueryClientProvider>,
    );

    // `getByRole("grid")` sozinho é ambíguo: o calendário de `SeletorDePeriodo`
    // (F9a) TAMBÉM usa `role="grid"` (uma tabela HTML nativa). Só a grade de
    // dados (`TabelaDeDados`) marca `aria-rowcount` — é o seletor que
    // desambigua as duas.
    function obterGradeDeDados(): HTMLElement {
      const grades = screen.getAllByRole("grid");
      const grade = grades.find((elemento) => elemento.hasAttribute("aria-rowcount"));
      if (!grade) throw new Error("grade de dados (TabelaDeDados) não encontrada ainda");
      return grade;
    }

    await waitFor(
      () => {
        expect(obterGradeDeDados()).toHaveAttribute("aria-rowcount", String(TOTAL_VINCULOS));
      },
      { timeout: 15_000 },
    );
    const duracaoMontagemMs = performance.now() - inicioMontagem;

    const linhasNoDomAposMontagem = document.querySelectorAll(
      '[role="rowgroup"] [role="row"]',
    ).length;

    const contenedorRolavel = obterGradeDeDados();
    const inicioRolagem = performance.now();
    fireEvent.scroll(contenedorRolavel, { target: { scrollTop: 8000 } });
    const duracaoRolagemMs = performance.now() - inicioRolagem;
    const linhasNoDomAposRolagem = document.querySelectorAll(
      '[role="rowgroup"] [role="row"]',
    ).length;

    console.warn(
      `[benchmark grade de apuração] 500 vínculos × 31 dias = 15.500 células — ` +
        `montagem: ${linhasNoDomAposMontagem} linhas no DOM em ${duracaoMontagemMs.toFixed(2)}ms; ` +
        `rolagem: ${linhasNoDomAposRolagem} linhas no DOM, evento processado em ${duracaoRolagemMs.toFixed(2)}ms`,
    );

    expect(linhasNoDomAposMontagem).toBeLessThan(LIMITE_LINHAS_NO_DOM);
    expect(duracaoMontagemMs).toBeLessThan(LIMITE_MONTAGEM_MS);
    expect(linhasNoDomAposRolagem).toBeLessThan(LIMITE_LINHAS_NO_DOM);
  }, 30_000);
});
