"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { PortaoDePermissao } from "@/lib/permissoes";
import { cn } from "@/lib/utils";

/**
 * Sub-navegação de `/painel/escalas` (T12/T13): grade visual (índice),
 * turnos e escalas (padrões cíclicos + atribuição). A guarda de sessão já
 * acontece uma vez em `apps/web/src/app/painel/layout.tsx` (A1,
 * `CascaDoPainel`) — este layout só organiza as três sub-telas que são
 * ownership exclusivo desta seção (`apps/web/src/app/painel/escalas/**`).
 */
export default function LayoutDeEscalas({ children }: { children: ReactNode }) {
  const caminhoAtual = usePathname();

  return (
    <div className="flex flex-col gap-6">
      <header>
        <h1 className="estilo-titulo-pagina text-texto-primario">Escalas</h1>
      </header>

      <nav
        aria-label="Navegação de escalas"
        className="flex flex-wrap items-center gap-1.5 rounded-pleno bg-fundo-sutil p-1.5 w-fit"
      >
        <ItemDeSubNavegacao href="/painel/escalas" rotulo="Grade" caminhoAtual={caminhoAtual} />
        <PortaoDePermissao permissao="turnos.ler">
          <ItemDeSubNavegacao
            href="/painel/escalas/turnos"
            rotulo="Turnos"
            caminhoAtual={caminhoAtual}
          />
        </PortaoDePermissao>
        <PortaoDePermissao permissao="escalas.ler">
          <ItemDeSubNavegacao
            href="/painel/escalas/padroes"
            rotulo="Padrões de escala"
            caminhoAtual={caminhoAtual}
          />
        </PortaoDePermissao>
      </nav>

      {children}
    </div>
  );
}

function ItemDeSubNavegacao({
  href,
  rotulo,
  caminhoAtual,
}: {
  href: string;
  rotulo: string;
  caminhoAtual: string;
}) {
  const ativo = caminhoAtual === href;
  return (
    <Link
      href={href}
      aria-current={ativo ? "page" : undefined}
      className={cn(
        "estilo-rotulo rounded-pleno px-3.5 py-1.5 text-texto-secundario transition-colors duration-imediata ease-padrao hover:text-texto-primario",
        ativo && "bg-fundo-superficie text-texto-primario shadow-flutuante-chip",
      )}
    >
      {rotulo}
    </Link>
  );
}
