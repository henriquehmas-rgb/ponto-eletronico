"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode, type SVGProps } from "react";
import { MenuIcon } from "lucide-react";

import { Botao } from "@/componentes/ui/button";
import { Esqueleto } from "@/componentes/ui/skeleton";
import { Folha, FolhaConteudo, FolhaTitulo } from "@/componentes/ui/sheet";
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
 * Visual: padrão oficial de "superfícies macias" (`docs/design-system-oficial.md`,
 * 09/08/2026) — barra lateral com itens em pílula e cartão de usuário
 * flutuante no rodapé, traduzido do protótipo `SEEG Ponto.dc.html` (linhas
 * 647-670) para os primitivos reais do projeto. `children` continua com a
 * mesma assinatura — todas as rotas de `/painel/*` dependem desta casca.
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
  const [menuMobileAberto, definirMenuMobileAberto] = useState(false);

  useEffect(() => {
    if (!sessao.carregando && !sessao.autenticado) {
      router.replace(`/?returnTo=${encodeURIComponent(caminhoAtual)}`);
    }
  }, [sessao.carregando, sessao.autenticado, caminhoAtual, router]);

  // Fecha o menu ao trocar de rota — o `<Folha>` não desmonta sozinho quando
  // um `<Link>` de dentro dele navega (é um portal fora da árvore do menu).
  useEffect(() => {
    definirMenuMobileAberto(false);
  }, [caminhoAtual]);

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

  const nome = sessao.usuario?.nome ?? "";
  const iniciais =
    nome
      .trim()
      .split(/\s+/)
      .slice(0, 2)
      .map((parte) => parte.charAt(0).toUpperCase())
      .join("") || "?";

  function aoSair() {
    void sessao.sair().then(() => router.replace("/"));
  }

  return (
    <div className="mx-auto flex w-full max-w-7xl flex-col gap-6 px-4 py-4 sm:flex-row sm:items-start sm:px-6 sm:py-8">
      <header className="flex items-center justify-between sm:hidden">
        <div className="flex items-center gap-2 px-1">
          <IconeLogo className="h-[21px] w-[21px] text-acao-primaria-fundo" />
          <span className="font-display text-[14px] font-bold tracking-[-0.01em] text-texto-primario">
            SEEG PONTO
          </span>
        </div>
        <Botao
          type="button"
          variant="sutil"
          tamanho="icone-toque"
          className="rounded-pleno"
          aria-label="Abrir menu de navegação"
          onClick={() => definirMenuMobileAberto(true)}
        >
          <MenuIcon aria-hidden="true" className="size-4" />
        </Botao>
      </header>

      <Folha open={menuMobileAberto} onOpenChange={definirMenuMobileAberto}>
        <FolhaConteudo lado="left" className="w-4/5 gap-6 p-4">
          <FolhaTitulo className="sr-only">Navegação do painel</FolhaTitulo>
          <ConteudoDaBarraLateral
            caminhoAtual={caminhoAtual}
            nome={nome}
            iniciais={iniciais}
            email={sessao.usuario?.email}
            aoSair={aoSair}
          />
        </FolhaConteudo>
      </Folha>

      <aside className="hidden shrink-0 flex-col gap-6 sm:sticky sm:top-8 sm:flex sm:w-60">
        <ConteudoDaBarraLateral
          caminhoAtual={caminhoAtual}
          nome={nome}
          iniciais={iniciais}
          email={sessao.usuario?.email}
          aoSair={aoSair}
        />
      </aside>
      <main id="conteudo-do-painel" className="min-w-0 flex-1">
        {children}
      </main>
    </div>
  );
}

