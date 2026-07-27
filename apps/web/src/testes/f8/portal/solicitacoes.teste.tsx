import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import NovaSolicitacao from "@/app/eu/solicitacoes/nova/page";
import { ErroDaApi } from "@/lib/api";

const useTiposSolicitacaoMock = vi.fn();
const mutateAsyncMock = vi.fn();
const useCriarSolicitacaoMock = vi.fn();
const useSessaoAtualMock = vi.fn();

vi.mock("@/ganchos/use-tipos-solicitacao", () => ({
  useTiposSolicitacao: (...args: unknown[]) => useTiposSolicitacaoMock(...args),
}));
vi.mock("@/ganchos/use-solicitacoes", () => ({
  useCriarSolicitacao: (...args: unknown[]) => useCriarSolicitacaoMock(...args),
}));
vi.mock("@/ganchos/use-sessao", () => ({
  useSessaoAtual: (...args: unknown[]) => useSessaoAtualMock(...args),
}));

const TIPOS = [
  {
    id: "tipo-1",
    nome: "Ajuste de ponto",
    categoria: "ajuste_ponto",
    exigeAnexo: false,
    exigeJustificativa: true,
  },
];

describe("/eu/solicitacoes/nova (T4)", () => {
  beforeEach(() => {
    useTiposSolicitacaoMock.mockReturnValue({
      data: { dados: TIPOS, paginacao: { temMais: false, limite: 200 } },
      isPending: false,
    });
    useSessaoAtualMock.mockReturnValue({ data: { colaboradorId: "c1" } });
    mutateAsyncMock.mockReset();
    useCriarSolicitacaoMock.mockReturnValue({
      mutateAsync: mutateAsyncMock,
      isPending: false,
      isError: false,
      error: null,
    });
  });

  it("submeter sem justificativa mostra erro de validação antes de chamar a API", async () => {
    const usuarioTeste = userEvent.setup();
    render(<NovaSolicitacao />);

    await usuarioTeste.click(screen.getByRole("button", { name: "Enviar solicitação" }));

    await waitFor(() =>
      expect(screen.getByText("Descreva o motivo do pedido.")).toBeInTheDocument(),
    );
    expect(mutateAsyncMock).not.toHaveBeenCalled();
  });

  it("resposta 501 (PONTO-INT-005) renderiza estado 'em breve', não uma exceção não tratada", async () => {
    const erro501 = new ErroDaApi(501, {
      type: "about:blank",
      title: "Recurso não implementado",
      status: 501,
      codigo: "PONTO-INT-005",
    });
    mutateAsyncMock.mockRejectedValue(erro501);
    useCriarSolicitacaoMock.mockReturnValue({
      mutateAsync: mutateAsyncMock,
      isPending: false,
      isError: true,
      error: erro501,
    });

    const usuarioTeste = userEvent.setup();
    render(<NovaSolicitacao />);

    await usuarioTeste.type(
      screen.getByLabelText("Justificativa"),
      "Esqueci de bater o ponto às 12h.",
    );

    // Seleciona o tipo através do Radix Select.
    await usuarioTeste.click(screen.getByRole("combobox", { name: "Tipo de solicitação" }));
    await usuarioTeste.click(await screen.findByRole("option", { name: "Ajuste de ponto" }));

    await usuarioTeste.click(screen.getByRole("button", { name: "Enviar solicitação" }));

    await waitFor(() => expect(screen.getByText("Disponível em breve")).toBeInTheDocument());
  });

  it("mockando 201, a mesma tela renderiza a confirmação com o protocolo", async () => {
    mutateAsyncMock.mockResolvedValue({ id: "s1", protocolo: "SOL-2026-0001" });

    const usuarioTeste = userEvent.setup();
    render(<NovaSolicitacao />);

    await usuarioTeste.type(
      screen.getByLabelText("Justificativa"),
      "Esqueci de bater o ponto às 12h.",
    );
    await usuarioTeste.click(screen.getByRole("combobox", { name: "Tipo de solicitação" }));
    await usuarioTeste.click(await screen.findByRole("option", { name: "Ajuste de ponto" }));
    await usuarioTeste.type(screen.getByLabelText("Data de referência"), "2026-07-20");
    await usuarioTeste.click(screen.getByRole("button", { name: "Enviar solicitação" }));

    await waitFor(() => expect(mutateAsyncMock).toHaveBeenCalled());
    await waitFor(() => expect(screen.getByText("Solicitação registrada")).toBeInTheDocument());
    expect(screen.getByText(/SOL-2026-0001/)).toBeInTheDocument();
  });
});
