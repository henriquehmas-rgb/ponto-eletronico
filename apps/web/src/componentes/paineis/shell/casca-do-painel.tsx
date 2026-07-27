"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

import { Botao } from "@/componentes/ui/button";
import { Esqueleto } from "@/componentes/ui/skeleton";
import { PortaoDePermissao } from "@/lib/permissoes";
import { useSessao } from "@/lib/sessao";
import { cn } from "@/lib/utils";

/**
 * Casca de navegação da área de gestão (T1) — mesmo padrão estrutural de
 * `apps/web/src/app/eu/layout.tsx` (F8, `GuardaDeRota`): guarda de rota por
 * `useSessao()`, sem sessão redireciona para `/?returnTo=<rota-atual>` (nunca
 * para uma rota `/painel/entrar`, que não existe — PCF F9b §2/§9 proibição 3).
 * `ProvedorDeSessao` é montado por `apps/web/src/app/painel/layout.tsx`, que
 * envolve este componente.
 *
 * Cada item de navegação além do próprio dashboard é individualmente
 * habilitado por `<PortaoDePermissao>` (RBAC por permissão exata, nunca por
 * nome de papel — PCF F9b §6/§9 proibição 8). "Cadastros" agrupa as sete
 * telas de A2 num único item de navegação gated por `empresas.ler` (a
 * primeira delas na rota); a lista completa de cadastros e o RBAC fino
 * dentro de cada um são ownership de A2 — este componente só decide se a
 * ENTRADA do menu aparece.
 */
export function CascaDoPainel({ children }: { children: ReactNode }) {
  const sessao = useSessao();
  const router = useRouter();
  const caminhoAtual = usePathname();

  useEffect(() => {
    if (!sessao.carregando && !sessao.autenticado) {
      router.replace(`/?returnTo=${encodeURIComponent(caminhoAtual)}`);
    }
  }, [sessao.carregando, sessao.autenticado, caminhoAtual, router]);

  if (sessao.carregando) {
    return (
      <div className="mx-auto w-full max-w-6xl px-6 py-12">
        <Esqueleto className="h-8 w-48" />
      </div>
    );
  }

  if (!sessao.autenticado) {
    // O useEffect acima já disparou a navegação — evita um flash de conteúdo de gestão.
    return null;
  }

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-6 px-6 py-8 sm:flex-row">
      <nav aria-label="Navegação do painel" className="flex shrink-0 flex-col gap-1 sm:w-56">
        <p className="estilo-legenda px-3 pb-1 text-texto-terciario">{sessao.usuario?.nome}</p>

        <ItemDeNavegacao href="/painel" rotulo="Painel" caminhoAtual={caminhoAtual} />

        <PortaoDePermissao permissao="empresas.ler">
          <ItemDeNavegacao
            href="/painel/cadastros/empresas"
            rotulo="Cadastros"
            caminhoAtual={caminhoAtual}
            prefixoAtivo="/painel/cadastros"
          />
        </PortaoDePermissao>
        <PortaoDePermissao permissao="apuracoes.ler">
          <ItemDeNavegacao href="/painel/apuracao" rotulo="Apuração" caminhoAtual={caminhoAtual} />
        </PortaoDePermissao>
        <PortaoDePermissao permissao="escalas.ler">
          <ItemDeNavegacao href="/painel/escalas" rotulo="Escalas" caminhoAtual={caminhoAtual} />
        </PortaoDePermissao>

        <Botao
          type="button"
          variant="sutil"
          className="mt-4 justify-start"
          onClick={() => {
            void sessao.sair().then(() => router.replace("/"));
          }}
        >
          Sair
        </Botao>
      </nav>
      <main id="conteudo-do-painel" className="min-w-0 flex-1">
        {children}
      </main>
    </div>
  );
}

function ItemDeNavegacao({
  href,
  rotulo,
  caminhoAtual,
  prefixoAtivo,
}: {
  href: string;
  rotulo: string;
  caminhoAtual: string;
  /** Prefixo alternativo para marcar "ativo" (ex.: qualquer sub-rota de `/painel/cadastros`). */
  prefixoAtivo?: string;
}) {
  const base = prefixoAtivo ?? href;
  const ativo =
    caminhoAtual === href || caminhoAtual === base || caminhoAtual.startsWith(`${base}/`);
  return (
    <Link
      href={href}
      aria-current={ativo ? "page" : undefined}
      className={cn(
        "estilo-corpo rounded-pequeno px-3 py-2 text-texto-secundario hover:bg-fundo-sutil",
        ativo && "bg-acao-sutil-fundo text-acao-sutil-texto",
      )}
    >
      {rotulo}
    </Link>
  );
}