function ConteudoDaBarraLateral({
  caminhoAtual,
  nome,
  iniciais,
  email,
  aoSair,
}: {
  caminhoAtual: string;
  nome: string;
  iniciais: string;
  email: string | undefined;
  aoSair: () => void;
}) {
  return (
    <>
      <div className="hidden items-center gap-2 px-3 sm:flex">
        <IconeLogo className="h-[21px] w-[21px] text-acao-primaria-fundo" />
        <span className="font-display text-[14px] font-bold tracking-[-0.01em] text-texto-primario">
          SEEG PONTO
        </span>
      </div>

      <nav aria-label="Navegação do painel" className="flex flex-col gap-1">
        <ItemDeNavegacao
          href="/painel"
          rotulo="Painel"
          caminhoAtual={caminhoAtual}
          icone={IconeVisaoGeral}
        />

        <PortaoDePermissao permissao="empresas.ler">
          <ItemDeNavegacao
            href="/painel/cadastros/empresas"
            rotulo="Cadastros"
            caminhoAtual={caminhoAtual}
            prefixoAtivo="/painel/cadastros"
            icone={IconeCadastros}
          />
        </PortaoDePermissao>
        <PortaoDePermissao permissao="aprovacoes.ler">
          <ItemDeNavegacao
            href="/painel/aprovacoes"
            rotulo="Aprovações"
            caminhoAtual={caminhoAtual}
            icone={IconeAprovacoes}
          />
        </PortaoDePermissao>
        <PortaoDePermissao permissao="apuracoes.ler">
          <ItemDeNavegacao
            href="/painel/apuracao"
            rotulo="Apuração"
            caminhoAtual={caminhoAtual}
            icone={IconeApuracao}
          />
        </PortaoDePermissao>
        <PortaoDePermissao permissao="escalas.ler">
          <ItemDeNavegacao
            href="/painel/escalas"
            rotulo="Escalas"
            caminhoAtual={caminhoAtual}
            icone={IconeEscalas}
          />
        </PortaoDePermissao>
        <PortaoDePermissao permissao="webhooks.ler">
          <ItemDeNavegacao
            href="/painel/integracoes"
            rotulo="Integrações"
            caminhoAtual={caminhoAtual}
            prefixoAtivo="/painel/integracoes"
            icone={IconeIntegracoes}
          />
        </PortaoDePermissao>
        <PortaoDePermissao permissao="marcacoes.ler_sensivel">
          <ItemDeNavegacao
            href="/painel/antifraude"
            rotulo="Antifraude"
            caminhoAtual={caminhoAtual}
            prefixoAtivo="/painel/antifraude"
            icone={IconeAntifraude}
          />
        </PortaoDePermissao>
        <PortaoDePermissao permissao="relatorios.ler">
          <ItemDeNavegacao
            href="/painel/relatorios"
            rotulo="Relatórios"
            caminhoAtual={caminhoAtual}
            prefixoAtivo="/painel/relatorios"
            icone={IconeRelatorios}
          />
        </PortaoDePermissao>
      </nav>

      <div className="mt-auto flex flex-col gap-2">
        <div className="flex items-center gap-[var(--espacamento-3)] rounded-suave bg-fundo-sutil p-3 shadow-flutuante-cartao">
          <span
            aria-hidden="true"
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-pleno bg-gradient-to-br from-marca-300 to-marca-600 text-[12px] font-semibold text-texto-inverso"
          >
            {iniciais}
          </span>
          <div className="min-w-0 flex-1">
            <p className="truncate text-[12.5px] font-semibold text-texto-primario">{nome}</p>
            <p className="truncate text-[11px] text-texto-terciario">{email}</p>
          </div>
        </div>
        <Botao type="button" variant="sutil" className="justify-start rounded-pleno" onClick={aoSair}>
          Sair
        </Botao>
      </div>
    </>
  );
}

