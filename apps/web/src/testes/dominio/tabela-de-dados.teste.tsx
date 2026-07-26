import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeAll, describe, expect, it } from "vitest";

import { TabelaDeDados, type ColunaDeTabela } from "@/componentes/dominio/tabela-de-dados";

/**
 * O jsdom não faz layout de verdade: `offsetHeight`/`offsetWidth` ficam
 * sempre em 0, e é exatamente essa medida que o `@tanstack/react-virtual`
 * usa (sem `ResizeObserver`, que o jsdom também não implementa) para saber
 * quantos itens cabem na janela visível. Sem este stub, a lista virtualizada
 * nunca renderiza nenhuma linha em teste — não é defeito do componente.
 */
beforeAll(() => {
  Object.defineProperty(HTMLElement.prototype, "offsetHeight", {
    configurable: true,
    value: 384,
  });
  Object.defineProperty(HTMLElement.prototype, "offsetWidth", {
    configurable: true,
    value: 800,
  });
});

interface LinhaDeTeste {
  id: string;
  nome: string;
  saldoMinutos: number;
}

const LINHAS: LinhaDeTeste[] = [
  { id: "1", nome: "Beatriz", saldoMinutos: 30 },
  { id: "2", nome: "Ana", saldoMinutos: 90 },
  { id: "3", nome: "Carlos", saldoMinutos: -15 },
];

const COLUNAS: ColunaDeTabela<LinhaDeTeste>[] = [
  {
    id: "nome",
    cabecalho: "Nome",
    renderizarCelula: (linha) => linha.nome,
    ordenavel: true,
    valorDeOrdenacao: (linha) => linha.nome,
  },
  {
    id: "saldo",
    cabecalho: "Saldo",
    renderizarCelula: (linha) => String(linha.saldoMinutos),
    ordenavel: true,
    valorDeOrdenacao: (linha) => linha.saldoMinutos,
  },
];

describe("TabelaDeDados", () => {
  it("renderiza o estado vazio", () => {
    render(<TabelaDeDados linhas={[]} colunas={COLUNAS} obterId={(linha) => linha.id} />);
    expect(screen.getByText("Nenhum registro encontrado.")).toBeInTheDocument();
  });

  it("renderiza o estado de carregamento", () => {
    render(<TabelaDeDados linhas={LINHAS} colunas={COLUNAS} obterId={(linha) => linha.id} carregando />);
    expect(screen.getByText("Carregando…")).toBeInTheDocument();
  });

  it("renderiza as linhas com role grid/row/gridcell", () => {
    render(<TabelaDeDados linhas={LINHAS} colunas={COLUNAS} obterId={(linha) => linha.id} />);
    expect(screen.getByRole("grid")).toBeInTheDocument();
    expect(screen.getAllByRole("row")).toHaveLength(4); // 1 cabecalho + 3 dados
    expect(screen.getAllByRole("gridcell")).toHaveLength(6); // 3 linhas x 2 colunas
  });

  it("ordena por coluna com aria-sort correto", async () => {
    const usuario = userEvent.setup();
    render(<TabelaDeDados linhas={LINHAS} colunas={COLUNAS} obterId={(linha) => linha.id} />);

    const cabecalhoNome = screen.getByRole("columnheader", { name: /nome/i });
    expect(cabecalhoNome).toHaveAttribute("aria-sort", "none");

    await usuario.click(within(cabecalhoNome).getByRole("button"));
    expect(cabecalhoNome).toHaveAttribute("aria-sort", "ascending");
    const celulas = screen.getAllByRole("gridcell");
    expect(celulas[0]).toHaveTextContent("Ana");

    await usuario.click(within(cabecalhoNome).getByRole("button"));
    expect(cabecalhoNome).toHaveAttribute("aria-sort", "descending");
    expect(screen.getAllByRole("gridcell")[0]).toHaveTextContent("Carlos");
  });

  it("seleciona linhas e conta selecionadas", async () => {
    const usuario = userEvent.setup();
    render(
      <TabelaDeDados linhas={LINHAS} colunas={COLUNAS} obterId={(linha) => linha.id} selecionaveis />,
    );

    await usuario.click(screen.getByRole("checkbox", { name: "Selecionar linha 1" }));
    expect(screen.getByText("1 selecionada")).toBeInTheDocument();

    await usuario.click(screen.getByRole("checkbox", { name: "Selecionar todas as linhas" }));
    expect(screen.getByText("3 selecionadas")).toBeInTheDocument();
  });

  it("esconde e reordena colunas pelo painel", async () => {
    const usuario = userEvent.setup();
    render(<TabelaDeDados linhas={LINHAS} colunas={COLUNAS} obterId={(linha) => linha.id} />);

    await usuario.click(screen.getByText("Colunas"));
    await usuario.click(screen.getByLabelText("Saldo"));

    expect(screen.queryByRole("columnheader", { name: /saldo/i })).not.toBeInTheDocument();
    expect(screen.getAllByRole("gridcell")).toHaveLength(3); // so a coluna Nome restante
  });
});
