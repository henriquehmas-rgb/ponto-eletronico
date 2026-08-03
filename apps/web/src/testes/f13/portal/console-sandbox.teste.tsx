import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ConsoleSandbox } from "@/componentes/desenvolvedores/console-sandbox";

describe("ConsoleSandbox (F13/A2, T7)", () => {
  const onToken = vi.fn();

  beforeEach(() => {
    onToken.mockReset();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("chama onToken(accessToken) quando a cadeia login->criarApiClient->token funciona", async () => {
    const usuario = userEvent.setup();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          clientId: "client-sandbox-123",
          accessToken: "token-de-sandbox-abc",
          tokenType: "Bearer",
          expiresIn: 3600,
          scope: "webhooks:ler webhooks:escrever",
        }),
      }),
    );

    render(<ConsoleSandbox onToken={onToken} />);

    await usuario.click(screen.getByRole("button", { name: /criar cliente de sandbox/i }));

    await waitFor(() => {
      expect(screen.getByText(/token de sandbox emitido/i)).toBeInTheDocument();
    });

    expect(onToken).toHaveBeenCalledWith(undefined); // limpo no início da chamada
    expect(onToken).toHaveBeenCalledWith("token-de-sandbox-abc");
    expect(screen.getByText("token-de-sandbox-abc")).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledWith("/desenvolvedores/api/sandbox", { method: "POST" });
  });

  it("mostra o detalhe do erro quando o proxy devolve um Problema (RFC 9457)", async () => {
    const usuario = userEvent.setup();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 503,
        json: async () => ({
          type: "about:blank",
          title: "Sandbox não configurado neste ambiente",
          status: 503,
          codigo: "PONTO-INT-001",
          detail: "Variável de ambiente PONTO_SANDBOX_ADMIN_SENHA ausente no servidor do portal.",
        }),
      }),
    );

    render(<ConsoleSandbox onToken={onToken} />);
    await usuario.click(screen.getByRole("button", { name: /criar cliente de sandbox/i }));

    await waitFor(() => {
      expect(
        screen.getByText(/variável de ambiente ponto_sandbox_admin_senha ausente/i),
      ).toBeInTheDocument();
    });
    expect(onToken).not.toHaveBeenCalledWith(expect.stringMatching(/./));
  });

  it("desabilita o botão enquanto a chamada está em andamento", async () => {
    const usuario = userEvent.setup();
    let resolverFetch: (valor: unknown) => void = () => {};
    const promessa = new Promise((resolve) => {
      resolverFetch = resolve;
    });
    vi.stubGlobal("fetch", vi.fn().mockReturnValue(promessa));

    render(<ConsoleSandbox onToken={onToken} />);
    const botao = screen.getByRole("button", { name: /criar cliente de sandbox/i });
    await usuario.click(botao);

    expect(botao).toBeDisabled();

    resolverFetch({
      ok: true,
      status: 200,
      json: async () => ({
        clientId: "c1",
        accessToken: "tk",
        tokenType: "Bearer",
        expiresIn: 60,
        scope: "webhooks:ler",
      }),
    });

    await waitFor(() => expect(botao).not.toBeDisabled());
  });
});
