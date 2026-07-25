import type { Metadata, Viewport } from "next";
import { IBM_Plex_Mono, IBM_Plex_Sans, Schibsted_Grotesk } from "next/font/google";
import type { ReactNode } from "react";

import { CabecalhoDoAndaime } from "@/componentes/andaime/cabecalho-do-andaime";
import { ProvedorDeConsultas } from "@/componentes/provedor-de-consultas";
import { SCRIPT_ANTI_FLASH } from "@/componentes/tema/preferencia-de-tema";
import { ProvedorDeTema } from "@/componentes/tema/provedor-de-tema";

import "@/estilos/globais.css";

// Identidade visual oficial (RFC-003) — tres vozes, auto-hospedadas (sem
// chamada a CDN do Google em producao). Os pesos carregados sao exatamente os
// que tipografia.estilo.* consome em packages/contracts/design-tokens.json:
// sans/mono em 400/500/600/700, display em 500-800 (titulo de pagina usa 700,
// numero-destaque usa 600; 500/800 ficam de reserva para o logotipo e uso de
// marca fora dos estilos compostos).
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

export const metadata: Metadata = {
  title: {
    default: "SEEG Ponto",
    template: "%s · SEEG Ponto",
  },
  description:
    "Prova justa da jornada. Sistema de ponto eletronico REP-P multiempresa, em conformidade com a Portaria MTP 671/2021.",
  applicationName: "SEEG Ponto",
  robots: { index: false, follow: false },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  // Os dois esquemas sao suportados de verdade; o navegador ajusta a UI nativa.
  colorScheme: "light dark",
  // Cor de marca na UI do navegador/PWA. Literal (nao var()): e um valor de
  // metadado servido no <head>, fora do alcance do CSS dos tokens. Mesmo
  // hex de primitivo.cor.marca.600 em design-tokens.json (#4C5FCA).
  themeColor: "#4C5FCA",
};

export default function LayoutRaiz({ children }: { children: ReactNode }) {
  return (
    <html
      lang="pt-BR"
      suppressHydrationWarning
      className={`${ibmPlexSans.variable} ${ibmPlexMono.variable} ${schibstedGrotesk.variable}`}
    >
      <head>
        {/*
          Precisa ser sincrono e vir ANTES de qualquer conteudo: e ele que
          escreve data-tema no <html> antes do primeiro paint. Sem isto o
          usuario de tema escuro leva um flash branco a cada navegacao dura.
          O conteudo e uma constante do proprio codigo — nao ha entrada de
          usuario envolvida.
        */}
        <script dangerouslySetInnerHTML={{ __html: SCRIPT_ANTI_FLASH }} />
      </head>
      <body className="min-h-dvh">
        <ProvedorDeTema>
          <ProvedorDeConsultas>
            <a
              href="#conteudo"
              className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-[var(--camada-dialogo)] focus:rounded-pequeno focus:bg-fundo-superficie focus:px-4 focus:py-2 focus:text-texto-primario"
            >
              Pular para o conteudo
            </a>
            <CabecalhoDoAndaime />
            <main id="conteudo">{children}</main>
          </ProvedorDeConsultas>
        </ProvedorDeTema>
      </body>
    </html>
  );
}
