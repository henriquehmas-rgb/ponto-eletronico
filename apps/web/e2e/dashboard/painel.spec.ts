import { expect, test, type Page, type Route } from "@playwright/test";

/**
 * E2E do painel de RH/gestor/diretoria (T1/T2/T3 — casca, RBAC, dashboard).
 *
 * Mesmo padrão de `e2e/registro-webcam.spec.ts` (F8, T10): NENHUM destes
 * testes depende do backend real — toda chamada de rede é interceptada por
 * `page.route()`, sem tocar um servidor de verdade (a API real já é
 * verificada separadamente, por fora do Playwright, contra uma instância
 * local subida para esta fase — ver relatório da fase). Só o processo
 * Next.js precisa estar de pé (`webServer` de `playwright.config.ts`, F8/A2,
 * ownership compartilhado — não editado por esta fase).
 */

const CREDENCIAIS_DE_TESTE = { email: "gestor.e2e@seeg.com.br", senha: "senha-de-teste-123" };
const COOKIE_DE_REFRESH_DE_TESTE = "refreshToken=refresh-e2e-de-teste";

/**
 * `NEXT_PUBLIC_API_URL` aponta por padrão para uma origem diferente da do
 * app — todo mock de `/v1/**` precisa responder o preflight `OPTIONS` com
 * cabeçalhos CORS, mesma armadilha documentada em `e2e/registro-webcam.spec.ts`.
 */
async function comCabecalhosCors(
  route: Route,
  resposta: { status: number; body: string; headers?: Record<string, string> },
): Promise<void> {
  const cabecalhosCors = {
    "access-control-allow-origin": "*",
    "access-control-allow-headers": "*",
    "access-control-allow-methods": "*",
  };
  if (route.request().method() === "OPTIONS") {
    await route.fulfill({ status: 204, headers: cabecalhosCors });
    return;
  }
  await route.fulfill({
    status: resposta.status,
    contentType: "application/json",
    headers: { ...cabecalhosCors, ...(resposta.headers ?? {}) },
    body: resposta.body,
  });
}

const SESSAO_ATUAL_BASE = {
  usuario: { id: "usuario-e2e-1", nome: "Gestor E2E", email: CREDENCIAIS_DE_TESTE.email },
  tenant: { id: "tenant-1", slug: "seeg", nomeExibicao: "SEEG" },
  sessaoId: "sessao-e2e-1",
  perfis: ["gestor"],
  expiraEm: new Date(Date.now() + 900_000).toISOString(),
};

function listaVazia() {
  return JSON.stringify({ dados: [], paginacao: { temMais: false, limite: 100, total: 0 } });
}

async function mockarRedeBasica(page: Page, permissoes: string[]): Promise<void> {
  await page.route("**/api/auth/login", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      headers: { "set-cookie": `${COOKIE_DE_REFRESH_DE_TESTE}; Path=/api/auth; HttpOnly` },
      body: JSON.stringify({
        accessToken: "token-de-teste-e2e",
        expiresIn: 900,
        usuario: SESSAO_ATUAL_BASE.usuario,
        tenant: { slug: "seeg", nomeExibicao: "SEEG" },
      }),
    });
  });

  await page.route("**/api/auth/refresh", async (route) => {
    const cookieRecebido = route.request().headers()["cookie"] ?? "";
    if (!cookieRecebido.includes("refreshToken=")) {
      await route.fulfill({
        status: 401,
        contentType: "application/json",
        body: JSON.stringify({
          type: "about:blank",
          title: "Sem sessão",
          status: 401,
          codigo: "PONTO-AUTH-002",
        }),
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      headers: {
        "set-cookie": `${COOKIE_DE_REFRESH_DE_TESTE}-rotacionado; Path=/api/auth; HttpOnly`,
      },
      body: JSON.stringify({
        accessToken: "token-de-teste-e2e-renovado",
        expiresIn: 900,
        usuario: SESSAO_ATUAL_BASE.usuario,
        tenant: { slug: "seeg", nomeExibicao: "SEEG" },
      }),
    });
  });

  await page.route("**/v1/auth/sessao", async (route) => {
    await comCabecalhosCors(route, {
      status: 200,
      body: JSON.stringify({ ...SESSAO_ATUAL_BASE, permissoes }),
    });
  });

  // Todo o resto de /v1/** usado pelo dashboard (T2/T3): listas vazias
  // bastam para provar RBAC/roteamento sem depender de dado de negócio real.
  for (const caminho of [
    "**/v1/empresas",
    "**/v1/unidades",
    "**/v1/apuracoes",
    "**/v1/ocorrencias",
    "**/v1/colaboradores",
    "**/v1/marcacoes",
  ]) {
    await page.route(caminho, async (route) => {
      await comCabecalhosCors(route, { status: 200, body: listaVazia() });
    });
  }
}

