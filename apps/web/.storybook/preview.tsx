import { IBM_Plex_Mono, IBM_Plex_Sans, Schibsted_Grotesk } from "next/font/google";
import { useEffect } from "react";

import type { Decorator, Preview } from "@storybook/nextjs";

import { ATRIBUTO_TEMA } from "../src/componentes/tema/preferencia-de-tema";

import "../src/estilos/globais.css";

// Mesmas tres vozes tipograficas de `src/app/layout.tsx` (identidade visual
// oficial, RFC-003). Duplicado aqui de proposito: o Storybook nao renderiza
// `layout.tsx` (fora do ownership desta fase — ver PCF F09a), mas os
// componentes usam `.estilo-*` e `--tipografia-familia-*`, que so resolvem
// para fonte de verdade quando a classe `.variable` do `next/font` esta
// aplicada num ancestral. Sem isto, toda historia cairia no fallback
// generico da pilha (system-ui) silenciosamente.
const ibmPlexSans = IBM_Plex_Sans({
  subsets: ["latin", "latin-ext"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-ibm-plex-sans",
  display: "swap",
});

const ibmPlexMono = IBM_Plex_Mono({
  subsets: ["latin", "latin-ext"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-ibm-plex-mono",
  display: "swap",
});

const schibstedGrotesk = Schibsted_Grotesk({
  subsets: ["latin", "latin-ext"],
  weight: ["500", "600", "700", "800"],
  variable: "--font-schibsted-grotesk",
  display: "swap",
});

/**
 * Decorator global de tema.
 *
 * Alterna `data-tema` no elemento raiz do preview (o `<html>` do iframe do
 * Storybook) — o MESMO mecanismo que `ProvedorDeTema` usa na aplicacao real
 * (ver `src/componentes/tema/provedor-de-tema.tsx`). Nao existe uma segunda
 * verdade sobre "esta escuro?": e sempre o atributo, nunca uma classe `.dark`
 * paralela nem um contexto React proprio criado so para o Storybook.
 *
 * O controle fica no toolbar global "Tema" (globalType `tema` abaixo), para
 * troca manual ao navegar pelas historias. A verificacao AUTOMATICA de
 * contraste/acessibilidade nos dois temas roda a parte, no test-runner
 * (`.storybook/test-runner.ts`), que alterna e testa os dois temas na mesma
 * visita — nao depende deste decorator.
 */
const AlternarTema: Decorator = (Story, contexto) => {
  const tema = contexto.globals["tema"] === "escuro" ? "escuro" : "claro";

  useEffect(() => {
    const raiz = document.documentElement;
    raiz.setAttribute(ATRIBUTO_TEMA, tema);
    raiz.style.colorScheme = tema === "escuro" ? "dark" : "light";
  }, [tema]);

  return (
    <div
      className={`${ibmPlexSans.variable} ${ibmPlexMono.variable} ${schibstedGrotesk.variable}`}
      style={{
        backgroundColor: "var(--cor-fundo-aplicacao)",
        color: "var(--cor-texto-primario)",
        minHeight: "100dvh",
        padding: "var(--espacamento-3)",
        fontFamily: "var(--tipografia-familia-sans)",
      }}
    >
      <Story />
    </div>
  );
};

const preview: Preview = {
  parameters: {
    controls: {
      matchers: {
        color: /(background|color)$/i,
        date: /Date$/i,
      },
    },
    // addon-a11y: painel manual de inspecao dentro do Storybook. O GATE
    // automatico (falhar build em violacao serious/critical) e o test-runner,
    // nao este parametro — ver `.storybook/test-runner.ts`.
    a11y: {
      test: "error",
    },
    backgrounds: { disable: true }, // o fundo vem sempre do token do tema, nunca de um picker solto.
  },
  globalTypes: {
    tema: {
      name: "Tema",
      description: "Tema claro/escuro do produto (tema.claro / tema.escuro do contrato)",
      defaultValue: "claro",
      toolbar: {
        icon: "mirror",
        items: [
          { value: "claro", title: "Tema claro", icon: "sun" },
          { value: "escuro", title: "Tema escuro", icon: "moon" },
        ],
        dynamicTitle: true,
      },
    },
  },
  decorators: [AlternarTema],
};

export default preview;
