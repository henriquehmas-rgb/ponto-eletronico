import { NextRequest } from "next/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

/**
 * Testa `POST /api/auth/sso/concluir` diretamente, mockando `fetch` global
 * — mesmo padrão de forma de `src/testes/f8/portal/rotas-de-auth.teste.ts`.
 *
 * Diferente do proxy OIDC (`rota-callback-oidc.teste.ts`): aqui a API já
 * concluiu o login (SAML `POST /v1/sso/saml/acs`, ver
 * `apps/api/app/identidade/sso/saml/fluxo.py:url_conclusao_spa`) e emitiu
 * os tokens ANTES do redirecionamento — o corpo desta rota já chega com
 * `accessToken`/`refreshToken`/`expiresIn` (o que
 * `src/app/sso/concluir/pagina-de-conclusao.tsx` leu de
 * `window.location.hash`), e esta rota só precisa buscar o `usuario`
 * (`GET /v1/auth/sessao`) antes de reusar `montarRespostaAutenticada`.
 *
 * `sec-fetch-site`/`Content-Type` estritos em toda requisição "legítima":
 * achado de revisão adversarial no fechamento da F13 — sem essas duas
 * checagens (`lib/sessao/servidor/csrf.ts`), um site de terceiros
 * conseguiria montar um `<form enctype="text/plain">` cross-site cujo corpo
 * `Request.json()` aceita como JSON válido apesar do Content-Type errado,
 * plantando um cookie de sessão autenticado como o ATACANTE no navegador da
 * vítima (login-CSRF) — ver os dois testes de rejeição abaixo.
 */

function respostaJson(corpo: unknown, status = 200): Response {
  return new Response(JSON.stringify(corpo), {
    status,
    headers: { "content-type": "application/json" },
  });
}

const USUARIO_EXEMPLO = {
  id: "22222222-2222-2222-2222-222222222222",
  nomeCompleto: "João Colaborador",
  email: "joao@exemplo.com",
};

const SESSAO_EXEMPLO = {
  usuario: USUARIO_EXEMPLO,
  tenant: { id: "t2", slug: "globex", nomeExibicao: "Globex Ltda" },
};

function requisicaoConclusao(corpo: unknown, cabecalhosExtra: Record<string, string> = {}): NextRequest {
  return new NextRequest("http://localhost:3000/api/auth/sso/concluir", {
    method: "POST",
    body: JSON.stringify(corpo),
    headers: { "content-type": "application/json", "sec-fetch-site": "same-origin", ...cabecalhosExtra },
  });
}

describe("POST /api/auth/sso/concluir", () => {
  let mockFetch: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    mockFetch = vi.fn();
    vi.stubGlobal("fetch", mockFetch);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("tokens válidos: resolve o usuário via /v1/auth/sessao, grava o cookie httpOnly do refresh e nunca devolve o refreshToken", async () => {
    mockFetch.mockImplementation(async (url: string, init?: RequestInit) => {
      if (url.toString().endsWith("/v1/auth/sessao")) {
        const cabecalhos = new Headers(init?.headers);
        expect(cabecalhos.get("Authorization")).toBe("Bearer access-saml-123");
        return respostaJson(SESSAO_EXEMPLO);
      }
      throw new Error(`URL inesperada: ${url}`);
    });

    const { POST } = await import("@/app/api/auth/sso/concluir/route");
    const resposta = await POST(
      requisicaoConclusao({
        accessToken: "access-saml-123",
        refreshToken: "refresh-saml-secreto",
        expiresIn: 900,
      }),
    );
    const corpo = (await resposta.json()) as Record<string, unknown>;

    expect(resposta.status).toBe(200);
    expect(corpo.accessToken).toBe("access-saml-123");
    expect(corpo).not.toHaveProperty("refreshToken");
    expect(corpo.tenant).toEqual({ slug: "globex", nomeExibicao: "Globex Ltda" });

    const cookie = resposta.cookies.get("ponto_refresh_token");
    expect(cookie?.value).toBe("refresh-saml-secreto");
    expect(cookie?.httpOnly).toBe(true);
  });

  it("corpo sem accessToken/refreshToken/expiresIn responde 400 sem chamar a API", async () => {
    const { POST } = await import("@/app/api/auth/sso/concluir/route");
    const resposta = await POST(requisicaoConclusao({ accessToken: "so-um-campo" }));
    const corpo = (await resposta.json()) as Record<string, unknown>;

    expect(resposta.status).toBe(400);
    expect(corpo.codigo).toBe("PONTO-VAL-001");
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it("corpo não é JSON válido responde 400", async () => {
    const requisicao = new NextRequest("http://localhost:3000/api/auth/sso/concluir", {
      method: "POST",
      body: "isto nao e json",
      headers: { "content-type": "application/json", "sec-fetch-site": "same-origin" },
    });

    const { POST } = await import("@/app/api/auth/sso/concluir/route");
    const resposta = await POST(requisicao);

    expect(resposta.status).toBe(400);
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it("requisição cross-site (sec-fetch-site) responde 403 sem chamar a API — nem ler o corpo", async () => {
    const requisicao = requisicaoConclusao(
      { accessToken: "a", refreshToken: "r", expiresIn: 900 },
      { "sec-fetch-site": "cross-site" },
    );

    const { POST } = await import("@/app/api/auth/sso/concluir/route");
    const resposta = await POST(requisicao);
    const corpo = (await resposta.json()) as Record<string, unknown>;

    expect(resposta.status).toBe(403);
    expect(corpo.codigo).toBe("PONTO-PERM-006");
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it("Content-Type diferente de application/json responde 403 — bloqueia o truque de CSRF via <form enctype=text/plain>", async () => {
    const requisicao = new NextRequest("http://localhost:3000/api/auth/sso/concluir", {
      method: "POST",
      body: JSON.stringify({ accessToken: "do-atacante", refreshToken: "r", expiresIn: 900 }),
      headers: { "content-type": "text/plain;charset=UTF-8", "sec-fetch-site": "same-origin" },
    });

    const { POST } = await import("@/app/api/auth/sso/concluir/route");
    const resposta = await POST(requisicao);
    const corpo = (await resposta.json()) as Record<string, unknown>;

    expect(resposta.status).toBe(403);
    expect(corpo.codigo).toBe("PONTO-PERM-006");
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it("accessToken inválido (sessão upstream falha) responde 502, sem gravar cookie", async () => {
    mockFetch.mockResolvedValue(respostaJson({ codigo: "PONTO-AUTH-005" }, 401));

    const { POST } = await import("@/app/api/auth/sso/concluir/route");
    const resposta = await POST(
      requisicaoConclusao({
        accessToken: "access-invalido",
        refreshToken: "refresh-x",
        expiresIn: 900,
      }),
    );

    expect(resposta.status).toBe(502);
    expect(resposta.cookies.get("ponto_refresh_token")).toBeUndefined();
  });
});
