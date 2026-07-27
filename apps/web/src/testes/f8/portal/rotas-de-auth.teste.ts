import { NextRequest } from "next/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

/**
 * Testa os três Route Handlers de T1 (`api/auth/{login,refresh,logout}`) e o
 * de MFA diretamente, mockando `fetch` global — nenhum teste aqui sobe a API
 * real (T1, "Pronto quando").
 */

function respostaJson(corpo: unknown, status = 200): Response {
  return new Response(JSON.stringify(corpo), {
    status,
    headers: { "content-type": "application/json" },
  });
}

const USUARIO_EXEMPLO = {
  id: "11111111-1111-1111-1111-111111111111",
  nomeCompleto: "Maria Colaboradora",
  email: "maria@exemplo.com",
};

const SESSAO_EXEMPLO = {
  usuario: USUARIO_EXEMPLO,
  tenant: { id: "t1", slug: "acme", nomeExibicao: "Acme Ltda" },
};

describe("POST /api/auth/login", () => {
  let mockFetch: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    mockFetch = vi.fn();
    vi.stubGlobal("fetch", mockFetch);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("login com credencial válida devolve accessToken e grava o cookie httpOnly do refresh (nunca o refreshToken ao cliente)", async () => {
    mockFetch.mockImplementation(async (url: string) => {
      if (url.endsWith("/v1/auth/login")) {
        return respostaJson({
          mfaRequerido: false,
          accessToken: "access-123",
          refreshToken: "refresh-secreto-456",
          expiresIn: 900,
          usuario: USUARIO_EXEMPLO,
        });
      }
      if (url.endsWith("/v1/auth/sessao")) {
        return respostaJson(SESSAO_EXEMPLO);
      }
      throw new Error(`URL inesperada: ${url}`);
    });

    const { POST } = await import("@/app/api/auth/login/route");
    const requisicao = new NextRequest("http://localhost:3000/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ email: "maria@exemplo.com", senha: "senha-correta-123" }),
      headers: { "content-type": "application/json" },
    });

    const resposta = await POST(requisicao);
    const corpo = (await resposta.json()) as Record<string, unknown>;

    expect(resposta.status).toBe(200);
    expect(corpo.accessToken).toBe("access-123");
    expect(corpo).not.toHaveProperty("refreshToken");
    expect(corpo.tenant).toEqual({ slug: "acme", nomeExibicao: "Acme Ltda" });

    const cookie = resposta.cookies.get("ponto_refresh_token");
    expect(cookie?.value).toBe("refresh-secreto-456");
    expect(cookie?.httpOnly).toBe(true);
    expect(cookie?.sameSite).toBe("lax");

    // Achado da verificação final da F8: o slug do tenant precisa ficar
    // persistido também, para um refresh silencioso futuro (sem
    // Authorization, sem corpo com tenant) ainda conseguir resolver o tenant
    // no servidor — ver `servidor/cookie.ts`.
    const cookieTenant = resposta.cookies.get("ponto_tenant");
    expect(cookieTenant?.value).toBe("acme");
    expect(cookieTenant?.httpOnly).toBe(true);
  });

  it("mfaRequerido verdadeiro não grava cookie e não expõe token nenhum", async () => {
    mockFetch.mockImplementation(async (url: string) => {
      if (url.endsWith("/v1/auth/login")) {
        return respostaJson({ mfaRequerido: true, desafioId: "desafio-1", metodosMfa: ["totp"] });
      }
      throw new Error(`URL inesperada: ${url}`);
    });

    const { POST } = await import("@/app/api/auth/login/route");
    const requisicao = new NextRequest("http://localhost:3000/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ email: "maria@exemplo.com", senha: "senha-correta-123" }),
      headers: { "content-type": "application/json" },
    });

    const resposta = await POST(requisicao);
    const corpo = (await resposta.json()) as Record<string, unknown>;

    expect(corpo).toEqual({ mfaRequerido: true, desafioId: "desafio-1", metodosMfa: ["totp"] });
    expect(resposta.cookies.get("ponto_refresh_token")).toBeUndefined();
  });

  it("login com senha errada repassa o Problema (PONTO-AUTH-001) com o mesmo status", async () => {
    mockFetch.mockImplementation(async (url: string) => {
      if (url.endsWith("/v1/auth/login")) {
        return respostaJson(
          {
            type: "about:blank",
            title: "Credenciais inválidas",
            status: 401,
            codigo: "PONTO-AUTH-001",
          },
          401,
        );
      }
      throw new Error(`URL inesperada: ${url}`);
    });

    const { POST } = await import("@/app/api/auth/login/route");
    const requisicao = new NextRequest("http://localhost:3000/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ email: "maria@exemplo.com", senha: "errada" }),
      headers: { "content-type": "application/json" },
    });

    const resposta = await POST(requisicao);
    const corpo = (await resposta.json()) as Record<string, unknown>;

    expect(resposta.status).toBe(401);
    expect(corpo.codigo).toBe("PONTO-AUTH-001");
  });

  it("encaminha X-Tenant a partir do campo tenant do corpo", async () => {
    mockFetch.mockImplementation(async (url: string, init?: RequestInit) => {
      if (url.endsWith("/v1/auth/login")) {
        const cabecalhos = new Headers(init?.headers);
        expect(cabecalhos.get("X-Tenant")).toBe("acme");
        expect(cabecalhos.get("Idempotency-Key")).toBeTruthy();
        return respostaJson({
          mfaRequerido: false,
          accessToken: "a",
          refreshToken: "r",
          expiresIn: 900,
          usuario: USUARIO_EXEMPLO,
        });
      }
      if (url.endsWith("/v1/auth/sessao")) return respostaJson(SESSAO_EXEMPLO);
      throw new Error(`URL inesperada: ${url}`);
    });

    const { POST } = await import("@/app/api/auth/login/route");
    const requisicao = new NextRequest("http://localhost:3000/api/auth/login", {
      method: "POST",
      body: JSON.stringify({
        email: "maria@exemplo.com",
        senha: "senha-correta-123",
        tenant: "acme",
      }),
      headers: { "content-type": "application/json" },
    });

    await POST(requisicao);
    expect(mockFetch).toHaveBeenCalled();
  });
});

