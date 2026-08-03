import type { Metadata } from "next";
import Link from "next/link";
import type { ReactNode } from "react";

/**
 * Layout do portal de desenvolvedor (`/desenvolvedores`, F13/A2, T7).
 *
 * Deliberadamente FORA da casca do `painel` (`CascaDoPainel`,
 * `apps/web/src/componentes/paineis/shell`): esta e uma rota publica,
 * voltada ao TIME TECNICO de integracao de um cliente (ou a um avaliador
 * externo da API), nao a tela interna de RH/gestor. Nao monta
 * `ProvedorDeSessao` (`apps/web/src/lib/sessao`) — o console "tente agora"
 * (T7) fala com `/desenvolvedores/api/sandbox`, um proxy proprio que
 * autentica server-side com credenciais de demonstracao dedicadas (nunca a
 * sessao humana de quem navega ate aqui). Ver PCF F13 §5.3, linha
 * `casca-do-painel.tsx`: "A2 nao toca aqui -- /desenvolvedores e rota
 * propria, fora da casca do painel".
 */
export const metadata: Metadata = {
  title: "Portal de desenvolvedor",
  description:
    "Documentacao interativa e sandbox da API publica do SEEG Ponto — OAuth 2.0, webhooks e integracoes.",
};

export default function LayoutDoPortalDeDesenvolvedor({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-dvh flex-col bg-fundo-base text-texto-primario">
      <header className="border-b border-borda-padrao bg-fundo-superficie">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-6 py-4">
          <Link href="/desenvolvedores" className="flex items-center gap-2">
            <span className="estilo-titulo-cartao">SEEG Ponto</span>
            <span className="rounded-pleno border border-borda-padrao bg-fundo-sutil px-2 py-0.5 estilo-legenda text-texto-secundario">
              desenvolvedores
            </span>
          </Link>
          <nav className="flex items-center gap-4 estilo-corpo text-texto-secundario">
            <a
              href="https://docs.ponto.seeg.com.br"
              target="_blank"
              rel="noreferrer"
              className="hover:text-texto-primario hover:underline"
            >
              Documentacao completa
            </a>
            <Link href="/" className="hover:text-texto-primario hover:underline">
              Entrar no sistema
            </Link>
          </nav>
        </div>
      </header>
      <main className="mx-auto w-full max-w-6xl flex-1 px-6 py-8">{children}</main>
      <footer className="border-t border-borda-padrao px-6 py-4 text-center estilo-legenda text-texto-terciario">
        API publica do SEEG Ponto — versionamento e depreciacao seguem ADR-005.
      </footer>
    </div>
  );
}
