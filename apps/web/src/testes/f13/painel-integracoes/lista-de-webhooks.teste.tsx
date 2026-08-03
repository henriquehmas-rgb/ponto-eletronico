import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import { ListaDeWebhooks } from "@/componentes/paineis/integracoes/lista-de-webhooks";

/**
 * Painel de entregas — lista/CRUD de webhooks (T14, F13/A4).
 *
 * Os ganchos de `@/ganchos/use-webhooks` são mockados diretamente (mesmo
 * padrão de `apps/web/src/testes/f8/portal/solicitacoes.teste.tsx`, F8): a
 * integração final com a API real de A3 é responsabilidade dela (PCF §5.1),
 * este componente só precisa honrar o contrato de dados que o gancho expõe.
 */

/**
 * O jsdom não faz layout de verdade (`offsetHeight`/`offsetWidth` sempre 0),
 * e é essa medida que `@tanstack/react-virtual` usa para saber quantas
 * linhas cabem na janela visível — mesmo stub de
 * `testes/dominio/tabela-de-dados.teste.tsx` (F9a). O jsdom também não
 * implementa `ResizeObserver`, usado por primitivos Radix (`Checkbox`,
 * `Select`) — mesmo stub de `testes/paineis/dashboard/secao-apuracao.teste.tsx`
 * (F9a) para o mesmo problema.
 */
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
  Object.defineProperty(HTMLElement.prototype, "offsetHeight", { configurable: true, value: 600 });
  Object.defineProperty(HTMLElement.prototype, "offsetWidth", { configurable: true, value: 900 });
});

const useSessaoCompletaMock = vi.fn();
vi.mock("@/ganchos/use-sessao-completa", () => ({
  useSessaoCompleta: () => useSessaoCompletaMock(),
}));

const useWebhooksMock = vi.fn();
const criarMutateMock = vi.fn();
const atualizarMutateMock = vi.fn();
const excluirMutateMock = vi.fn();

vi.mock("@/ganchos/use-webhooks", () => ({
  useWebhooks: (...args: unknown[]) => useWebhooksMock(...args),
  useCriarWebhook: () => ({
    mutate: criarMutateMock,
    isPending: false,
    isError: false,
    error: null,
  }),
  useAtualizarWebhook: () => ({
    mutate: atualizarMutateMock,
    isPending: false,
    isError: false,
    error: null,
  }),
  useExcluirWebhook: () => ({
    mutate: excluirMutateMock,
    isPending: false,
    isError: false,
    error: null,
  }),
}));

const WEBHOOK_ATIVO = {
  id: "wh-1",
  nome: "ERP de folha",
  url: "https://erp.exemplo.com/hook",
  eventos: ["marcacao.criada", "periodo.fechado"],
  status: "ativo" as const,
  falhasConsecutivas: 0,
  ultimaEntregaEm: "2026-08-01T12:00:00Z",
};

function permitir(...permissoes: string[]) {
  useSessaoCompletaMock.mockReturnValue({
    sessao: { permissoes },
    carregando: false,
    erro: null,
  });
}

describe("ListaDeWebhooks (T14)", () => {
  beforeEach(() => {
    useWebhooksMock.mockReset();
    criarMutateMock.mockReset();
    atualizarMutateMock.mockReset();
    excluirMutateMock.mockReset();
    useWebhooksMock.mockReturnValue({
      data: { dados: [WEBHOOK_ATIVO], paginacao: { temMais: false, limite: 100 } },
      isPending: false,
      isError: false,
      error: null,
    });
    permitir("webhooks.ler", "webhooks.criar", "webhooks.editar", "webhooks.excluir");
  });

  it("lista os webhooks devolvidos por useWebhooks", () => {
    render(<ListaDeWebhooks />);
    expect(screen.getByText("ERP de folha")).toBeInTheDocument();
    expect(screen.getByText("2 assinado(s)")).toBeInTheDocument();
  });

  it('sem "webhooks.criar", o botão "Novo webhook" não aparece', () => {
    permitir("webhooks.ler");
    render(<ListaDeWebhooks />);
    expect(screen.queryByRole("button", { name: "Novo webhook" })).not.toBeInTheDocument();
  });

  it('com "webhooks.criar", criar um webhook mostra o segredo HMAC uma única vez', async () => {
    criarMutateMock.mockImplementation((_corpo, opcoes) => {
      opcoes?.onSuccess?.({
        webhook: { ...WEBHOOK_ATIVO, id: "wh-2", nome: "Novo webhook" },
        segredoHmac: "segredo-de-teste-123",
        cabecalhoAssinatura: "X-Ponto-Signature",
        formatoAssinatura: "t=<epoch>,v1=<hmac-sha256>",
      });
    });
    const usuario = userEvent.setup();
    render(<ListaDeWebhooks />);

    await usuario.click(screen.getByRole("button", { name: "Novo webhook" }));
    await usuario.type(screen.getByLabelText(/Nome/), "Novo webhook");
    await usuario.type(screen.getByLabelText(/URL de destino/), "https://exemplo.com/hook");
    await usuario.click(screen.getByRole("checkbox", { name: /Marcação criada/ }));
    await usuario.click(screen.getByRole("button", { name: "Salvar" }));

    await waitFor(() => expect(criarMutateMock).toHaveBeenCalledTimes(1));
    expect(screen.getByText("segredo-de-teste-123")).toBeInTheDocument();
    expect(screen.getByText(/aparece uma única vez/)).toBeInTheDocument();
  });

  it("excluir um webhook exige confirmação antes de chamar useExcluirWebhook", async () => {
    excluirMutateMock.mockImplementation((_id, opcoes) => {
      opcoes?.onSuccess?.();
    });
    const usuario = userEvent.setup();
    render(<ListaDeWebhooks />);

    // Botão de ação da linha abre o diálogo de confirmação (F9a §4/§9 —
    // exclusão nunca acontece direto do clique na linha).
    await usuario.click(screen.getByRole("button", { name: "Excluir" }));
    expect(excluirMutateMock).not.toHaveBeenCalled();
    const dialogo = await screen.findByRole("dialog", { name: "Excluir webhook" });
    const botaoConfirmar = within(dialogo).getByRole("button", { name: "Excluir" });
    await usuario.click(botaoConfirmar);
    await waitFor(() => expect(excluirMutateMock).toHaveBeenCalledWith("wh-1", expect.anything()));
  });
});
