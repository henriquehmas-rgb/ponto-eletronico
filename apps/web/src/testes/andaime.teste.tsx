import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";

import PaginaDoColaborador from "@/app/eu/page";
import PaginaDeLogin from "@/app/page";
import PaginaDoPainel from "@/app/painel/page";
import { CabecalhoDoAndaime } from "@/componentes/andaime/cabecalho-do-andaime";
import { ProvedorDeConsultas } from "@/componentes/provedor-de-consultas";
import { ProvedorDeTema } from "@/componentes/tema/provedor-de-tema";

/**
 * Teste minimo da Fase 0: prova que a aplicacao RENDERIZA.
 *
 * Nao testa regra de negocio — nao existe nenhuma nesta fase. Testa o que o
 * andaime promete: as tres rotas montam, os provedores nao explodem e cada
 * pagina diz honestamente qual fase a implementa.
 */

function comProvedores(no: ReactNode) {
  return (
    <ProvedorDeTema>
      <ProvedorDeConsultas>{no}</ProvedorDeConsultas>
    </ProvedorDeTema>
  );
}

describe("andaime da aplicacao web", () => {
  it("renderiza a rota / e aponta a F1 como responsavel", () => {
    render(comProvedores(<PaginaDeLogin />));

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("/ — Entrar");
    expect(screen.getByText("F1")).toBeInTheDocument();
    expect(screen.getByText(/sem regra de negocio/i)).toBeInTheDocument();
  });

  it("renderiza a rota /painel e aponta a F9b como responsavel", () => {
    render(comProvedores(<PaginaDoPainel />));

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("/painel");
    expect(screen.getByText("F9b")).toBeInTheDocument();
    // A vedacao legal do REP-P precisa estar visivel ja no andaime.
    expect(screen.getByText("POST /v1/tratamentos")).toBeInTheDocument();
  });

  it("renderiza a rota /eu e aponta a F8 como responsavel", () => {
    render(comProvedores(<PaginaDoColaborador />));

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("/eu");
    expect(screen.getByText("F8")).toBeInTheDocument();
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
