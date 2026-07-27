import { expect, test, type Page, type Route } from "@playwright/test";

/**
 * E2E do registro de ponto por webcam — T10 do PCF F08.
 *
 * NENHUM destes testes depende do backend real: toda chamada de rede que a
 * aplicação faz (`/api/auth/login`, `/api/auth/refresh`, `/v1/tenants/atual`,
 * `/v1/auth/sessao`, `/v1/marcacoes`) é interceptada por `page.route()`, sem
 * nunca tocar um servidor de verdade — a API real já está coberta pelos
 * testes de outras fases (§6, T10).
 *
 * LIMITAÇÃO CONHECIDA, DOCUMENTADA (não escondida): o dispositivo de vídeo
 * fabricado pelo Chromium via `--use-fake-device-for-media-stream` (sem
 * `--use-file-for-fake-video-capture`) é um padrão sintético SEM rosto
 * humano. O `FaceLandmarker` (T7) nunca detecta um rosto nele — o desafio de
 * prova de vida, portanto, NUNCA pode ser aprovado neste ambiente. Isso
 * significa que os cenários "captura → desafio APROVADO → sucesso" e
 * "reautenticação automática após aprovar" (ambos exigem aprovação) não
 * podem ser exercitados ponta-a-ponta aqui sem um arquivo de vídeo real com
 * um rosto (que este ambiente headless, sem câmera e sem acesso a um acervo
 * de vídeo com direito de uso, não tem como produzir) — cobertos em vez
 * disso por `src/testes/f8/webcam/fluxo-de-registro.teste.tsx`, que exercita
 * o MESMO componente de orquestração real, mockando só os ganchos de
 * câmera/prova-de-vida (não a lógica de decisão). Os dois testes abaixo que
 * dependeriam de aprovação ficam com `test.fixme` e a mesma explicação,
 * para ficar visível no relatório do Playwright em vez de simplesmente
 * ausentes.
 */

const CREDENCIAIS_DE_TESTE = { email: "colaborador.e2e@seeg.com.br", senha: "senha-de-teste-123" };

/** Cookie de refresh simulado — precisa existir para o mock ser realista: ver comentário abaixo. */
const COOKIE_DE_REFRESH_DE_TESTE = "refreshToken=refresh-e2e-de-teste";

