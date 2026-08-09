import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { PainelDeIndicadores } from "@/componentes/paineis/dashboard/painel-de-indicadores";

const useSessaoCompletaMock = vi.fn();
vi.mock("@/ganchos/use-sessao-completa", () => ({
  useSessaoCompleta: () => useSessaoCompletaMock(),
}));

vi.mock("@/componentes/paineis/dashboard/seletor-de-escopo", () => ({
  SeletorDeEscopo: () => <div data-testid="secao-seletor" />,
}));
vi.mock("@/componentes/paineis/dashboard/secao-colaboradores", () => ({
  SecaoColaboradores: () => <div data-testid="secao-colaboradores" />,
}));
vi.mock("@/componentes/paineis/dashboard/secao-apuracao", () => ({
  SecaoApuracao: () => <div data-testid="secao-apuracao" />,
}));
vi.mock("@/componentes/paineis/dashboard/secao-ocorrencias", () => ({
  SecaoOcorrencias: () => <div data-testid="secao-ocorrencias" />,
}));
vi.mock("@/componentes/paineis/dashboard/secao-banco-de-horas", () => ({
  SecaoBancoDeHoras: () => <div data-testid="secao-banco-de-horas" />,
}));
vi.mock("@/componentes/paineis/dashboard/marcacoes-em-aberto", () => ({
  MarcacoesEmAberto: () => <div data-testid="secao-marcacoes-em-aberto" />,
}));
vi.mock("@/componentes/paineis/dashboard/fila-de-aprovacoes", () => ({
  FilaDeAprovacoes: () => <div data-testid="secao-fila-de-aprovacoes" />,
}));

function sessaoComPermissoes(permissoes: string[]) {
  return { sessao: { permissoes }, carregando: false, erro: null };
}

/**
 * T2 (PCF F9b): "cada seção do dashboard é individualmente controlada por
 * `<PortaoDePermissao>` com a permissão exata do dado que ela mostra —
 * NUNCA um `if papel === 'rh'`". Prova por teste, como o "pronto quando" da
 * T2 exige: sessão sem `banco_horas.ler` não renderiza o cartão de saldo
 * (idem para as demais seções, cada uma com sua própria permissão).
 */
describe("PainelDeIndicadores (T2 — RBAC por seção, nunca por papel)", () => {
  it("sem nenhuma permissão, nenhuma seção de dado aparece", () => {
    useSessaoCompletaMock.mockReturnValue(sessaoComPermissoes([]));

    render(<PainelDeIndicadores />);

    expect(screen.queryByTestId("secao-seletor")).not.toBeInTheDocument();
    expect(screen.queryByTestId("secao-colaboradores")).not.toBeInTheDocument();
    expect(screen.queryByTestId("secao-apuracao")).not.toBeInTheDocument();
    expect(screen.queryByTestId("secao-ocorrencias")).not.toBeInTheDocument();
    expect(screen.queryByTestId("secao-banco-de-horas")).not.toBeInTheDocument();
    expect(screen.queryByTestId("secao-marcacoes-em-aberto")).not.toBeInTheDocument();
    expect(screen.queryByTestId("secao-fila-de-aprovacoes")).not.toBeInTheDocument();
  });

  it("sem banco_horas.ler, o cartão de saldo não renderiza — mesmo com todas as outras permissões", () => {
    useSessaoCompletaMock.mockReturnValue(
      sessaoComPermissoes([
        "empresas.ler",
        "colaboradores.ler",
        "apuracoes.ler",
        "ocorrencias.ler",
        "marcacoes.ler",
        "aprovacoes.ler",
      ]),
    );

    render(<PainelDeIndicadores />);

    expect(screen.getByTestId("secao-colaboradores")).toBeInTheDocument();
    expect(screen.getByTestId("secao-apuracao")).toBeInTheDocument();
    expect(screen.getByTestId("secao-ocorrencias")).toBeInTheDocument();
    expect(screen.getByTestId("secao-marcacoes-em-aberto")).toBeInTheDocument();
    expect(screen.getByTestId("secao-fila-de-aprovacoes")).toBeInTheDocument();
    expect(screen.queryByTestId("secao-banco-de-horas")).not.toBeInTheDocument();
  });

  it("com banco_horas.ler, o cartão de saldo renderiza", () => {
    useSessaoCompletaMock.mockReturnValue(sessaoComPermissoes(["banco_horas.ler"]));

    render(<PainelDeIndicadores />);

    expect(screen.getByTestId("secao-banco-de-horas")).toBeInTheDocument();
  });

  it("cada permissão controla EXATAMENTE sua própria seção, isoladamente", () => {
    useSessaoCompletaMock.mockReturnValue(sessaoComPermissoes(["apuracoes.ler"]));

    render(<PainelDeIndicadores />);

    expect(screen.getByTestId("secao-apuracao")).toBeInTheDocument();
    expect(screen.queryByTestId("secao-colaboradores")).not.toBeInTheDocument();
    expect(screen.queryByTestId("secao-ocorrencias")).not.toBeInTheDocument();
    expect(screen.queryByTestId("secao-marcacoes-em-aberto")).not.toBeInTheDocument();
    expect(screen.queryByTestId("secao-fila-de-aprovacoes")).not.toBeInTheDocument();
    expect(screen.queryByTestId("secao-banco-de-horas")).not.toBeInTheDocument();
  });

  it("aprovacoes.ler controla a fila de aprovações isoladamente", () => {
    useSessaoCompletaMock.mockReturnValue(sessaoComPermissoes(["aprovacoes.ler"]));

    render(<PainelDeIndicadores />);

    expect(screen.getByTestId("secao-fila-de-aprovacoes")).toBeInTheDocument();
    expect(screen.queryByTestId("secao-apuracao")).not.toBeInTheDocument();
    expect(screen.queryByTestId("secao-marcacoes-em-aberto")).not.toBeInTheDocument();
  });
});
