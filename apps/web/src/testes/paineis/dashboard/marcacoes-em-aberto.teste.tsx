import { readFileSync } from "node:fs";
import { join } from "node:path";

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { MarcacoesEmAberto } from "@/componentes/paineis/dashboard/marcacoes-em-aberto";
import { ErroDaApi } from "@/lib/api";

const useMarcacoesEmAbertoMock = vi.fn();
vi.mock("@/ganchos/use-marcacoes-em-aberto", () => ({
  useMarcacoesEmAberto: (...args: unknown[]) => useMarcacoesEmAbertoMock(...args),
}));

function estadoDeCarregamento() {
  return { data: undefined, isPending: true, isError: false, error: null };
}
function estadoDeSucesso(data: unknown) {
  return { data, isPending: false, isError: false, error: null };
}
function estadoDeErro(erro: unknown) {
  return { data: undefined, isPending: false, isError: true, error: erro };
}

describe("MarcacoesEmAberto (T3 — widget de dashboard, tempo real por polling)", () => {
  it("estado de carregamento", () => {
    useMarcacoesEmAbertoMock.mockReturnValue(estadoDeCarregamento());
    render(<MarcacoesEmAberto escopo={{}} />);
    expect(screen.getByText("Carregando…")).toBeInTheDocument();
  });

  it("estado de erro mostra mensagem amigável", () => {
    useMarcacoesEmAbertoMock.mockReturnValue(
      estadoDeErro(
        new ErroDaApi(500, {
          type: "about:blank",
          title: "Erro interno",
          status: 500,
          codigo: "PONTO-INT-001",
        }),
      ),
    );
    render(<MarcacoesEmAberto escopo={{}} />);
    expect(screen.getByText(/Não foi possível carregar as marcações de hoje/)).toBeInTheDocument();
  });

  it("estado vazio: nenhum vínculo em aberto", () => {
    useMarcacoesEmAbertoMock.mockReturnValue(estadoDeSucesso([]));
    render(<MarcacoesEmAberto escopo={{}} />);
    expect(
      screen.getByText("Nenhum vínculo com marcação em aberto no momento."),
    ).toBeInTheDocument();
  });

  it("lista vínculos em aberto com rótulo honesto (última marcação, nunca presença como fato)", () => {
    useMarcacoesEmAbertoMock.mockReturnValue(
      estadoDeSucesso([
        {
          vinculoId: "v1",
          colaboradorId: "c1",
          nomeColaborador: "Maria Souza",
          quantidadeMarcacoes: 3,
          ultimaMarcacaoEm: "2026-07-27T14:32:00Z",
          ultimoCanal: "web",
        },
      ]),
    );
    render(<MarcacoesEmAberto escopo={{}} />);

    expect(screen.getByText("Maria Souza")).toBeInTheDocument();
    expect(screen.getByText(/última marcação às/)).toBeInTheDocument();
    expect(screen.getByText(/sem marcação registrada depois/)).toBeInTheDocument();
  });

  it("sem nome resolvido, cai no identificador do vínculo (nunca quebra)", () => {
    useMarcacoesEmAbertoMock.mockReturnValue(
      estadoDeSucesso([
        {
          vinculoId: "abcdef12-3456-7890-abcd-ef1234567890",
          colaboradorId: undefined,
          nomeColaborador: undefined,
          quantidadeMarcacoes: 1,
          ultimaMarcacaoEm: "2026-07-27T08:00:00Z",
          ultimoCanal: "terminal",
        },
      ]),
    );
    render(<MarcacoesEmAberto escopo={{}} />);
    expect(screen.getByText(/Vínculo abcdef12/)).toBeInTheDocument();
  });
});

/**
 * "Pronto quando" da T3: "nenhum texto do componente afirma presença como
 * certeza (grep no código-fonte do componente não encontra 'está trabalhando'
 * nem equivalente categórico)". Varredura real do código-fonte, não promessa.
 */
describe("MarcacoesEmAberto — varredura de texto proibido (T3)", () => {
  const ARQUIVOS = [
    join(import.meta.dirname, "../../../componentes/paineis/dashboard/marcacoes-em-aberto.tsx"),
    join(import.meta.dirname, "../../../ganchos/use-marcacoes-em-aberto.ts"),
  ];

  const FRASES_PROIBIDAS = [
    /est[aá]\s+trabalhando/i,
    /trabalhando\s+agora/i,
    /presente\s+no\s+momento/i,
    /confirmad[oa]\s+no\s+trabalho/i,
  ];

  /**
   * Remove comentários (`//...` e `/* ... *\/`) antes de varrer: os dois
   * arquivos DISCUTEM a proibição em prosa explicativa ("este gancho NUNCA
   * afirma que...") — é aí, de propósito, que a frase proibida aparece. O
   * critério real da T3 é sobre texto que o USUÁRIO vê (JSX/string literal),
   * não sobre a documentação que explica a regra.
   */
  function semComentarios(codigo: string): string {
    return codigo.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/.*$/gm, "");
  }

  it.each(ARQUIVOS)("%s não afirma presença como fato (fora de comentários)", (caminho) => {
    const codigoSemComentarios = semComentarios(readFileSync(caminho, "utf-8"));
    for (const frase of FRASES_PROIBIDAS) {
      expect(codigoSemComentarios).not.toMatch(frase);
    }
  });
});
