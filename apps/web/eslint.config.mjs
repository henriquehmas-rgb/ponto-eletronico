import { dirname } from "node:path";
import { fileURLToPath } from "node:url";

import { FlatCompat } from "@eslint/eslintrc";

const __dirname = dirname(fileURLToPath(import.meta.url));
const compat = new FlatCompat({ baseDirectory: __dirname });

/** @type {import("eslint").Linter.Config[]} */
const config = [
  {
    ignores: [
      ".next/**",
      "node_modules/**",
      "next-env.d.ts",
      // Saida de build do Storybook (`pnpm build-storybook`): artefato
      // gerado/minificado, ja coberto por `.gitignore` — nao e codigo-fonte
      // desta fase e nao deve ser lintado.
      "storybook-static/**",
      // Arquivos gerados: a verificacao deles e "estar em dia com o contrato",
      // feita por `pnpm tokens:check` e `pnpm tipos:api:check`, nao por lint.
      "src/lib/api/tipos.gerado.ts",
      "src/estilos/tokens.gerado.css",
    ],
  },
  ...compat.extends("next/core-web-vitals", "next/typescript", "prettier"),
  {
    rules: {
      "@typescript-eslint/consistent-type-imports": "error",
      "@typescript-eslint/no-unused-vars": [
        "error",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^_" },
      ],
      eqeqeq: ["error", "smart"],
      "no-console": ["error", { allow: ["warn", "error"] }],
    },
  },
  {
    // Os geradores sao ferramentas de linha de comando: a saida deles E o
    // console. Silenciar seria pedir para rodar `pnpm tokens` no escuro.
    files: ["scripts/**/*.mjs"],
    rules: { "no-console": "off" },
  },
  {
    // Mesma razao: `.storybook/testar-estatico.mjs` e a ferramenta de linha
    // de comando que orquestra `pnpm test:storybook` (T1) — a saida dela E o
    // console, nao um log de aplicacao.
    files: [".storybook/*.mjs"],
    rules: { "no-console": "off" },
  },
];

export default config;
