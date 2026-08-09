import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { FilaDeAprovacoes } from "@/componentes/paineis/dashboard/fila-de-aprovacoes";
import { ErroDaApi } from "@/lib/api";

const useAprovacoesPendentesMock = vi.fn();
const useDecidirAprovacaoMock = vi.fn();
vi.mock("@/ganchos/use-aprovacoes", () => ({
  useAprovacoesPendentes: (...args: unknown[]) => useAprovacoesPendentesMock(...args),
  useDecidirAprovacao: () => useDecidirAprovacaoMock(),
}));

const useSolicitacaoMock = vi.fn();
vi.mock("@/ganchos/use-solicitacoes", () => ({
  useSolicitacao: (...args: unknown[]) => useSolicitacaoMock(...args),
}));

const useColaboradorMock = vi.fn();
vi.mock("@/ganchos/use-colaboradores", () => ({
  useColaborador: (...args: unknown[]) => useColaboradorMock(...args),
}));

const useTiposSolicitacaoMock = vi.fn();
vi.mock("@/ganchos/use-tipos-solicitacao", () => ({
  useTiposSolicitacao: () => useTiposSolicitacaoMock(),
}));

const useSessaoCompletaMock = vi.fn();
vi.mock("@/ganchos/use-sessao-completa", () => ({
  useSessaoCompleta: () => useSessaoCompletaMock(),
}));

function estadoDeSucesso<T>(data: T) {
  return { data, isPending: false, isError: false, error: null };
}
function estadoDeCarregamento() {
  return { data: undefined, isPending: true, isError: false, error: null };
}
function estadoDeErro(erro: unknown) {
  return { data: undefined, isPending: false, isError: true, error: erro };
}

const APROVACAO = {
  id: "a1",
  solicitacaoId: "s1",
  etapa: 1,
  papel: "gestor",
  decisao: "pendente",
  prazoEm: "2026-08-15T00:00:00Z",
};

function configurarPadrao() {
  useSessaoCompletaMock.mockReturnValue({
    sessao: { permissoes: ["aprovacoes.ler", "aprovacoes.aprovar"] },
    carregando: false,
    erro: null,
  });
  useSolicitacaoMock.mockReturnValue(
    estadoDeSucesso({
      id: "s1",
      colaboradorId: "c1",
      tipoSolicitacaoId: "t1",
      descricao: "Ajuste do dia 10/08",
    }),
  );
  useColaboradorMock.mockReturnValue(estadoDeSucesso({ id: "c1", nomeCompleto: "Maria Souza" }));
  useTiposSolicitacaoMock.mockReturnValue(
    estadoDeSucesso({ dados: [{ id: "t1", nome: "Ajuste de ponto" }] }),
  );
  useDecidirAprovacaoMock.mockReturnValue({ mutate: vi.fn(), isPending: false, isError: false });
}

describe("FilaDeAprovacoes (fila real de gestor — GET /v1/aprovacoes, primeira tela a consumir)", () => {
  it("estado de carregamento mostra esqueletos", () => {
    configurarPadrao();
    useAprovacoesPendentesMock.mockReturnValue(estadoDeCarregamento());
    render(<FilaDeAprovacoes />);
    expect(document.querySelectorAll('[data-slot="esqueleto"]').length).toBeGreaterThan(0);
  });

  it("estado de erro mostra mensagem amigável", () => {
    configurarPadrao();
    useAprovacoesPendentesMock.mockReturnValue(
      estadoDeErro(
        new ErroDaApi(500, { type: "about:blank", title: "Erro interno", status: 500, codigo: "PONTO-INT-001" }),
      ),
    );
    render(<FilaDeAprovacoes />);
    expect(screen.getByText("Erro interno")).toBeInTheDocument();
  });

  it("fila vazia mostra estado neutro, nunca um erro", () => {
    configurarPadrao();
    useAprovacoesPendentesMock.mockReturnValue(
      estadoDeSucesso({ dados: [], paginacao: { temMais: false, limite: 5 } }),
    );
    render(<FilaDeAprovacoes />);
    expect(screen.getByText("Fila zerada")).toBeInTheDocument();
    expect(screen.getByText("Nada aguardando decisão sua.")).toBeInTheDocument();
  });

  it("lista uma etapa pendente com nome do colaborador e tipo, resolvidos por fora do endpoint de aprovações", () => {
    configurarPadrao();
    useAprovacoesPendentesMock.mockReturnValue(
      estadoDeSucesso({ dados: [APROVACAO], paginacao: { temMais: false, limite: 5 } }),
    );
    render(<FilaDeAprovacoes />);
    expect(screen.getByText("Maria Souza")).toBeInTheDocument();
    expect(screen.getByText(/Ajuste de ponto/)).toBeInTheDocument();
    expect(screen.getByText("1")).toBeInTheDocument();
  });

  it("aprovar chama a mutação com decisao=aprovar e o id real da etapa", () => {
    configurarPadrao();
    const mutate = vi.fn();
    useDecidirAprovacaoMock.mockReturnValue({ mutate, isPending: false, isError: false });
    useAprovacoesPendentesMock.mockReturnValue(
      estadoDeSucesso({ dados: [APROVACAO], paginacao: { temMais: false, limite: 5 } }),
    );
    render(<FilaDeAprovacoes />);

    fireEvent.click(screen.getByRole("button", { name: "Aprovar" }));

    expect(mutate).toHaveBeenCalledWith({ aprovacaoId: "a1", decisao: "aprovar" });
  });

  it("recusar exige comentário antes de confirmar (contrato: obrigatório na reprovação)", () => {
    configurarPadrao();
    const mutate = vi.fn();
    useDecidirAprovacaoMock.mockReturnValue({ mutate, isPending: false, isError: false });
    useAprovacoesPendentesMock.mockReturnValue(
      estadoDeSucesso({ dados: [APROVACAO], paginacao: { temMais: false, limite: 5 } }),
    );
    render(<FilaDeAprovacoes />);

    fireEvent.click(screen.getByRole("button", { name: "Recusar" }));
    const botaoConfirmar = screen.getByRole("button", { name: "Confirmar recusa" });
    expect(botaoConfirmar).toBeDisabled();

    fireEvent.change(screen.getByPlaceholderText("Motivo da recusa (obrigatório)"), {
      target: { value: "Escala já coberta" },
    });
    fireEvent.click(botaoConfirmar);

    expect(mutate).toHaveBeenCalledWith(
      { aprovacaoId: "a1", decisao: "reprovar", comentario: "Escala já coberta" },
      expect.anything(),
    );
  });

  it("sem aprovacoes.aprovar, mostra a etapa mas não os botões de decisão", () => {
    configurarPadrao();
    useSessaoCompletaMock.mockReturnValue({
      sessao: { permissoes: ["aprovacoes.ler"] },
      carregando: false,
      erro: null,
    });
    useAprovacoesPendentesMock.mockReturnValue(
      estadoDeSucesso({ dados: [APROVACAO], paginacao: { temMais: false, limite: 5 } }),
    );
    render(<FilaDeAprovacoes />);

    expect(screen.getByText("Maria Souza")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Aprovar" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Recusar" })).not.toBeInTheDocument();
  });
});
