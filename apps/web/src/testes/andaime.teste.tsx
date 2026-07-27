import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";

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
 * por desenho, não por regressão. A cobertura real de `/` e `/eu` vive em
 * `src/testes/f8/portal/pagina-de-login.teste.tsx` e
 * `src/testes/f8/portal/painel-do-colaborador.teste.tsx`.
 *
 * NOTA (F9b, T1 — MESMO tratamento, mesma exceção documentada que F8 já
 * aplicou acima): a asserção de `/painel` que existia aqui ("renderiza a
 * rota /painel e aponta a F9b como responsavel", verificando o texto do
 * `PlaceholderDeFase`) foi REMOVIDA — `/painel/page.tsx` deixou de ser
 * placeholder (T2) e agora exige `ProvedorDeSessao`/`useSessao()` (guarda de
 * rota redireciona sem sessão) e `QueryClientProvider` com ganchos reais para
 * montar, o que foge do espírito de "smoke test trivial sem mocks" deste
 * arquivo — mesma incompatibilidade lógica que a F8 já documentou para `/` e
 * `/eu`: manter a asserção antiga faria este teste falhar sempre, por
 * definição, não por regressão. A cobertura real de `/painel` (estados de
 * carregamento/erro/sucesso do dashboard, RBAC por seção) vive em
 * `src/testes/paineis/dashboard/**`. Este arquivo continua fora do ownership
 * de A1 (PCF F9b §5, "Explicitamente fora do seu ownership") — esta é uma
 * edição pontual e documentada, não uma reescrita.
 */

function comProvedores(no: ReactNode) {
  return (
    <ProvedorDeTema>
      <ProvedorDeConsultas>{no}</ProvedorDeConsultas>
    </ProvedorDeTema>
  );
}

describe("andaime da aplicacao web", () => {
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
