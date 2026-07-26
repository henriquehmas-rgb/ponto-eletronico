import type { StorybookConfig } from "@storybook/nextjs";

/**
 * Configuracao do Storybook (F9a — Design System).
 *
 * Framework `@storybook/nextjs`: reaproveita o webpack do Next.js 15, o que
 * inclui o suporte a `next/font` (a fonte auto-hospedada e mockada no build do
 * Storybook, sem chamada de rede) e ao PostCSS/Tailwind v4 ja configurados em
 * `postcss.config.mjs`. Nenhuma configuracao de tema mora aqui — isso e
 * `.storybook/preview.tsx`.
 */
const config: StorybookConfig = {
  stories: ["../src/**/*.mdx", "../src/**/*.stories.@(ts|tsx)"],

  addons: ["@storybook/addon-a11y"],

  framework: {
    name: "@storybook/nextjs",
    options: {},
  },

  typescript: {
    reactDocgen: "react-docgen-typescript",
  },

  staticDirs: ["../public"],

  core: {
    disableTelemetry: true,
  },
};

export default config;
