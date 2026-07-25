import Link from "next/link";

import { AlternadorDeTema } from "@/componentes/tema/alternador-de-tema";
import { AMBIENTE } from "@/lib/api";

const ROTAS = [
  { href: "/", rotulo: "Entrar", fase: "F1" },
  { href: "/painel", rotulo: "Painel", fase: "F9b" },
  { href: "/eu", rotulo: "Eu", fase: "F8" },
] as const;

/**
 * Barra de navegacao do andaime. Existe para provar que as tres rotas sobem e
 * que a troca de tema funciona — nao e o shell do produto, que nasce na F9a.
 */
export function CabecalhoDoAndaime() {
  return (
    <header className="sticky top-0 z-[var(--camada-cabecalho)] border-b border-borda-sutil bg-fundo-superficie/95 backdrop-blur">
      <div className="mx-auto flex w-full max-w-5xl items-center gap-4 px-6 py-3">
        <span className="estilo-titulo-cartao text-texto-primario">Ponto Eletronico</span>

        <span className="estilo-legenda rounded-pleno bg-fundo-sutil px-2 py-0.5 uppercase text-texto-terciario">
          {AMBIENTE}
        </span>

        <nav aria-label="Rotas do andaime" className="ml-auto flex items-center gap-1">
          {ROTAS.map((rota) => (
            <Link
              key={rota.href}
              href={rota.href}
              className="estilo-rotulo rounded-pequeno px-3 py-2 text-texto-secundario transition-colors duration-rapida ease-padrao hover:bg-fundo-sutil hover:text-texto-primario"
            >
              {rota.rotulo}
              <span className="estilo-legenda ml-1.5 text-texto-terciario">{rota.fase}</span>
            </Link>
          ))}
        </nav>

        <AlternadorDeTema />
      </div>
    </header>
  );
}
