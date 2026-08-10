import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PaginaDeLogin } from "@/componentes/sessao/pagina-de-login";
import { ProvedorDeTema } from "@/componentes/tema/provedor-de-tema";
import type * as ModuloDaApi from "@/lib/api";

const substituirRota = vi.fn();
let parametrosDeBuscaAtuais = new URLSearchParams();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: substituirRota }),
  useSearchParams: () => parametrosDeBuscaAtuais,
}));

const chamarLoginMock = vi.fn();
const chamarRefreshMock = vi.fn();
const chamarLogoutMock = vi.fn();
const chamarVerificarSegundoFatorMock = vi.fn();

vi.mock("@/lib/sessao/cliente-de-sessao", () => ({
  chamarLogin: (...args: unknown[]) => chamarLoginMock(...args),
  chamarVerificarSegundoFator: (...args: unknown[]) => chamarVerificarSegundoFatorMock(...args),
  chamarRefresh: (...args: unknown[]) => chamarRefreshMock(...args),
  chamarLogout: (...args: unknown[]) => chamarLogoutMock(...args),
}));

const apiGetMock = vi.fn();

vi.mock("@/lib/api", async (importarOriginal) => {
  const original = await importarOriginal<typeof ModuloDaApi>();
  return {
    ...original,
    api: { ...original.api, GET: (...args: unknown[]) => apiGetMock(...args) },
  };
});

const TENANT = { slug: "acme", nomeExibicao: "Acme Ltda" };
const USUARIO = { id: "u1", nome: "Maria", email: "maria@exemplo.com" };

function renderizar() {
  const cliente = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <ProvedorDeTema>
      <QueryClientProvider client={cliente}>
        <PaginaDeLogin />
      </QueryClientProvider>
    </ProvedorDeTema>,
  );
}

describe("PaginaDeLogin (T1) — returnTo e fluxo de credenciais", () => {
  beforeEach(() => {
    substituirRota.mockReset();
    chamarLoginMock.mockReset();
    chamarRefreshMock.mockReset();
    chamarLogoutMock.mockReset();
    chamarVerificarSegundoFatorMock.mockReset();
    apiGetMock.mockReset();

    chamarRefreshMock.mockRejectedValue(new Error("sem cookie"));
    apiGetMock.mockResolvedValue({ data: undefined, error: { codigo: "PONTO-TEN-001" } });
    parametrosDeBuscaAtuais = new URLSearchParams();
  });

  it("login válido sem returnTo navega para /eu", async () => {
    chamarLoginMock.mockResolvedValue({
      mfaRequerido: false,
      accessToken: "t1",
      expiresIn: 900,
      usuario: USUARIO,
      tenant: TENANT,
    });

    const usuarioTeste = userEvent.setup();
    renderizar();

    await waitFor(() => expect(screen.getByLabelText("E-mail")).toBeInTheDocument());
    await usuarioTeste.type(screen.getByLabelText("E-mail"), "maria@exemplo.com");
    await usuarioTeste.type(screen.getByLabelText("Senha"), "senha-correta-123");
    await usuarioTeste.click(screen.getByRole("button", { name: "Entrar" }));

    await waitFor(() => expect(substituirRota).toHaveBeenCalledWith("/eu"));
  });

  it("login a partir de ?returnTo=/painel navega para /painel após sucesso", async () => {
    parametrosDeBuscaAtuais = new URLSearchParams("returnTo=/painel");
    chamarLoginMock.mockResolvedValue({
      mfaRequerido: false,
      accessToken: "t1",
      expiresIn: 900,
      usuario: USUARIO,
      tenant: TENANT,
    });

    const usuarioTeste = userEvent.setup();
    renderizar();

    await waitFor(() => expect(screen.getByLabelText("E-mail")).toBeInTheDocument());
    await usuarioTeste.type(screen.getByLabelText("E-mail"), "maria@exemplo.com");
    await usuarioTeste.type(screen.getByLabelText("Senha"), "senha-correta-123");
    await usuarioTeste.click(screen.getByRole("button", { name: "Entrar" }));

    await waitFor(() => expect(substituirRota).toHaveBeenCalledWith("/painel"));
  });

  it.each(["//evil.com", "https://evil.com"])(
    "returnTo=%s é rejeitado e tratado como ausente (navega para /eu)",
    async (alvoMalicioso) => {
      parametrosDeBuscaAtuais = new URLSearchParams({ returnTo: alvoMalicioso });
      chamarLoginMock.mockResolvedValue({
        mfaRequerido: false,
        accessToken: "t1",
        expiresIn: 900,
        usuario: USUARIO,
        tenant: TENANT,
      });

      const usuarioTeste = userEvent.setup();
      renderizar();

      await waitFor(() => expect(screen.getByLabelText("E-mail")).toBeInTheDocument());
      await usuarioTeste.type(screen.getByLabelText("E-mail"), "maria@exemplo.com");
      await usuarioTeste.type(screen.getByLabelText("Senha"), "senha-correta-123");
      await usuarioTeste.click(screen.getByRole("button", { name: "Entrar" }));

      await waitFor(() => expect(substituirRota).toHaveBeenCalledWith("/eu"));
    },
  );

  it("credencial inválida mostra a mensagem mapeada (PONTO-AUTH-001) sem navegar", async () => {
    const { ErroDaApi } = await import("@/lib/api");
    chamarLoginMock.mockRejectedValue(
      new ErroDaApi(401, {
        type: "about:blank",
        title: "Credenciais inválidas",
        status: 401,
        codigo: "PONTO-AUTH-001",
      }),
    );

    const usuarioTeste = userEvent.setup();
    renderizar();

    await waitFor(() => expect(screen.getByLabelText("E-mail")).toBeInTheDocument());
    await usuarioTeste.type(screen.getByLabelText("E-mail"), "maria@exemplo.com");
    await usuarioTeste.type(screen.getByLabelText("Senha"), "senha-errada");
    await usuarioTeste.click(screen.getByRole("button", { name: "Entrar" }));

    await waitFor(() =>
      expect(screen.getByText("E-mail ou senha incorretos.")).toBeInTheDocument(),
    );
    expect(substituirRota).not.toHaveBeenCalled();
  });
});