test.describe("/painel — casca, RBAC no cliente e dashboard (T1/T2/T3)", () => {
  test("sem sessão, acessar /painel redireciona para /?returnTo=/painel", async ({ page }) => {
    await mockarRedeBasica(page, []);
    // Sem cookie de refresh: o refresh silencioso falha, a guarda de rota redireciona.
    await page.context().clearCookies();
    await page.goto("/painel");
    await page.waitForURL("**/?returnTo=%2Fpainel");
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  });

  test("login a partir de ?returnTo=/painel volta para /painel autenticado", async ({ page }) => {
    await mockarRedeBasica(page, ["colaboradores.ler"]);
    await page.goto("/?returnTo=%2Fpainel");
    await page.getByLabel("E-mail").fill(CREDENCIAIS_DE_TESTE.email);
    await page.getByLabel("Senha").fill(CREDENCIAIS_DE_TESTE.senha);
    await page.getByRole("button", { name: "Entrar" }).click();
    await page.waitForURL("**/painel");

    await expect(page.getByRole("heading", { name: "Painel" })).toBeVisible();
    await expect(page.getByText("Gestor E2E")).toBeVisible();
  });

  test("RBAC: sem nenhuma permissão de leitura, nenhuma seção de dado renderiza", async ({
    page,
  }) => {
    await mockarRedeBasica(page, []);
    await page.goto("/?returnTo=%2Fpainel");
    await page.getByLabel("E-mail").fill(CREDENCIAIS_DE_TESTE.email);
    await page.getByLabel("Senha").fill(CREDENCIAIS_DE_TESTE.senha);
    await page.getByRole("button", { name: "Entrar" }).click();
    await page.waitForURL("**/painel");

    await expect(page.getByRole("heading", { name: "Painel" })).toBeVisible();
    await expect(page.getByText("Banco de horas")).not.toBeVisible();
    await expect(page.getByRole("link", { name: "Apuração" })).not.toBeVisible();
    await expect(page.getByRole("link", { name: "Cadastros" })).not.toBeVisible();
  });

  test("RBAC: com apuracoes.ler, a navegação mostra o item Apuração", async ({ page }) => {
    await mockarRedeBasica(page, ["apuracoes.ler"]);
    await page.goto("/?returnTo=%2Fpainel");
    await page.getByLabel("E-mail").fill(CREDENCIAIS_DE_TESTE.email);
    await page.getByLabel("Senha").fill(CREDENCIAIS_DE_TESTE.senha);
    await page.getByRole("button", { name: "Entrar" }).click();
    await page.waitForURL("**/painel");

    await expect(page.getByRole("link", { name: "Apuração" })).toBeVisible();
  });

  test("logout a partir de /painel volta para /", async ({ page }) => {
    await mockarRedeBasica(page, []);
    await page.route("**/api/auth/logout", async (route) => {
      await route.fulfill({ status: 204 });
    });
    await page.goto("/?returnTo=%2Fpainel");
    await page.getByLabel("E-mail").fill(CREDENCIAIS_DE_TESTE.email);
    await page.getByLabel("Senha").fill(CREDENCIAIS_DE_TESTE.senha);
    await page.getByRole("button", { name: "Entrar" }).click();
    await page.waitForURL("**/painel");

    await page.getByRole("button", { name: "Sair" }).click();
    await page.waitForURL((url) => url.pathname === "/");
  });
});
