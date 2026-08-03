import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PaginaDeConclusaoSaml } from "@/app/sso/concluir/pagina-de-conclusao";
import { CHAVE_SESSION_STORAGE_RETURN_TO } from "@/lib/sso/vinculo";

/**
 * Testa `PaginaDeConclusaoSaml` — mesma lacuna de cobertura do lado OIDC
 * (ver `pagina-de-conclusao-oidc.teste.tsx`), aqui para o fluxo SAML: quem
 * lê `window.location.hash` (tokens no FRAGMENTO, nunca visível a nenhum
 * servidor), limpa o fragmento da URL imediatamente, e decide entre
 * sucesso/erro com mensagem derivada do código.
 */

const substituirRota = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: substituirRota }),
}));

function respostaJson(corpo: unknown, status = 200): Response {
  return new Response(JSON.stringify(corpo), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function definirFragmento(fragmento: string): void {
  window.history.pushState(null, "", `/sso/concluir#${fragmento}`);
}

describe("PaginaDeConclusaoSaml", () => {
  let mockFetch: ReturnType<typeof vi.fn>;
  let substituirEstadoSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    substituirRota.mockReset();
    mockFetch = vi.fn();
    vi.stubGlobal("fetch", mockFetch);
    sessionStorage.clear();
    substituirEstadoSpy = vi.spyOn(window.history, "replaceState");
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    sessionStorage.clear();
    substituirEstadoSpy.mockRestore();
    window.history.pushState(null, "", "/");
  });

  it("fragmento com tokens: limpa a URL IMEDIATAMENTE (antes do fetch resolver) e navega para returnTo salvo", async () => {
    definirFragmento("accessToken=a1&refreshToken=r1&expiresIn=900");
    sessionStorage.setItem(CHAVE_SESSION_STORAGE_RETURN_TO, "/painel/aprovacoes");
    let resolverFetch!: (resposta: Response) => void;
    mockFetch.mockReturnValue(new Promise((resolve) => (resolverFetch = resolve)));

    render(<PaginaDeConclusaoSaml />);

    // O history.replaceState roda de forma SINCRONA ao montar, antes do
    // fetch (ainda pendente) resolver — prova a ordem que a correção exige.
    expect(substituirEstadoSpy).toHaveBeenCalled();
    expect(window.location.hash).toBe("");

    resolverFetch(respostaJson({ accessToken: "a1" }));
    await waitFor(() => expect(substituirRota).toHaveBeenCalledWith("/painel/aprovacoes"));

    const [, init] = mockFetch.mock.calls[0] as [string, RequestInit];
    const corpo = JSON.parse(init.body as string) as Record<string, unknown>;
    expect(corpo).toEqual({ accessToken: "a1", refreshToken: "r1", expiresIn: 900 });
  });

  it("fragmento incompleto: limpa o hash e mostra erro sem chamar a API", async () => {
    definirFragmento("accessToken=a1");

    render(<PaginaDeConclusaoSaml />);

    expect(window.location.hash).toBe("");
    await waitFor(() =>
      expect(screen.getByText(/validar sua sessão/i)).toBeInTheDocument(),
    );
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it("proxy responde erro: mostra mensagem derivada do código (não texto genérico fixo) e o hash já sumiu", async () => {
    definirFragmento("accessToken=a1&refreshToken=r1&expiresIn=900");
    mockFetch.mockResolvedValue(
      respostaJson({ type: "about:blank", title: "x", status: 401, codigo: "PONTO-AUTH-004" }, 401),
    );

    render(<PaginaDeConclusaoSaml />);

    expect(window.location.hash).toBe("");
    await waitFor(() =>
      expect(screen.getByText(/validar sua sessão/i)).toBeInTheDocument(),
    );
  });
});
