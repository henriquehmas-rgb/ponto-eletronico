import type { NextConfig } from "next";

/**
 * Configuracao do Next.js — Fase 0 (andaime).
 *
 * `output: "standalone"` e requisito do Dockerfile: o estagio final copia
 * apenas `.next/standalone`, `.next/static` e `public`, e roda `node server.js`
 * sem `node_modules` completo. O `PORT` e o `HOSTNAME` vem do ambiente, como
 * o `infra/docker-compose.yml` ja define (3000 e 0.0.0.0).
 */
const nextConfig: NextConfig = {
  output: "standalone",
  reactStrictMode: true,
  poweredByHeader: false,

  // O ESLint roda como etapa propria e bloqueante do CI (`pnpm lint`) e do
  // Makefile (`make lint-web`). Rodar de novo dentro do build so duplicaria o
  // tempo e criaria uma segunda configuracao para manter em sincronia.
  eslint: { ignoreDuringBuilds: true },

  // Tipos NAO sao ignorados: `tsc --noEmit` roda no CI antes do build, e o
  // proprio build reprova em erro de tipo. Deixado explicito de proposito.
  typescript: { ignoreBuildErrors: false },
};

export default nextConfig;
