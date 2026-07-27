import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { definirProvedorDeToken, definirTenant } from "@/lib/api";
import { ProvedorDeSessao, useSessao } from "@/lib/sessao/contexto-de-sessao";

const chamarLoginMock = vi.fn();
const chamarVerificarSegundoFatorMock = vi.fn();
const chamarRefreshMock = vi.fn();
const chamarLogoutMock = vi.fn();

vi.mock("@/lib/sessao/cliente-de-sessao", () => ({
  chamarLogin: (...args: unknown[]) => chamarLoginMock(...args),
  chamarVerificarSegundoFator: (...args: unknown[]) => chamarVerificarSegundoFatorMock(...args),
  chamarRefresh: (...args: unknown[]) => chamarRefreshMock(...args),
  chamarLogout: (...args: unknown[]) => chamarLogoutMock(...args),
}));

const TENANT = { slug: "acme", nomeExibicao: "Acme Ltda" };
const USUARIO = { id: "u1", nome: "Maria", email: "maria@exemplo.com" };

function PainelDeTeste() {
  const sessao = useSessao();
  return (
    <div>
      <p data-testid="autenticado">{String(sessao.autenticado)}</p>
      <p data-testid="carregando">{String(sessao.carregando)}</p>
      <p data-testid="usuario">{sessao.usuario?.nome ?? "sem-usuario"}</p>
      <p data-testid="tenant">{sessao.tenant?.slug ?? "sem-tenant"}</p>
      <button
        onClick={() => {
          void sessao.entrar({ email: "maria@exemplo.com", senha: "123" });
        }}
      >
        entrar
      </button>
      <button
        onClick={() => {
          void sessao.verificarSegundoFator("000000");
        }}
      >
        verificar
      </button>
      <button
        onClick={() => {
          void sessao.sair();
        }}
      >
        sair
      </button>
    </div>
  );
}

describe("ProvedorDeSessao / useSessao (T1)", () => {
  beforeEach(() => {
    chamarLoginMock.mockReset();
    chamarVerificarSegundoFatorMock.mockReset();
    chamarRefreshMock.mockReset();
    chamarLogoutMock.mockReset();
    definirProvedorDeToken(() => undefined);
    definirTenant(undefined);
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("refresh silencioso ao montar autentica quando o cookie ainda é válido", async () => {
    chamarRefreshMock.mockResolvedValue({
      mfaRequerido: false,
      accessToken: "token-1",
      expiresIn: 900,
      usuario: USUARIO,
      tenant: TENANT,
    });

    render(
      <ProvedorDeSessao>
        <PainelDeTeste />
      </ProvedorDeSessao>,
    );

    await waitFor(() => expect(screen.getByTestId("autenticado").textContent).toBe("true"));
    expect(screen.getByTestId("usuario").textContent).toBe("Maria");
    expect(screen.getByTestId("tenant").textContent).toBe("acme");
    expect(screen.getByTestId("carregando").textContent).toBe("false");
  });

  it("sem sessão prévia (refresh falha) fica não autenticado, nunca preso em carregando", async () => {
    chamarRefreshMock.mockRejectedValue(new Error("sem cookie"));

    render(
      <ProvedorDeSessao>
        <PainelDeTeste />
      </ProvedorDeSessao>,
    );

    await waitFor(() => expect(screen.getByTestId("carregando").textContent).toBe("false"));
    expect(screen.getByTestId("autenticado").textContent).toBe("false");
  });

  it("entrar() com mfaRequerido não autentica ainda, e verificarSegundoFator() conclui", async () => {
    chamarRefreshMock.mockRejectedValue(new Error("sem cookie"));
    chamarLoginMock.mockResolvedValue({
      mfaRequerido: true,
      desafioId: "desafio-1",
      metodosMfa: ["totp"],
    });
    chamarVerificarSegundoFatorMock.mockResolvedValue({
      mfaRequerido: false,
      accessToken: "token-2",
      expiresIn: 900,
      usuario: USUARIO,
      tenant: TENANT,
    });

    const usuarioTeste = userEvent.setup();
    render(
      <ProvedorDeSessao>
        <PainelDeTeste />
      </ProvedorDeSessao>,
    );
    await waitFor(() => expect(screen.getByTestId("carregando").textContent).toBe("false"));

    await usuarioTeste.click(screen.getByText("entrar"));
    await waitFor(() => expect(chamarLoginMock).toHaveBeenCalled());
    expect(screen.getByTestId("autenticado").textContent).toBe("false");

    await usuarioTeste.click(screen.getByText("verificar"));
    await waitFor(() => expect(screen.getByTestId("autenticado").textContent).toBe("true"));
    expect(chamarVerificarSegundoFatorMock).toHaveBeenCalledWith(
      expect.objectContaining({ desafioId: "desafio-1", codigo: "000000" }),
    );
  });

  it("sair() limpa o estado mesmo quando chamarLogout falha", async () => {
    chamarRefreshMock.mockResolvedValue({
      mfaRequerido: false,
      accessToken: "token-1",
      expiresIn: 900,
      usuario: USUARIO,
      tenant: TENANT,
    });
    chamarLogoutMock.mockRejectedValue(new Error("rede fora do ar"));

    const usuarioTeste = userEvent.setup();
    render(
      <ProvedorDeSessao>
        <PainelDeTeste />
      </ProvedorDeSessao>,
    );
    await waitFor(() => expect(screen.getByTestId("autenticado").textContent).toBe("true"));

    await act(async () => {
      await usuarioTeste.click(screen.getByText("sair"));
    });

    expect(screen.getByTestId("autenticado").textContent).toBe("false");
    expect(screen.getByTestId("usuario").textContent).toBe("sem-usuario");
  });
});
