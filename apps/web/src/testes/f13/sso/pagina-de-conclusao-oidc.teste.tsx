import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PaginaDeConclusaoOidc } from "@/app/sso/callback/[provedor]/pagina-de-conclusao";
import { CHAVE_SESSION_STORAGE_RETURN_TO, CHAVE_SESSION_STORAGE_VINCULO } from "@/lib/sso/vinculo";

/**
 * Testa `PaginaDeConclusaoOidc` — a peça que faltava na cobertura da F13
 * (achado de revisão adversarial no fechamento): os testes de Route Handler
 * (`rota-callback-oidc.teste.ts`) provam o proxy servidor a servidor, mas
 * nenhum teste montava esta página, que é quem de fato lê `code`/`state`
 * da query string e `vinculo` de `sessionStorage`, chama o proxy via
 * `fetch` do navegador, e decide entre sucesso (`router.replace`) e erro
 * (mensagem derivada do `codigo`, nunca texto genérico fixo).
 */

const substituirRota = vi.fn();
let parametrosDeBuscaAtuais = new URLSearchParams();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: substituirRota }),
  useSearchParams: () => parametrosDeBuscaAtuais,
}));

function respostaJson(corpo: unknown, status = 200): Response {
  return new Response(JSON.stringify(corpo), {
    status,
    headers: { "content-type": "application/json" },
  });
}

describe("PaginaDeConclusaoOidc", () => {
  let mockFetch: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    substituirRota.mockReset();
    mockFetch = vi.fn();
    vi.stubGlobal("fetch", mockFetch);
    sessionStorage.clear();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    sessionStorage.clear();
  });

  it("code/state na query + vinculo em sessionStorage: chama o proxy e navega para returnTo salvo", async () => {
    sessionStorage.setItem(CHAVE_SESSION_STORAGE_VINCULO, "vinculo-bruto-123");
    sessionStorage.setItem(CHAVE_SESSION_STORAGE_RETURN_TO, "/painel/aprovacoes");
    parametrosDeBuscaAtuais = new URLSearchParams({ code: "codigo-x", state: "estado-y" });
    mockFetch.mockResolvedValue(respostaJson({ accessToken: "a" }));

    render(<PaginaDeConclusaoOidc provedor="google" />);

    await waitFor(() => expect(substituirRota).toHaveBeenCalledWith("/painel/aprovacoes"));

    const [url] = mockFetch.mock.calls[0] as [string];
    expect(url).toContain("/api/auth/sso/google/callback");
    expect(url).toContain("code=codigo-x");
    expect(url).toContain("state=estado-y");
    expect(url).toContain("vinculo=vinculo-bruto-123");
    // Uso único: limpo do sessionStorage após a leitura.
    expect(sessionStorage.getItem(CHAVE_SESSION_STORAGE_VINCULO)).toBeNull();
    expect(sessionStorage.getItem(CHAVE_SESSION_STORAGE_RETURN_TO)).toBeNull();
  });

  it("sem returnTo salvo, navega para / (padrão)", async () => {
    sessionStorage.setItem(CHAVE_SESSION_STORAGE_VINCULO, "vinculo-bruto-123");
    parametrosDeBuscaAtuais = new URLSearchParams({ code: "c", state: "s" });
    mockFetch.mockResolvedValue(respostaJson({ accessToken: "a" }));

    render(<PaginaDeConclusaoOidc provedor="google" />);

    await waitFor(() => expect(substituirRota).toHaveBeenCalledWith("/"));
  });

  it("sem vinculo em sessionStorage (aba diferente/expirada): mostra erro derivado do código, nunca chama o proxy", async () => {
    parametrosDeBuscaAtuais = new URLSearchParams({ code: "c", state: "s" });

    render(<PaginaDeConclusaoOidc provedor="google" />);

    await waitFor(() =>
      expect(screen.getByText(/validar sua sessão/i)).toBeInTheDocument(),
    );
    expect(mockFetch).not.toHaveBeenCalled();
    expect(substituirRota).not.toHaveBeenCalled();
  });

  it("proxy responde erro com Problema (RFC 9457): mostra a mensagem DERIVADA do código, não um texto genérico fixo", async () => {
    sessionStorage.setItem(CHAVE_SESSION_STORAGE_VINCULO, "vinculo-bruto-123");
    parametrosDeBuscaAtuais = new URLSearchParams({ code: "c", state: "s" });
    mockFetch.mockResolvedValue(
      respostaJson(
        { type: "about:blank", title: "x", status: 404, codigo: "PONTO-TEN-001" },
        404,
      ),
    );

    render(<PaginaDeConclusaoOidc provedor="google" />);

    // Mensagem real do dicionário (`dicionario-de-erros.ts`) para PONTO-TEN-001
    // — prova que a página lê o corpo, não descarta a resposta.
    await waitFor(() =>
      expect(screen.getByText(/empresa informada/i)).toBeInTheDocument(),
    );
  });

  it('"Voltar ao login" navega para /', async () => {
    parametrosDeBuscaAtuais = new URLSearchParams();

    render(<PaginaDeConclusaoOidc provedor="google" />);

    await waitFor(() => expect(screen.getByRole("button", { name: /voltar ao login/i })).toBeInTheDocument());
    screen.getByRole("button", { name: /voltar ao login/i }).click();
    expect(substituirRota).toHaveBeenCalledWith("/");
  });
});
