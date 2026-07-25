import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";

import { CabecalhoDoAndaime } from "@/componentes/andaime/cabecalho-do-andaime";
import { ProvedorDeConsultas } from "@/componentes/provedor-de-consultas";
import { SCRIPT_ANTI_FLASH } from "@/componentes/tema/preferencia-de-tema";
import { ProvedorDeTema } from "@/componentes/tema/provedor-de-tema";

import "@/estilos/globais.css";

export const metadata: Metadata = {
  title: {
    default: "Ponto Eletronico",
    template: "%s · Ponto Eletronico",
  },
  description:
    "Sistema de ponto eletronico REP-P multiempresa, em conformidade com a Portaria MTP 671/2021.",
  applicationName: "Ponto Eletronico",
  robots: { index: false, follow: false },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  // Os dois esquemas sao suportados de verdade; o navegador ajusta a UI nativa.
  colorScheme: "light dark",
};

export default function LayoutRaiz({ children }: { children: ReactNode }) {
  return (
    <html lang="pt-BR" suppressHydrationWarning>
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
