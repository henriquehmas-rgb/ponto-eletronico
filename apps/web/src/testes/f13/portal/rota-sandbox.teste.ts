import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

/**
 * Testa `POST /desenvolvedores/api/sandbox` (T7) mockando `fetch` global —
 * nenhum teste aqui sobe a API real. Mesmo padrão de forma de
 * `src/testes/f8/portal/rotas-de-auth.teste.ts` (F8, T1).
 */

function respostaJson(corpo: unknown, status = 200): Response {
  return new Response(JSON.stringify(corpo), {
    status,
    headers: { "content-type": "application/json" },
  });
}

describe("POST /desenvolvedores/api/sandbox", () => {
  let mockFetch: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    mockFetch = vi.fn();
    vi.stubGlobal("fetch", mockFetch);
    vi.stubEnv("PONTO_SANDBOX_ADMIN_SENHA", "senha-de-teste-123");
    vi.stubEnv("PONTO_SANDBOX_TENANT_SLUG", "sandbox-demo");
    vi.stubEnv("PONTO_SANDBOX_ADMIN_EMAIL", "portal-sandbox@sandbox-demo.ponto.seeg.com.br");
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
    vi.resetModules();
  });

  it("encadeia login -> criarApiClient(ambiente=sandbox) -> emitirTokenOAuth e nunca devolve o clientSecret", async () => {
    mockFetch.mockImplementation(async (url: string, init?: RequestInit) => {
      if (url.endsWith("/v1/auth/login")) {
        return respostaJson({
          mfaRequerido: false,
          accessToken: "sessao-humana-admin-demo",
          refreshToken: "refresh-nao-usado",
          expiresIn: 900,
          usuario: { id: "u1", nomeCompleto: "Admin Sandbox", email: "x@y.com" },
        });
      }
      if (url.endsWith("/v1/admin/api-clients")) {
        const corpo = JSON.parse(init?.body as string);
        expect(corpo.ambiente).toBe("sandbox");
        expect((init?.headers as Record<string, string>).Authorization).toBe(
          "Bearer sessao-humana-admin-demo",
        );
        return respostaJson(
          {
            cliente: {
              id: "cli-1",
              clientId: "client-id-publico",
              ambiente: "sandbox",
              nome: corpo.nome,
            },
            clientSecret: "segredo-em-claro-nunca-deve-sair-do-servidor",
          },
          201,
        );
      }
      if (url.endsWith("/v1/auth/token")) {
        const corpo = JSON.parse(init?.body as string);
        expect(corpo.clientId).toBe("client-id-publico");
        expect(corpo.clientSecret).toBe("segredo-em-claro-nunca-deve-sair-do-servidor");
        return respostaJson({
          accessToken: "oauth-token-final",
          tokenType: "Bearer",
          expiresIn: 3600,
          scope: corpo.scope,
        });
      }
      throw new Error(`URL inesperada: ${url}`);
    });

    const { POST } = await import("@/app/desenvolvedores/api/sandbox/route");
    const resposta = await POST();
    const corpo = await resposta.json();

    expect(resposta.status).toBe(200);
    expect(corpo.accessToken).toBe("oauth-token-final");
    expect(corpo.clientId).toBe("client-id-publico");
    expect(JSON.stringify(corpo)).not.toContain("segredo-em-claro-nunca-deve-sair-do-servidor");
    expect(mockFetch).toHaveBeenCalledTimes(3);
  });

  it("responde 503 com PONTO-INT-001 quando PONTO_SANDBOX_ADMIN_SENHA não está configurada", async () => {
    vi.unstubAllEnvs();
    vi.stubEnv("PONTO_SANDBOX_TENANT_SLUG", "sandbox-demo");

    const { POST } = await import("@/app/desenvolvedores/api/sandbox/route");
    const resposta = await POST();
    const corpo = await resposta.json();

    expect(resposta.status).toBe(503);
    expect(corpo.codigo).toBe("PONTO-INT-001");
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it("repassa o Problema (RFC 9457) quando o login do admin de demonstração falha", async () => {
    mockFetch.mockResolvedValue(
      respostaJson(
        {
          type: "about:blank",
          title: "Credenciais inválidas",
          status: 401,
          codigo: "PONTO-AUTH-001",
        },
        401,
      ),
    );

    const { POST } = await import("@/app/desenvolvedores/api/sandbox/route");
    const resposta = await POST();
    const corpo = await resposta.json();

    expect(resposta.status).toBe(401);
    expect(corpo.codigo).toBe("PONTO-AUTH-001");
  });
});
