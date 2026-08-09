"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";
import { Clock3, FileText, Home, User } from "lucide-react";

import { Botao } from "@/componentes/ui/button";
import { Esqueleto } from "@/componentes/ui/skeleton";
import { cn } from "@/lib/utils";
import { ProvedorDeSessao, useSessao } from "@/lib/sessao";

/**
 * Casca de navegação do colaborador (T1) — aninhada, sem tocar em
 * `cabecalho-do-andaime.tsx` nem em `src/app/layout.tsx` (§2/§5 do PCF: a
 * navegação global "andaime" só é substituída quando F8 e F9b já tiverem
 * rodado, decisão de outra fase).
 *
 * Monta seu PRÓPRIO `<ProvedorDeSessao>` — o mesmo módulo que `/painel`
 * (F9b) vai montar depois. Cada área do produto mantém sua própria instância
 * porque não há um layout raiz compartilhado disponível para isso (Fase 0);
 * o `refresh` silencioso ao montar (T1) restaura a sessão a partir do cookie
 * `httpOnly` em qualquer uma delas.
 */
export default function LayoutDoColaborador({ children }: { children: ReactNode }) {
  return (
    <ProvedorDeSessao>
      <GuardaDeRota>{children}</GuardaDeRota>
    </ProvedorDeSessao>
  );
}

const ITENS_DE_NAVEGACAO = [
  { href: "/eu", rotulo: "Início" },
  { href: "/eu/extrato", rotulo: "Extrato" },
  { href: "/eu/solicitacoes", rotulo: "Solicitações" },
  { href: "/eu/comprovantes", rotulo: "Comprovantes" },
  { href: "/eu/registrar", rotulo: "Registrar ponto" },
  { href: "/eu/perfil", rotulo: "Perfil" },
] as const;

/**
 * Navegação inferior flutuante (celular) — padrão 7 de
 * `docs/design-system-oficial.md`. Só as 4 abas mais frequentes cabem numa
 * barra flutuante de toque confortável; "Registrar ponto" já é o CTA
 * principal do cartão hero de `/eu`, e "Comprovantes" fica a um toque de
 * distância em Início › Serviços — nenhuma rota perde alcance, só muda de
 * lugar.
 */
const ITENS_DE_NAVEGACAO_INFERIOR = [
  { href: "/eu", rotulo: "Início", Icone: Home },
  { href: "/eu/extrato", rotulo: "Extrato", Icone: Clock3 },
  { href: "/eu/solicitacoes", rotulo: "Solicitações", Icone: FileText },
  { href: "/eu/perfil", rotulo: "Perfil", Icone: User },
] as const;

function GuardaDeRota({ children }: { children: ReactNode }) {
  const sessao = useSessao();
  const router = useRouter();
  const caminhoAtual = usePathname();

  useEffect(() => {
    if (!sessao.carregando && !sessao.autenticado) {
      // `returnTo` aqui é redundante com o padrão de `/` (que já navega para
      // `/eu` sem parâmetro), mas mantém o MESMO mecanismo uniforme que
      // `/painel` (F9b) vai usar — um único jeito de "voltar de onde saiu".
      router.replace(`/?returnTo=${encodeURIComponent(caminhoAtual)}`);
    }
  }, [sessao.carregando, sessao.autenticado, caminhoAtual, router]);

  if (sessao.carregando) {
    return (
      <div className="mx-auto w-full max-w-5xl px-6 py-12">
        <Esqueleto className="h-8 w-48" />
      </div>
    );
  }

  if (!sessao.autenticado) {
    // O useEffect acima já disparou a navegação — evita um flash de conteúdo.
    return null;
  }

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-6 px-4 py-8 sm:flex-row sm:px-6">
      {/* Sidebar — só a partir de `sm`, onde a tela tem largura de sobra para uma coluna de navegação. */}
      <nav
        aria-label="Navegação do colaborador"
        className="hidden shrink-0 flex-col gap-1 sm:flex sm:w-48"
      >
        <p className="estilo-legenda px-3 pb-1 text-texto-terciario">{sessao.usuario?.nome}</p>
        {ITENS_DE_NAVEGACAO.map((item) => {
          const ativo = caminhoAtual === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              aria-current={ativo ? "page" : undefined}
              className={cn(
                "estilo-corpo rounded-pequeno px-3 py-2 text-texto-secundario hover:bg-fundo-sutil",
                ativo && "bg-acao-sutil-fundo text-acao-sutil-texto",
              )}
            >
              {item.rotulo}
            </Link>
          );
        })}
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

      <main id="conteudo-do-colaborador" className="min-w-0 flex-1 pb-28 sm:pb-0">
        {children}
      </main>

      {/* Navegação inferior flutuante — só abaixo de `sm`, padrão 7 de docs/design-system-oficial.md. */}
      <nav
        aria-label="Navegação do colaborador"
        className="fixed inset-x-4 bottom-6 z-[var(--camada-navegacao)] flex items-center gap-0.5 rounded-pronunciado
                   border border-borda-sutil bg-fundo-superficie/90 p-2 shadow-flutuante-alta
                   backdrop-blur-xl sm:hidden"
      >
        {ITENS_DE_NAVEGACAO_INFERIOR.map((item) => {
          const ativo = caminhoAtual === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              aria-current={ativo ? "page" : undefined}
              className={cn(
                "flex flex-1 flex-col items-center gap-1 rounded-grande py-2",
                ativo ? "bg-fundo-inverso text-texto-inverso" : "text-texto-terciario",
              )}
            >
              <item.Icone className="h-5 w-5" aria-hidden="true" />
              <span className="text-3xs font-semibold">{item.rotulo}</span>
            </Link>
          );
        })}
      </nav>
    </div>
  );
}
