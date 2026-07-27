import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";

import PaginaDoPainel from "@/app/painel/page";
import { CabecalhoDoAndaime } from "@/componentes/andaime/cabecalho-do-andaime";
import { ProvedorDeConsultas } from "@/componentes/provedor-de-consultas";
import { ProvedorDeTema } from "@/componentes/tema/provedor-de-tema";

/**
 * Teste minimo da Fase 0: prova que a aplicacao RENDERIZA.
 *
 * Nao testa regra de negocio — nao existe nenhuma nesta fase. Testa o que o
 * andaime promete: as rotas ainda em placeholder montam, os provedores nao
 * explodem e cada pagina diz honestamente qual fase a implementa.
 *
 * NOTA (F8, T1): as asserções de `/` e `/eu` que existiam aqui foram
 * REMOVIDAS de propósito — a F8 substituiu os dois `PlaceholderDeFase` por
 * conteúdo real (login de verdade e painel do colaborador), então o texto
 * "F1"/"F8 — placeholder" que este smoke test verificava deixou de existir
 * por desenho, não por regressão. As duas páginas passaram a exigir contexto
 * de app router e de sessão (`ProvedorDeSessao`) para montar, o que foge do
 * espírito de "smoke test trivial sem mocks" deste arquivo — a cobertura real
 * de `/` e `/eu` agora vive em `src/testes/f8/portal/pagina-de-login.teste.tsx`
 * e `src/testes/f8/portal/painel-do-colaborador.teste.tsx`, com os mocks que
 * as páginas de verdade precisam. `/painel` continua placeholder (F9b ainda
 * não rodou nesta build) e a asserção correspondente foi mantida.
 */

function comProvedores(no: ReactNode) {
  return (
    <ProvedorDeTema>
      <ProvedorDeConsultas>{no}</ProvedorDeConsultas>
    </ProvedorDeTema>
  );
}

describe("andaime da aplicacao web", () => {
  it("renderiza a rota /painel e aponta a F9b como responsavel", () => {
    render(comProvedores(<PaginaDoPainel />));

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("/painel");
    expect(screen.getByText("F9b")).toBeInTheDocument();
    // A vedacao legal do REP-P precisa estar visivel ja no andaime.
    expect(screen.getByText("POST /v1/tratamentos")).toBeInTheDocument();
  });

  it("monta o cabecalho com as tres rotas e o alternador de tema", () => {
    render(comProvedores(<CabecalhoDoAndaime />));

    expect(screen.getByRole("navigation", { name: /rotas do andaime/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /entrar/i })).toHaveAttribute("href", "/");
    expect(screen.getByRole("link", { name: /painel/i })).toHaveAttribute("href", "/painel");
    expect(screen.getByRole("link", { name: /^eu/i })).toHaveAttribute("href", "/eu");

    const grupo = screen.getByRole("radiogroup", { name: /tema da interface/i });
    expect(grupo).toBeInTheDocument();
    expect(screen.getAllByRole("radio")).toHaveLength(3);
  });
});
