# syntax=docker/dockerfile:1.7
# =============================================================================
# apps/web — Next.js 15 (App Router), saida standalone
# =============================================================================
# CONTEXTO DE BUILD: a RAIZ do monorepo, nao apps/web. Foi assim que
# infra/docker-compose.yml (`context: ..`, `dockerfile: apps/web/Dockerfile`) e
# .github/workflows/ci.yml (`context: .`, `file: apps/web/Dockerfile`) ja
# declaram. Por isso todo COPY comeca com `apps/web/`.
#
# POR QUE OS COPY SAO EXPLICITOS, e nao `COPY apps/web/ ./`:
# nao existe `.dockerignore` na raiz do monorepo, que e a raiz do contexto — e
# o Docker le o `.dockerignore` do CONTEXTO, nao o de apps/web. Um COPY do
# diretorio inteiro traria `node_modules` e `.next` da maquina de quem builda
# por cima da camada `deps`, misturando binario nativo de Windows com imagem
# Linux. Listar o que entra e a unica forma de o build ser identico aqui, no CI
# e na maquina de qualquer pessoa.
#
# Estagios:
#   base      node + pnpm, sem nada instalado
#   deps      node_modules a partir do lockfile congelado
#   dev       ALVO USADO por infra/docker-compose.dev.yml (`target: dev`)
#   builder   next build
#   runner    ALVO PADRAO (producao): so o standalone, usuario sem privilegio
#
# Contrato com o compose (nao mude sem mudar la):
#   porta 3000 · HOSTNAME 0.0.0.0 · healthcheck em GET /api/health
# =============================================================================

ARG NODE_VERSION=24-alpine

# -----------------------------------------------------------------------------
FROM node:${NODE_VERSION} AS base
ENV PNPM_HOME=/pnpm \
    PATH=/pnpm:$PATH \
    NEXT_TELEMETRY_DISABLED=1
RUN corepack enable
WORKDIR /app

# -----------------------------------------------------------------------------
# deps — camada cara, invalidada so quando package.json, .npmrc ou o lockfile
# mudam. O .npmrc entra junto: e ele que define node-linker=hoisted, sem o qual
# o rastreamento do standalone tenta criar link simbolico.
# -----------------------------------------------------------------------------
FROM base AS deps
COPY apps/web/package.json apps/web/pnpm-lock.yaml apps/web/.npmrc ./
RUN --mount=type=cache,id=pnpm-store,target=/pnpm/store \
    pnpm install --frozen-lockfile

# -----------------------------------------------------------------------------
# dev — usado por infra/docker-compose.dev.yml.
# O compose monta ../apps/web em /app e reserva volumes anonimos para
# /app/node_modules e /app/.next; por isso as dependencias PRECISAM estar
# instaladas exatamente em /app/node_modules dentro da imagem.
# Tambem monta ../packages/contracts em /contracts (somente leitura), para os
# geradores (`pnpm tokens`, `pnpm tipos:api`) enxergarem o contrato.
# -----------------------------------------------------------------------------
FROM base AS dev
ENV NODE_ENV=development \
    PORT=3000 \
    HOSTNAME=0.0.0.0 \
    WATCHPACK_POLLING=true
COPY --from=deps /app/node_modules ./node_modules
COPY apps/web/package.json apps/web/pnpm-lock.yaml apps/web/.npmrc ./
COPY apps/web/next.config.ts apps/web/tsconfig.json apps/web/postcss.config.mjs ./
COPY apps/web/eslint.config.mjs apps/web/vitest.config.ts apps/web/vitest.setup.ts ./
COPY apps/web/components.json apps/web/.prettierrc.json apps/web/.prettierignore ./
COPY apps/web/scripts ./scripts
COPY apps/web/public ./public
COPY apps/web/src ./src
EXPOSE 3000
CMD ["pnpm", "dev"]

# -----------------------------------------------------------------------------
# builder — compila. As NEXT_PUBLIC_* precisam existir AQUI: o Next as inlina
# no bundle do cliente em tempo de build, nao le do ambiente em runtime.
# -----------------------------------------------------------------------------
FROM base AS builder
ARG AMBIENTE=prd
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NODE_ENV=production \
    AMBIENTE=${AMBIENTE} \
    NEXT_PUBLIC_AMBIENTE=${AMBIENTE} \
    NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}
COPY --from=deps /app/node_modules ./node_modules
COPY apps/web/package.json apps/web/pnpm-lock.yaml apps/web/.npmrc ./
COPY apps/web/next.config.ts apps/web/tsconfig.json apps/web/postcss.config.mjs ./
COPY apps/web/public ./public
COPY apps/web/src ./src
RUN pnpm build

# -----------------------------------------------------------------------------
# runner — imagem final. Sem pnpm, sem node_modules completo, sem codigo-fonte:
# apenas o servidor standalone e os estaticos.
# -----------------------------------------------------------------------------
FROM node:${NODE_VERSION} AS runner
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0
WORKDIR /app

# O usuario `node` (uid 1000) ja vem na imagem oficial. Root nao serve HTTP.
COPY --from=builder --chown=node:node /app/.next/standalone ./
COPY --from=builder --chown=node:node /app/.next/static ./.next/static
COPY --from=builder --chown=node:node /app/public ./public

USER node
EXPOSE 3000

# Espelha o healthcheck de infra/docker-compose.yml, para `docker run` avulso
# ter o mesmo comportamento do compose.
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=5 \
    CMD node -e "fetch('http://127.0.0.1:3000/api/health').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"

# server.js e gerado por `output: "standalone"` (ver next.config.ts).
CMD ["node", "server.js"]