/**
 * `NEXT_PUBLIC_API_URL` (`src/lib/api/config.ts`) aponta, por padrão, para
 * `http://localhost:8000` — uma ORIGEM DIFERENTE da do app
 * (`http://127.0.0.1:<porta>`, ver `playwright.config.ts`). As chamadas de
 * `/v1/**` do cliente `api` (`src/lib/api/cliente.ts`) mandam `Authorization`/
 * `X-Tenant`, o que faz o navegador emitir um *preflight* `OPTIONS` antes de
 * QUALQUER GET/POST entre origens diferentes — sem responder o preflight com
 * cabeçalhos CORS, o navegador recusa a chamada real no PRÓPRIO cliente
 * (`net::ERR_FAILED`), mesmo com `page.route()` respondendo a chamada em si.
 * Todo mock de `/v1/**` abaixo passa por este envelope para nunca cair nessa
 * armadilha — não é comportamento real do produto (que roda atrás do mesmo
 * domínio em produção), é só o preço de simular uma origem cruzada no teste.
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

async function mockarRedeBasica(
  page: Page,
  opcoes: { chamadasDeMarcacoes: string[] },
): Promise<void> {
  await page.route("**/api/auth/login", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      // `Set-Cookie` de propósito: `/eu/layout.tsx` (A1, T1) monta o SEU
      // PRÓPRIO `<ProvedorDeSessao>`, independente do de `/` — ao navegar
      // para `/eu/registrar` depois do login, essa segunda instância tenta
      // `chamarRefresh()` no próprio mount para restaurar a sessão a partir
      // do cookie `httpOnly` (mesmo mecanismo que faz a sessão sobreviver a
      // um F5 de página de verdade). Sem simular o cookie aqui, o mock fica
      // incompleto: o refresh da segunda instância sempre falharia e a
      // guarda de rota devolveria o colaborador para `/` num loop, mesmo
      // com o login "funcionando" — não é um bug da aplicação, é o mock
      // precisando reproduzir o mesmo contrato que o Route Handler real.
      headers: { "set-cookie": `${COOKIE_DE_REFRESH_DE_TESTE}; Path=/api/auth; HttpOnly` },
      body: JSON.stringify({
        accessToken: "token-de-teste-e2e",
        expiresIn: 900,
        usuario: {
          id: "usuario-e2e-1",
          nome: "Colaborador E2E",
          email: CREDENCIAIS_DE_TESTE.email,
        },
        tenant: { slug: "seeg", nomeExibicao: "SEEG" },
      }),
    });
  });

  await page.route("**/api/auth/refresh", async (route) => {
    const cookieRecebido = route.request().headers()["cookie"] ?? "";
    if (!cookieRecebido.includes("refreshToken=")) {
      // Sem cookie de refresh (contexto de navegador limpo, primeira visita):
      // falha silenciosamente, como o `ProvedorDeSessao` (T1) já espera.
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
    // Cookie presente (login já aconteceu numa instância anterior do
    // `ProvedorDeSessao`): simula o refresh bem-sucedido de verdade.
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      headers: {
        "set-cookie": `${COOKIE_DE_REFRESH_DE_TESTE}-rotacionado; Path=/api/auth; HttpOnly`,
      },
      body: JSON.stringify({
        accessToken: "token-de-teste-e2e-renovado",
        expiresIn: 900,
        usuario: {
          id: "usuario-e2e-1",
          nome: "Colaborador E2E",
          email: CREDENCIAIS_DE_TESTE.email,
        },
        tenant: { slug: "seeg", nomeExibicao: "SEEG" },
      }),
    });
  });

  await page.route("**/v1/tenants/atual", async (route) => {
    await comCabecalhosCors(route, {
      status: 200,
      body: JSON.stringify({ id: "tenant-1", slug: "seeg", nomeExibicao: "SEEG" }),
    });
  });

  await page.route("**/v1/auth/sessao", async (route) => {
    await comCabecalhosCors(route, {
      status: 200,
      body: JSON.stringify({
        usuario: {
          id: "usuario-e2e-1",
          nome: "Colaborador E2E",
          email: CREDENCIAIS_DE_TESTE.email,
        },
        tenant: { id: "tenant-1", slug: "seeg", nomeExibicao: "SEEG" },
        sessaoId: "sessao-e2e-1",
        perfis: ["colaborador"],
        permissoes: [],
        colaboradorId: "colaborador-e2e-1",
        expiraEm: new Date(Date.now() + 900_000).toISOString(),
      }),
    });
  });

  await page.route("**/v1/marcacoes", async (route) => {
    if (route.request().method() !== "POST") {
      await comCabecalhosCors(route, { status: 200, body: "{}" });
      return;
    }
    opcoes.chamadasDeMarcacoes.push(route.request().postData() ?? "");
    await comCabecalhosCors(route, {
      status: 201,
      body: JSON.stringify({
        marcacao: { nsr: 1, datahoraMarcacao: new Date().toISOString() },
        comprovante: { numero: "E2E-0001" },
        revisaoRequerida: false,
      }),
    });
  });
}

async function instrumentarTrilhasDeMidia(page: Page): Promise<void> {
  await page.addInitScript(() => {
    const w = window as unknown as { __trilhasCriadas: MediaStreamTrack[] };
    w.__trilhasCriadas = [];
    const original = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
    navigator.mediaDevices.getUserMedia = async (restricoes) => {
      const stream = await original(restricoes);
      w.__trilhasCriadas.push(...stream.getTracks());
      return stream;
    };
  });
}

/** Reescreve o rótulo de TODA trilha de vídeo criada, simulando um software de câmera virtual. */
async function forcarRotuloDeCameraVirtual(page: Page): Promise<void> {
  await page.addInitScript(() => {
    const original = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
    navigator.mediaDevices.getUserMedia = async (restricoes) => {
      const stream = await original(restricoes);
      for (const trilha of stream.getVideoTracks()) {
        Object.defineProperty(trilha, "label", { value: "OBS Virtual Camera", configurable: true });
      }
      return stream;
    };
  });
}

async function entrarEIrParaRegistrar(page: Page): Promise<void> {
  await page.goto("/?returnTo=%2Feu%2Fregistrar");
  await page.getByLabel("E-mail").fill(CREDENCIAIS_DE_TESTE.email);
  await page.getByLabel("Senha").fill(CREDENCIAIS_DE_TESTE.senha);
  await page.getByRole("button", { name: "Entrar" }).click();
  await page.waitForURL("**/eu/registrar");
}

