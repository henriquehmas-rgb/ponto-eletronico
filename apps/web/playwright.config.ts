import { defineConfig, devices } from "@playwright/test";

/**
 * Configuração de E2E — T10 do PCF F08.
 *
 * NENHUM teste E2E desta fase depende do backend real rodando (§6, T10):
 * as chamadas de rede que a página faz (`/api/auth/**`, `/v1/auth/sessao`,
 * `/v1/marcacoes`) são interceptadas por `page.route()` dentro de cada
 * *spec* — a API real já está coberta pelos testes de outras fases. Só o
 * processo Next.js precisa estar de pé, para exercitar JavaScript de
 * verdade no navegador (getUserMedia, MediaPipe, RAF).
 *
 * Chromium com câmera falsa: `--use-fake-device-for-media-stream` fabrica
 * um dispositivo de vídeo (sem hardware real) e `--use-fake-ui-for-media-stream`
 * concede a permissão de câmera sem diálogo — os dois são necessários para
 * rodar em CI sem hardware nem interação humana.
 */
const PORTA = Number(process.env.PLAYWRIGHT_WEB_PORT ?? 3100);
const URL_BASE = `http://127.0.0.1:${PORTA}`;

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: [["list"]],
  timeout: 60_000,

  use: {
    baseURL: URL_BASE,
    trace: "retain-on-failure",
    video: "off",
  },

  projects: [
    {
      name: "chromium-camera-falsa",
      use: {
        ...devices["Desktop Chrome"],
        launchOptions: {
          args: [
            "--use-fake-device-for-media-stream",
            "--use-fake-ui-for-media-stream",
            // Sem `--use-file-for-fake-video-capture`: o padrão sintético do
            // Chromium (sem rosto real) basta para T6 (a câmera liga/mostra
            // quadros/libera ao sair) e para T8 (o rótulo do dispositivo é
            // reescrito por script de teste, não depende do conteúdo do
            // quadro). Cenários que exigem um desafio de prova de vida
            // APROVADO de verdade exigiriam um vídeo com rosto real — ver
            // nota em `e2e/registro-webcam.spec.ts`.
          ],
        },
      },
    },
  ],

  webServer: {
    // Produção (`next start`), não `next dev`, de propósito: `next dev`
    // recompila o *service worker* a cada troca de página (Fast Refresh) e o
    // plugin de injeção do `@serwist/next` (T5, A1) acusa "Multiple
    // instances of self.__SW_MANIFEST" nesse cenário — reproduzido isolando
    // o projeto numa cópia limpa, sem nenhum outro processo concorrente:
    // `next dev` falha a compilar o SW repetidamente e o servidor nunca
    // fica pronto; `next build` (compilação única) não acusa o problema
    // nenhuma vez. `pnpm build` já roda antes de `pnpm test:e2e` na
    // sequência de comandos da §8 do PCF — este `webServer` assume esse
    // build já pronto em `.next` e só sobe `next start`.
    command: `pnpm exec next start -p ${PORTA}`,
    url: URL_BASE,
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
});