describe("POST /api/auth/refresh", () => {
  let mockFetch: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    mockFetch = vi.fn();
    vi.stubGlobal("fetch", mockFetch);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("sem cookie devolve 401 sem chamar a API", async () => {
    const { POST } = await import("@/app/api/auth/refresh/route");
    const requisicao = new NextRequest("http://localhost:3000/api/auth/refresh", {
      method: "POST",
    });

    const resposta = await POST(requisicao);
    expect(resposta.status).toBe(401);
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it("com cookie válido renova o token e rotaciona o cookie", async () => {
    mockFetch.mockImplementation(async (url: string) => {
      if (url.endsWith("/v1/auth/refresh")) {
        return respostaJson({
          mfaRequerido: false,
          accessToken: "access-novo",
          refreshToken: "refresh-novo",
          expiresIn: 900,
          usuario: USUARIO_EXEMPLO,
        });
      }
      if (url.endsWith("/v1/auth/sessao")) return respostaJson(SESSAO_EXEMPLO);
      throw new Error(`URL inesperada: ${url}`);
    });

    const { POST } = await import("@/app/api/auth/refresh/route");
    const requisicao = new NextRequest("http://localhost:3000/api/auth/refresh", {
      method: "POST",
      headers: { cookie: "ponto_refresh_token=refresh-antigo; ponto_tenant=acme" },
    });

    const resposta = await POST(requisicao);
    const corpo = (await resposta.json()) as Record<string, unknown>;

    expect(resposta.status).toBe(200);
    expect(corpo.accessToken).toBe("access-novo");
    expect(resposta.cookies.get("ponto_refresh_token")?.value).toBe("refresh-novo");
    expect(resposta.cookies.get("ponto_tenant")?.value).toBe("acme");
  });

  it("encaminha X-Tenant a partir do cookie ponto_tenant (achado da verificação final: RefreshRequisicao não tem campo tenant, e esta chamada não tem Authorization)", async () => {
    mockFetch.mockImplementation(async (url: string, init?: RequestInit) => {
      if (url.endsWith("/v1/auth/refresh")) {
        const cabecalhos = new Headers(init?.headers);
        expect(cabecalhos.get("X-Tenant")).toBe("acme");
        return respostaJson({
          mfaRequerido: false,
          accessToken: "access-novo",
          refreshToken: "refresh-novo",
          expiresIn: 900,
          usuario: USUARIO_EXEMPLO,
        });
      }
      if (url.endsWith("/v1/auth/sessao")) return respostaJson(SESSAO_EXEMPLO);
      throw new Error(`URL inesperada: ${url}`);
    });

    const { POST } = await import("@/app/api/auth/refresh/route");
    const requisicao = new NextRequest("http://localhost:3000/api/auth/refresh", {
      method: "POST",
      headers: { cookie: "ponto_refresh_token=refresh-antigo; ponto_tenant=acme" },
    });

    await POST(requisicao);
    expect(mockFetch).toHaveBeenCalled();
  });

  it("reuso de refresh token (401 upstream) limpa os dois cookies locais", async () => {
    mockFetch.mockImplementation(async (url: string) => {
      if (url.endsWith("/v1/auth/refresh")) {
        return respostaJson(
          { type: "about:blank", title: "Token inválido", status: 401, codigo: "PONTO-AUTH-005" },
          401,
        );
      }
      throw new Error(`URL inesperada: ${url}`);
    });

    const { POST } = await import("@/app/api/auth/refresh/route");
    const requisicao = new NextRequest("http://localhost:3000/api/auth/refresh", {
      method: "POST",
      headers: { cookie: "ponto_refresh_token=refresh-ja-usado; ponto_tenant=acme" },
    });

    const resposta = await POST(requisicao);
    expect(resposta.status).toBe(401);
    expect(resposta.cookies.get("ponto_refresh_token")?.value).toBe("");
    expect(resposta.cookies.get("ponto_tenant")?.value).toBe("");
  });
});

describe("POST /api/auth/logout", () => {
  let mockFetch: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    mockFetch = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", mockFetch);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("limpa os dois cookies e devolve 204 mesmo sem cookie prévio", async () => {
    const { POST } = await import("@/app/api/auth/logout/route");
    const requisicao = new NextRequest("http://localhost:3000/api/auth/logout", { method: "POST" });

    const resposta = await POST(requisicao);
    expect(resposta.status).toBe(204);
    expect(resposta.cookies.get("ponto_refresh_token")?.value).toBe("");
    expect(resposta.cookies.get("ponto_tenant")?.value).toBe("");
  });

  it("encaminha X-Tenant a partir do cookie ponto_tenant quando não há Authorization", async () => {
    mockFetch.mockImplementation(async (_url: string, init?: RequestInit) => {
      const cabecalhos = new Headers(init?.headers);
      expect(cabecalhos.get("X-Tenant")).toBe("acme");
      return new Response(null, { status: 204 });
    });

    const { POST } = await import("@/app/api/auth/logout/route");
    const requisicao = new NextRequest("http://localhost:3000/api/auth/logout", {
      method: "POST",
      headers: { cookie: "ponto_refresh_token=refresh-abc; ponto_tenant=acme" },
    });

    await POST(requisicao);
    expect(mockFetch).toHaveBeenCalled();
  });

  it("limpa o cookie mesmo quando a chamada upstream falha (rede fora do ar)", async () => {
    mockFetch.mockRejectedValue(new Error("rede indisponível"));

    const { POST } = await import("@/app/api/auth/logout/route");
    const requisicao = new NextRequest("http://localhost:3000/api/auth/logout", {
      method: "POST",
      headers: { cookie: "ponto_refresh_token=refresh-abc" },
    });

    const resposta = await POST(requisicao);
    expect(resposta.status).toBe(204);
    expect(resposta.cookies.get("ponto_refresh_token")?.value).toBe("");
  });
});
