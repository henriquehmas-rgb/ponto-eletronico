import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import PerfilDoColaborador from "@/app/eu/perfil/page";

const useColaboradorMock = vi.fn();
const useDispositivosMock = vi.fn();
const useSessoesAtivasMock = vi.fn();
const useRevogarSessaoMock = vi.fn();
const mutateAsyncMock = vi.fn();
const sairMock = vi.fn();
const substituirRota = vi.fn();

vi.mock("@/ganchos/use-perfil", () => ({
  useColaborador: (...args: unknown[]) => useColaboradorMock(...args),
  useDispositivos: (...args: unknown[]) => useDispositivosMock(...args),
  useSessoesAtivas: (...args: unknown[]) => useSessoesAtivasMock(...args),
  useRevogarSessao: (...args: unknown[]) => useRevogarSessaoMock(...args),
}));
vi.mock("@/lib/sessao", () => ({
  useSessao: () => ({ sair: sairMock }),
}));
vi.mock("@/componentes/tema/provedor-de-tema", () => ({
  useTema: () => ({ preferencia: "sistema", resolvido: "claro", definirPreferencia: vi.fn() }),
}));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: substituirRota }),
}));

const SESSOES = [
  {
    id: "s-atual",
    canal: "web",
    ip: "10.0.0.1",
    atual: true,
    ultimaAtividadeEm: "2026-07-26T08:00:00Z",
  },
  {
    id: "s-outra",
    canal: "mobile",
    ip: "10.0.0.2",
    atual: false,
    ultimaAtividadeEm: "2026-07-25T08:00:00Z",
  },
];

describe("/eu/perfil (T5)", () => {
  beforeEach(() => {
    mutateAsyncMock.mockReset().mockResolvedValue(undefined);
    sairMock.mockReset().mockResolvedValue(undefined);
    substituirRota.mockReset();

    useColaboradorMock.mockReturnValue({
      data: {
        nomeCompleto: "Maria Colaboradora",
        matricula: "0001",
        email: "maria@exemplo.com",
        status: "ativo",
      },
      isPending: false,
      isError: false,
      error: null,
    });
    useDispositivosMock.mockReturnValue({
      data: { dados: [], paginacao: { temMais: false, limite: 100 } },
      isPending: false,
      isError: false,
      error: null,
    });
    useSessoesAtivasMock.mockReturnValue({
      data: { dados: SESSOES, paginacao: { temMais: false, limite: 100 } },
      isPending: false,
      isError: false,
      error: null,
    });
    useRevogarSessaoMock.mockReturnValue({ mutateAsync: mutateAsyncMock, isPending: false });
  });

  it("mostra dados cadastrais e as sessões ativas, marcando a atual", () => {
    render(<PerfilDoColaborador />);

    expect(screen.getAllByText("Maria Colaboradora").length).toBeGreaterThan(0);
    expect(screen.getByText("(esta sessão)")).toBeInTheDocument();
  });

  it("revogar uma sessão diferente da atual chama a mutação e não desloga", async () => {
    const usuarioTeste = userEvent.setup();
    render(<PerfilDoColaborador />);

    const linhaOutraSessao = screen.getByText("mobile").closest("li");
    expect(linhaOutraSessao).not.toBeNull();
    await usuarioTeste.click(
      within(linhaOutraSessao as HTMLElement).getByRole("button", { name: "Revogar" }),
    );

    await waitFor(() => expect(mutateAsyncMock).toHaveBeenCalledWith("s-outra"));
    expect(sairMock).not.toHaveBeenCalled();
    expect(substituirRota).not.toHaveBeenCalled();
  });

  it("revogar a própria sessão atual desloga e volta para /", async () => {
    const usuarioTeste = userEvent.setup();
    render(<PerfilDoColaborador />);

    const linhaSessaoAtual = screen.getByText("(esta sessão)").closest("li");
    expect(linhaSessaoAtual).not.toBeNull();
    await usuarioTeste.click(
      within(linhaSessaoAtual as HTMLElement).getByRole("button", { name: "Revogar" }),
    );

    await waitFor(() => expect(mutateAsyncMock).toHaveBeenCalledWith("s-atual"));
    await waitFor(() => expect(sairMock).toHaveBeenCalled());
    await waitFor(() => expect(substituirRota).toHaveBeenCalledWith("/"));
  });
});
