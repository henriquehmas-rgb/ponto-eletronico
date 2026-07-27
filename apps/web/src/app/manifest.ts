import type { MetadataRoute } from "next";

// PWA instalavel (F8 aprofunda; isto ja deixa o manifesto correto desde a
// identidade visual). Cores literais aqui sao inevitaveis: o manifesto e um
// JSON estatico servido antes de qualquer CSS, sem acesso a custom property.
// Os valores sao os mesmos de packages/contracts/design-tokens.json
// (primitivo.cor.marca.600 = #4C5FCA; tema.claro.fundo.aplicacao = #F7F8FB).
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "SEEG Ponto",
    short_name: "SEEG Ponto",
    description: "Prova justa da jornada — registro de ponto REP-P multiempresa.",
    start_url: "/",
    display: "standalone",
    // "business"/"productivity" são as categorias reconhecidas mais próximas
    // de um sistema de ponto eletrônico corporativo (W3C Manifest, lista de
    // categorias conhecidas usada por lojas de app) — F8/T5.
    categories: ["business", "productivity"],
    background_color: "#F7F8FB",
    theme_color: "#4C5FCA",
    icons: [
      { src: "/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
    ],
  };
}