test.describe("Registro de ponto por webcam (T10)", () => {
  test("captura ao vivo exibe quadros e libera a câmera ao sair da tela (T6)", async ({ page }) => {
    const chamadasDeMarcacoes: string[] = [];
    await instrumentarTrilhasDeMidia(page);
    await mockarRedeBasica(page, { chamadasDeMarcacoes });
    await entrarEIrParaRegistrar(page);

    const video = page.locator("video");
    await expect(video).toBeVisible();

    // "Começa a exibir quadros": o vídeo tem dimensão real e avançou de
    // readyState 0 (HAVE_NOTHING) para pelo menos 2 (HAVE_CURRENT_DATA).
    await expect
      .poll(async () => video.evaluate((el: HTMLVideoElement) => el.readyState), {
        timeout: 15_000,
      })
      .toBeGreaterThanOrEqual(2);
    await expect
      .poll(async () => video.evaluate((el: HTMLVideoElement) => el.videoWidth))
      .toBeGreaterThan(0);

    // Nenhum upload de arquivo é o único caminho de captura (critério 4 da §7).
    await expect(page.locator('input[type="file"]')).toHaveCount(0);

    // Navegação DENTRO do app (clique num link, não `page.goto`): precisa
    // desmontar `FluxoDeRegistro` (T9) via ciclo de vida real do React
    // dentro do MESMO documento — só assim o `useEffect` de limpeza de
    // `useCapturaWebcam` (T6) roda de verdade. `page.goto` faria um
    // carregamento de página inteiro (novo documento, novo `window`), o que
    // destrói o script de instrumentação da trilha ANTES do React ter a
    // chance de rodar a limpeza, e o teste checaria a trilha errada.
    await page.getByRole("link", { name: "Início" }).click();
    await page.waitForURL("**/eu");

    await expect
      .poll(
        async () =>
          page.evaluate(() => {
            const w = window as unknown as { __trilhasCriadas: MediaStreamTrack[] };
            return (
              w.__trilhasCriadas.length > 0 &&
              w.__trilhasCriadas.every((t) => t.readyState === "ended")
            );
          }),
        { timeout: 10_000 },
      )
      .toBe(true);
  });

  test("câmera virtual detectada bloqueia o registro sem nunca chamar a API (T8, critério 5 da §7)", async ({
    page,
  }) => {
    test.setTimeout(30_000);
    const chamadasDeMarcacoes: string[] = [];
    await forcarRotuloDeCameraVirtual(page);
    await mockarRedeBasica(page, { chamadasDeMarcacoes });
    await entrarEIrParaRegistrar(page);

    await expect(page.getByText(/câmera virtual detectada/i)).toBeVisible({ timeout: 15_000 });

    expect(chamadasDeMarcacoes).toHaveLength(0);
  });

  test("reprovar o desafio o número máximo de tentativas nunca chama a API", async ({ page }) => {
    test.setTimeout(60_000);
    const chamadasDeMarcacoes: string[] = [];
    await instrumentarTrilhasDeMidia(page);
    await mockarRedeBasica(page, { chamadasDeMarcacoes });
    await entrarEIrParaRegistrar(page);

    // Sem rosto real no dispositivo de vídeo fabricado, a prova de vida
    // esgota as 3 tentativas de forma determinística (nunca há progresso).
    await expect(page.getByText(/não foi possível confirmar o registro/i)).toBeVisible({
      timeout: 45_000,
    });

    expect(chamadasDeMarcacoes).toHaveLength(0);
  });

  test.fixme("captura → desafio aprovado → POST /v1/marcacoes → tela de sucesso — requer vídeo com rosto real (ver nota do arquivo)", async () => {
    // Não executável neste ambiente headless/sem câmera: o dispositivo de
    // vídeo fabricado pelo Chromium não contém um rosto detectável pelo
    // FaceLandmarker. Coberto por `src/testes/f8/webcam/fluxo-de-registro.teste.tsx`
    // ("captura → desafio aprovado → POST /v1/marcacoes com o corpo
    // esperado → tela de sucesso"), que exercita o mesmo componente real
    // com o gancho de prova de vida mockado apenas no resultado da
    // detecção, não na lógica de decisão (essa é testada à parte, com
    // sequências sintéticas, em `src/lib/deteccao/prova-de-vida.teste.ts`).
  });

  test.fixme("reautenticação automática após PONTO-AUTH-011 reenvia sem nova captura — requer vídeo com rosto real (ver nota do arquivo)", async () => {
    // Mesma limitação do teste acima (depende de desafio aprovado).
    // Coberto por `src/testes/f8/webcam/fluxo-de-registro.teste.tsx`
    // ("reenvia automaticamente após reautenticação (PONTO-AUTH-011), sem
    // nova captura").
  });
});
