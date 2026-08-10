import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import PaginaDeAprovacoes from "@/app/painel/aprovacoes/page";
import type * as ModuloDaApi from "@/lib/api";

/**
 * Tela cheia `/painel/aprovacoes` (antes só existia como widget resumido no
 * dashboard). Gate por `aprovacoes.ler`, mesmo padrão de RBAC por permissão
 * exata usado em `testes/paineis/cadastros/empresas-rbac.teste.tsx` (T4).
 */

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
      <PaginaDeAprovacoes />
    </QueryClientProvider>,
  );
}

function respostaVazia() {
  return { data: { dados: [], paginacao: { temMais: false, limite: 50 } }, error: undefined };
}

describe("PaginaDeAprovacoes (/painel/aprovacoes)", () => {
  it('sem "aprovacoes.ler", mostra o aviso de permissão necessária', () => {
    useSessaoCompletaMock.mockReturnValue({
      sessao: { permissoes: [] },
      carregando: false,
      erro: null,
    });
    apiGetMock.mockResolvedValue(respostaVazia());

    renderizar();

    expect(screen.getByText("Permissão necessária")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Aprovações" })).not.toBeInTheDocument();
  });

  it('com "aprovacoes.ler" e fila zerada, mostra o título, a contagem e o estado vazio', async () => {
    useSessaoCompletaMock.mockReturnValue({
      sessao: { permissoes: ["aprovacoes.ler"] },
      carregando: false,
      erro: null,
    });
    apiGetMock.mockResolvedValue(respostaVazia());

    renderizar();

    expect(await screen.findByRole("heading", { name: "Aprovações" })).toBeInTheDocument();
    expect(await screen.findByText("Nenhuma etapa aguardando decisão.")).toBeInTheDocument();
    expect(await screen.findByText("Fila zerada")).toBeInTheDocument();
  });

  it("lista uma etapa pendente e uma decidida recentemente, cada uma vinda de sua própria consulta filtrada por decisao", async () => {
    useSessaoCompletaMock.mockReturnValue({
      sessao: { permissoes: ["aprovacoes.ler", "aprovacoes.aprovar"] },
      carregando: false,
      erro: null,
    });
    apiGetMock.mockImplementation(async (caminho: string, opcoes: { params?: { query?: { decisao?: string } } }) => {
      if (caminho === "/v1/aprovacoes") {
        const decisao = opcoes?.params?.query?.decisao;
        if (decisao === "aprovada") {
          return {
            data: {
              dados: [
                {
                  id: "a2",
                  solicitacaoId: "s2",
                  etapa: 1,
                  papel: "gestor",
                  decisao: "aprovada",
                  decididoEm: "2026-08-08T12:00:00Z",
                },
              ],
              paginacao: { temMais: false, limite: 6 },
            },
            error: undefined,
          };
        }
        if (decisao === "reprovada") return respostaVazia();
        // consulta padrão (pendentes)
        return {
          data: {
            dados: [
              {
                id: "a1",
                solicitacaoId: "s1",
                etapa: 1,
                papel: "gestor",
                decisao: "pendente",
                prazoEm: "2026-08-15T00:00:00Z",
              },
            ],
            paginacao: { temMais: false, limite: 50 },
          },
          error: undefined,
        };
      }
      if (caminho === "/v1/solicitacoes/{solicitacaoId}") {
        return { data: { id: "s1", colaboradorId: "c1", tipoSolicitacaoId: "t1" }, error: undefined };
      }
      return respostaVazia();
    });

    renderizar();

    expect(await screen.findByText("1 etapa aguardando decisão.")).toBeInTheDocument();
    expect(await screen.findByText("Decididas recentemente")).toBeInTheDocument();
  });
});
