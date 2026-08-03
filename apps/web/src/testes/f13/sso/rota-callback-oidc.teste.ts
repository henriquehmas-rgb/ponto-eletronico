import { NextRequest } from "next/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

/**
 * Testa `GET /api/auth/sso/[provedor]/callback` (proxy servidor a servidor
 * de `GET /v1/sso/{provedor}/callback`) diretamente, mockando `fetch`
 * global — mesmo padrão de forma de `src/testes/f8/portal/
 * rotas-de-auth.teste.ts` (F8, T1) e `src/testes/f13/portal/
 * rota-sandbox.teste.ts` (F13, A2).
 *
 * Prova o critério 11 do PCF ("o relatório final da fase prova login
 * end-to-end real... não apenas 'não bloqueado'") na camada que faltava: a
 * ponte para a sessão real do navegador (`ponto_refresh_token` httpOnly),
 * não só a emissão de tokens pela API.
 *
 * `sec-fetch-site: same-origin` em toda requisição "legítima": achado de
 * revisão adversarial no fechamento da F13 — sem essa checagem
 * (`requisicaoDeMesmaOrigem`, `lib/sessao/servidor/csrf.ts`), um site de
 * terceiros conseguiria chamar esta rota diretamente. `vinculo` (RFC-019,
 * mesmo achado): o valor bruto do vínculo de navegador que a página de
 * conclusão lê de `sessionStorage` — sem ele, o proxy nem chama a API.
 */

