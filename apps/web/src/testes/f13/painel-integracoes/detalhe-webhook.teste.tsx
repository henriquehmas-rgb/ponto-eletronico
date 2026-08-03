import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import { DetalheWebhook } from "@/componentes/paineis/integracoes/detalhe-webhook";

/**
 * Detalhe de webhook: configuração + histórico de entregas + reenvio manual
 * (T14, F13/A4). Mesmo padrão de mocking de
 * `lista-de-webhooks.teste.tsx` — ganchos de dados mockados, sem depender da
 * API real de A3.
 */
/** O jsdom não implementa `ResizeObserver`, usado por primitivos Radix (`Checkbox`,
 * `Select`) — mesmo stub de `testes/paineis/dashboard/secao-apuracao.teste.tsx` (F9a). */
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

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));

const useSessaoCompletaMock = vi.fn();
vi.mock("@/ganchos/use-sessao-completa", () => ({
  useSessaoCompleta: () => useSessaoCompletaMock(),
}));

const useWebhookMock = vi.fn();
const useEntregasWebhookMock = vi.fn();
const reenviarMutateMock = vi.fn();
const atualizarMutateMock = vi.fn();
const excluirMutateMock = vi.fn();

vi.mock("@/ganchos/use-webhooks", () => ({
  useWebhook: (...args: unknown[]) => useWebhookMock(...args),
  useEntregasWebhook: (...args: unknown[]) => useEntregasWebhookMock(...args),
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
  useReenviarEntregaWebhook: () => ({
    mutate: reenviarMutateMock,
    isPending: false,
    isError: false,
    error: null,
  }),
}));

const WEBHOOK = {
  id: "wh-1",
  nome: "ERP de folha",
  url: "https://erp.exemplo.com/hook",
  eventos: ["marcacao.criada", "periodo.fechado"],
  status: "ativo" as const,
  falhasConsecutivas: 3,
  ultimaEntregaEm: "2026-08-01T12:00:00Z",
};

// Códigos de evento das entregas deliberadamente DIFERENTES dos eventos
// assinados pelo webhook (`WEBHOOK.eventos`, exibidos como selos no cabeçalho)
// — evita colisão de texto na árvore renderizada, que tornaria
// `getByText`/`getByRole` ambíguos entre o selo do cabeçalho e a célula da
// tabela de entregas.
const ENTREGA_DLQ = {
  id: "entrega-dlq-1",
  webhookId: "wh-1",
  evento: "colaborador.admitido",
  tentativa: 8,
  status: "dlq" as const,
  httpStatus: 503,
  duracaoMs: 1200,
  erro: "Timeout",
  criadoEm: "2026-08-01T12:00:00Z",
};

const ENTREGA_SUCESSO = {
  id: "entrega-ok-1",
  webhookId: "wh-1",
  evento: "terminal.offline",
  tentativa: 1,
  status: "sucesso" as const,
  httpStatus: 200,
  duracaoMs: 300,
  criadoEm: "2026-08-01T13:00:00Z",
};

function permitir(...permissoes: string[]) {
  useSessaoCompletaMock.mockReturnValue({
    sessao: { permissoes },
    carregando: false,
    erro: null,
  });
}

describe("DetalheWebhook (T14)", () => {
  beforeEach(() => {
    useWebhookMock.mockReset();
    useEntregasWebhookMock.mockReset();
    reenviarMutateMock.mockReset();
    useWebhookMock.mockReturnValue({
      data: WEBHOOK,
      isPending: false,
      isError: false,
      error: null,
    });
    useEntregasWebhookMock.mockReturnValue({
      data: { dados: [ENTREGA_DLQ, ENTREGA_SUCESSO], paginacao: { temMais: false, limite: 50 } },
      isPending: false,
      isError: false,
      error: null,
    });
    permitir("webhooks.ler", "webhooks.editar", "webhooks.excluir", "webhooks.executar");
  });

  it("mostra a configuração do webhook e os eventos assinados", () => {
    render(<DetalheWebhook webhookId="wh-1" />);
    expect(screen.getByText("ERP de folha")).toBeInTheDocument();
    expect(screen.getByText("https://erp.exemplo.com/hook")).toBeInTheDocument();
    expect(screen.getByText("marcacao.criada")).toBeInTheDocument();
    expect(screen.getByText("periodo.fechado")).toBeInTheDocument();
    expect(screen.getByText(/3 falha\(s\) consecutiva\(s\)/)).toBeInTheDocument();
  });

  it('entrega em "dlq" mostra o botão Reenviar; entrega "sucesso" não mostra', () => {
    render(<DetalheWebhook webhookId="wh-1" />);
    const botoesReenviar = screen.getAllByRole("button", { name: "Reenviar" });
    expect(botoesReenviar).toHaveLength(1);
  });

  it("clicar em Reenviar chama useReenviarEntregaWebhook com o par webhookId/entregaId corretos (critério de aceite 2 — DLQ reenvia)", async () => {
    const usuario = userEvent.setup();
    render(<DetalheWebhook webhookId="wh-1" />);

    await usuario.click(screen.getByRole("button", { name: "Reenviar" }));

    await waitFor(() =>
      expect(reenviarMutateMock).toHaveBeenCalledWith(
        { webhookId: "wh-1", entregaId: "entrega-dlq-1" },
        expect.anything(),
      ),
    );
  });

  it('sem "webhooks.executar", o botão Reenviar não aparece mesmo para uma entrega em dlq', () => {
    permitir("webhooks.ler");
    render(<DetalheWebhook webhookId="wh-1" />);
    expect(screen.queryByRole("button", { name: "Reenviar" })).not.toBeInTheDocument();
  });

  it("filtro de situação reinicia o cursor e consulta o novo status", async () => {
    const usuario = userEvent.setup();
    render(<DetalheWebhook webhookId="wh-1" />);

    // `getByRole("combobox", ...)` em vez de `getByLabelText` — o rótulo
    // "Situação" por si só não é garantidamente único na árvore (o seletor
    // de situação do próprio webhook, no diálogo de edição, usa o mesmo
    // texto); o `combobox` do filtro de entregas é inequívoco.
    await usuario.click(screen.getByRole("combobox", { name: "Situação" }));
    await usuario.click(screen.getByRole("option", { name: "Dead letter queue" }));

    await waitFor(() => {
      const ultimaChamada = useEntregasWebhookMock.mock.calls.at(-1);
      expect(ultimaChamada?.[1]).toMatchObject({ status: "dlq" });
    });
  });
});