function ItemDeNavegacao({
  href,
  rotulo,
  caminhoAtual,
  prefixoAtivo,
  icone: Icone,
}: {
  href: string;
  rotulo: string;
  caminhoAtual: string;
  /** Prefixo alternativo para marcar "ativo" (ex.: qualquer sub-rota de `/painel/cadastros`). */
  prefixoAtivo?: string;
  icone: (props: SVGProps<SVGSVGElement>) => ReactNode;
}) {
  const base = prefixoAtivo ?? href;
  const ativo =
    caminhoAtual === href || caminhoAtual === base || caminhoAtual.startsWith(`${base}/`);
  return (
    <Link
      href={href}
      aria-current={ativo ? "page" : undefined}
      className={cn(
        "estilo-corpo flex items-center gap-[11px] rounded-pleno px-3 py-2.5 text-texto-secundario",
        "hover:bg-fundo-sutil",
        ativo && "bg-acao-sutil-fundo font-medium text-acao-sutil-texto hover:bg-acao-sutil-fundo",
      )}
    >
      <Icone aria-hidden="true" className="h-[17px] w-[17px] shrink-0" />
      <span className="flex-1">{rotulo}</span>
    </Link>
  );
}

/** Marca gráfica (check estilizado) — mesmo traço do protótipo (`SEEG Ponto.dc.html`, l. 649). */
function IconeLogo(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 32 32" fill="none" {...props}>
      <path
        d="M8.6 18.6 13.6 24.1 24.2 7.6"
        stroke="currentColor"
        strokeWidth="2.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path d="M6.4 26 H25.6" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" />
    </svg>
  );
}

function propsIcone(props: SVGProps<SVGSVGElement>) {
  return {
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 2,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    ...props,
  };
}

function IconeVisaoGeral(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...propsIcone(props)}>
      <rect x="3.5" y="3.5" width="7.5" height="7.5" rx="1.5" />
      <rect x="13" y="3.5" width="7.5" height="7.5" rx="1.5" />
      <rect x="3.5" y="13" width="7.5" height="7.5" rx="1.5" />
      <rect x="13" y="13" width="7.5" height="7.5" rx="1.5" />
    </svg>
  );
}

function IconeCadastros(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...propsIcone(props)}>
      <circle cx="9" cy="8" r="3.2" />
      <path d="M3.5 20c0-3.6 2.5-6 5.5-6s5.5 2.4 5.5 6" />
      <circle cx="17" cy="7.5" r="2.3" />
      <path d="M15 12.2c2.4.2 4 2.2 4 5.3" />
    </svg>
  );
}

function IconeApuracao(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...propsIcone(props)}>
      <rect x="3.5" y="5" width="17" height="15" rx="3" />
      <path d="M3.5 9.5h17" />
      <path d="M8 3.5v3" />
      <path d="M16 3.5v3" />
      <path d="M8.5 14.5l2.4 2.4 4.6-5" />
    </svg>
  );
}

function IconeEscalas(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...propsIcone(props)}>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 7v5l3.2 2" />
    </svg>
  );
}

function IconeIntegracoes(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...propsIcone(props)}>
      <path d="M9 15 15 9" />
      <path d="M8 13.5 5.8 15.7a3 3 0 0 1-4.2-4.2L3.8 9.3" />
      <path d="M16 10.7l2.2-2.2a3 3 0 0 0-4.2-4.2L11.8 6.5" />
    </svg>
  );
}

function IconeAntifraude(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...propsIcone(props)}>
      <path d="M12 3.5 19.5 6.5V11.5C19.5 16 16.5 19.5 12 20.5C7.5 19.5 4.5 16 4.5 11.5V6.5Z" />
      <path d="M9 12l2 2 4-4.5" />
    </svg>
  );
}

function IconeAprovacoes(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...propsIcone(props)}>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M8.3 12.3l2.5 2.5 5-5.4" />
    </svg>
  );
}

function IconeRelatorios(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...propsIcone(props)}>
      <path d="M4.5 20.5h15" />
      <rect x="6" y="13" width="3.4" height="7.5" rx="0.8" />
      <rect x="10.3" y="8.5" width="3.4" height="12" rx="0.8" />
      <rect x="14.6" y="4.5" width="3.4" height="16" rx="0.8" />
    </svg>
  );
}