function respostaJson(corpo: unknown, status = 200): Response {
  return new Response(JSON.stringify(corpo), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function requisicaoMesmaOrigem(url: string): NextRequest {
  return new NextRequest(url, { headers: { "sec-fetch-site": "same-origin" } });
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

describe("GET /api/auth/sso/[provedor]/callback", () => {
  let mockFetch: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    mockFetch = vi.fn();
    vi.stubGlobal("fetch", mockFetch);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("code/state/vinculo válidos: grava o cookie httpOnly do refresh e devolve accessToken (nunca o refreshToken ao cliente)", async () => {
    mockFetch.mockImplementation(async (url: string) => {
      const bruta = url.toString();
      if (bruta.includes("/v1/sso/google/callback")) {
        const alvo = new URL(bruta);
        expect(alvo.searchParams.get("code")).toBe("codigo-de-autorizacao");
        expect(alvo.searchParams.get("state")).toBe("estado-opaco");
        expect(alvo.searchParams.get("vinculo")).toBe("vinculo-bruto-do-navegador");
        return respostaJson({
          mfaRequerido: false,
          accessToken: "access-oidc-123",
          refreshToken: "refresh-oidc-secreto",
          tokenType: "Bearer",
          expiresIn: 3600,
          usuario: USUARIO_EXEMPLO,
        });
      }
      if (bruta.endsWith("/v1/auth/sessao")) {
        return respostaJson(SESSAO_EXEMPLO);
      }
      throw new Error(`URL inesperada: ${bruta}`);
    });

    const { GET } = await import("@/app/api/auth/sso/[provedor]/callback/route");
    const requisicao = requisicaoMesmaOrigem(
      "http://localhost:3000/api/auth/sso/google/callback?code=codigo-de-autorizacao&state=estado-opaco&vinculo=vinculo-bruto-do-navegador",
    );

    const resposta = await GET(requisicao, { params: Promise.resolve({ provedor: "google" }) });
    const corpo = (await resposta.json()) as Record<string, unknown>;

    expect(resposta.status).toBe(200);
    expect(corpo.accessToken).toBe("access-oidc-123");
    expect(corpo).not.toHaveProperty("refreshToken");
    expect(corpo.tenant).toEqual({ slug: "acme", nomeExibicao: "Acme Ltda" });

    const cookie = resposta.cookies.get("ponto_refresh_token");
    expect(cookie?.value).toBe("refresh-oidc-secreto");
    expect(cookie?.httpOnly).toBe(true);
  });

  it("sem code, state ou vinculo responde 400 sem chamar a API", async () => {
    const { GET } = await import("@/app/api/auth/sso/[provedor]/callback/route");
    const requisicao = requisicaoMesmaOrigem(
      "http://localhost:3000/api/auth/sso/google/callback?code=x&state=s",
    );

    const resposta = await GET(requisicao, { params: Promise.resolve({ provedor: "google" }) });
    const corpo = (await resposta.json()) as Record<string, unknown>;

    expect(resposta.status).toBe(400);
    expect(corpo.codigo).toBe("PONTO-VAL-001");
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it("requisição de origem diferente (sec-fetch-site cross-site) responde 403 sem chamar a API", async () => {
    const { GET } = await import("@/app/api/auth/sso/[provedor]/callback/route");
    const requisicao = new NextRequest(
      "http://localhost:3000/api/auth/sso/google/callback?code=c&state=s&vinculo=v",
      { headers: { "sec-fetch-site": "cross-site" } },
    );

    const resposta = await GET(requisicao, { params: Promise.resolve({ provedor: "google" }) });
    const corpo = (await resposta.json()) as Record<string, unknown>;

    expect(resposta.status).toBe(403);
    expect(corpo.codigo).toBe("PONTO-PERM-006");
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it("provedor fora da allowlist responde 400 sem chamar a API", async () => {
    const { GET } = await import("@/app/api/auth/sso/[provedor]/callback/route");
    const requisicao = requisicaoMesmaOrigem(
      "http://localhost:3000/api/auth/sso/qualquer-coisa/callback?code=c&state=s&vinculo=v",
    );

    const resposta = await GET(requisicao, { params: Promise.resolve({ provedor: "qualquer-coisa" }) });
    const corpo = (await resposta.json()) as Record<string, unknown>;

    expect(resposta.status).toBe(400);
    expect(corpo.codigo).toBe("PONTO-VAL-001");
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it("state inválido/expirado repassa o Problema (PONTO-AUTH-004) com o mesmo status", async () => {
    mockFetch.mockImplementation(async (url: string) => {
      if (url.toString().includes("/v1/sso/google/callback")) {
        return respostaJson(
          {
            type: "about:blank",
            title: "Estado inválido",
            status: 401,
            codigo: "PONTO-AUTH-004",
          },
          401,
        );
      }
      throw new Error(`URL inesperada: ${url}`);
    });

    const { GET } = await import("@/app/api/auth/sso/[provedor]/callback/route");
    const requisicao = requisicaoMesmaOrigem(
      "http://localhost:3000/api/auth/sso/google/callback?code=x&state=adulterado&vinculo=v",
    );

    const resposta = await GET(requisicao, { params: Promise.resolve({ provedor: "google" }) });
    const corpo = (await resposta.json()) as Record<string, unknown>;

    expect(resposta.status).toBe(401);
    expect(corpo.codigo).toBe("PONTO-AUTH-004");
  });

  it("provedor vem do segmento dinâmico da rota (entra_id chama /v1/sso/entra_id/callback)", async () => {
    mockFetch.mockImplementation(async (url: string) => {
      const bruta = url.toString();
      if (bruta.includes("/v1/sso/entra_id/callback")) {
        return respostaJson({
          mfaRequerido: false,
          accessToken: "a",
          refreshToken: "r",
          tokenType: "Bearer",
          expiresIn: 900,
          usuario: USUARIO_EXEMPLO,
        });
      }
      if (bruta.endsWith("/v1/auth/sessao")) return respostaJson(SESSAO_EXEMPLO);
      throw new Error(`URL inesperada: ${bruta}`);
    });

    const { GET } = await import("@/app/api/auth/sso/[provedor]/callback/route");
    const requisicao = requisicaoMesmaOrigem(
      "http://localhost:3000/api/auth/sso/entra_id/callback?code=c&state=s&vinculo=v",
    );

    const resposta = await GET(requisicao, { params: Promise.resolve({ provedor: "entra_id" }) });
    expect(resposta.status).toBe(200);
  });
});
