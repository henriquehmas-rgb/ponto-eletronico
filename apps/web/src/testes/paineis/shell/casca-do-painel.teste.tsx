import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CascaDoPainel } from "@/componentes/paineis/shell/casca-do-painel";

const substituirRota = vi.fn();
let caminhoAtual = "/painel";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: substituirRota }),
  usePathname: () => caminhoAtual,
}));

const useSessaoMock = vi.fn();
vi.mock("@/lib/sessao", () => ({
  useSessao: () => useSessaoMock(),
}));

const useSessaoCompletaMock = vi.fn();
vi.mock("@/ganchos/use-sessao-completa", () => ({
  useSessaoCompleta: () => useSessaoCompletaMock(),
}));

function sessaoAutenticada(sobrescritas: Partial<ReturnType<typeof useSessaoMock>> = {}) {
  return {
    usuario: { id: "u1", nome: "Maria", email: "maria@exemplo.com" },
    tenant: { slug: "acme", nomeExibicao: "Acme" },
    autenticado: true,
    carregando: false,
    entrar: vi.fn(),
    verificarSegundoFator: vi.fn(),
    sair: vi.fn().mockResolvedValue(undefined),
    ...sobrescritas,
  };
}

describe("CascaDoPainel (T1 — guarda de rota e navegação)", () => {
  beforeEach(() => {
    substituirRota.mockReset();
    caminhoAtual = "/painel";
    useSessaoCompletaMock.mockReturnValue({
      sessao: { permissoes: [] },
      carregando: false,
      erro: null,
    });
  });

  it("sem sessão (carregando=false, autenticado=false) redireciona para /?returnTo=<rota-atual>", async () => {
    useSessaoMock.mockReturnValue(sessaoAutenticada({ autenticado: false }));

    const { container } = render(<CascaDoPainel>conteudo</CascaDoPainel>);

    await waitFor(() => expect(substituirRota).toHaveBeenCalledWith("/?returnTo=%2Fpainel"));
    // Nao renderiza a area de gestao sem sessao valida (nunca um flash de conteudo).
    expect(container.textContent).not.toContain("conteudo");
  });

  it("redireciona preservando a rota atual quando não é /painel (ex.: sub-rota)", async () => {
    caminhoAtual = "/painel/apuracao";
    useSessaoMock.mockReturnValue(sessaoAutenticada({ autenticado: false }));

    render(<CascaDoPainel>conteudo</CascaDoPainel>);

    await waitFor(() =>
      expect(substituirRota).toHaveBeenCalledWith("/?returnTo=%2Fpainel%2Fapuracao"),
    );
  });

  it("carregando=true mostra esqueleto, nunca redireciona", () => {
    useSessaoMock.mockReturnValue(sessaoAutenticada({ carregando: true, autenticado: false }));

    render(<CascaDoPainel>conteudo</CascaDoPainel>);

    expect(substituirRota).not.toHaveBeenCalled();
  });

  it("autenticado renderiza a navegação, o nome do usuário e o conteúdo", () => {
    useSessaoMock.mockReturnValue(sessaoAutenticada());

    render(<CascaDoPainel>conteudo-da-pagina</CascaDoPainel>);

    expect(screen.getByText("Maria")).toBeInTheDocument();
    expect(screen.getByText("conteudo-da-pagina")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Painel" })).toHaveAttribute("href", "/painel");
  });

  it("item de navegação gated some sem a permissão correspondente (RBAC por permissão, nunca por papel)", () => {
    useSessaoMock.mockReturnValue(sessaoAutenticada());
    useSessaoCompletaMock.mockReturnValue({
      sessao: { permissoes: [] },
      carregando: false,
      erro: null,
    });

    render(<CascaDoPainel>conteudo</CascaDoPainel>);

    expect(screen.queryByRole("link", { name: "Cadastros" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Apuração" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Escalas" })).not.toBeInTheDocument();
  });

  it("item de navegação aparece quando a permissão exata está presente", () => {
    useSessaoMock.mockReturnValue(sessaoAutenticada());
    useSessaoCompletaMock.mockReturnValue({
      sessao: { permissoes: ["apuracoes.ler"] },
      carregando: false,
      erro: null,
    });

    render(<CascaDoPainel>conteudo</CascaDoPainel>);

    expect(screen.getByRole("link", { name: "Apuração" })).toHaveAttribute(
      "href",
      "/painel/apuracao",
    );
    expect(screen.queryByRole("link", { name: "Cadastros" })).not.toBeInTheDocument();
  });

  it('clicar em "Sair" chama sessao.sair() e navega para "/"', async () => {
    const sessao = sessaoAutenticada();
    useSessaoMock.mockReturnValue(sessao);
    const usuarioTeste = userEvent.setup();

    render(<CascaDoPainel>conteudo</CascaDoPainel>);
    await usuarioTeste.click(screen.getByRole("button", { name: "Sair" }));

    await waitFor(() => expect(sessao.sair).toHaveBeenCalled());
    await waitFor(() => expect(substituirRota).toHaveBeenCalledWith("/"));
  });
});
