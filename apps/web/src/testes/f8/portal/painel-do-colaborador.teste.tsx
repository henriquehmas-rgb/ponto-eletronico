import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import PainelDoColaborador from "@/app/eu/page";
import { ErroDaApi } from "@/lib/api";

const useEspelhoDePontoMock = vi.fn();
const useSaldoBancoHorasMock = vi.fn();

vi.mock("@/ganchos/use-espelho-de-ponto", () => ({
  useEspelhoDePonto: (...args: unknown[]) => useEspelhoDePontoMock(...args),
}));
vi.mock("@/ganchos/use-banco-de-horas", () => ({
  useSaldoBancoHoras: (...args: unknown[]) => useSaldoBancoHorasMock(...args),
}));
vi.mock("@/lib/sessao", () => ({
  useSessao: () => ({
    usuario: { id: "u1", nome: "Henrique Mascarenhas", email: "henrique@seeg.com.br" },
    tenant: null,
    autenticado: true,
    carregando: false,
  }),
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

describe("/eu — painel do colaborador (T2)", () => {
  it("estado de carregamento mostra esqueletos", () => {
    useEspelhoDePontoMock.mockReturnValue(estadoDeCarregamento());
    useSaldoBancoHorasMock.mockReturnValue(estadoDeCarregamento());

    render(<PainelDoColaborador />);

    expect(screen.getByRole("heading", { level: 1 })).toBeInTheDocument();
    expect(document.querySelectorAll('[data-slot="esqueleto"]').length).toBeGreaterThan(0);
  });

  it("estado vazio mostra a mensagem de nenhuma marcação", () => {
    useEspelhoDePontoMock.mockReturnValue(
      estadoDeSucesso({ dados: [], paginacao: { temMais: false, limite: 100 } }),
    );
    useSaldoBancoHorasMock.mockReturnValue(estadoDeSucesso({ saldoMinutos: 0 }));

    render(<PainelDoColaborador />);

    expect(screen.getByText("Nenhuma marcação hoje")).toBeInTheDocument();
  });

  it("estado carregado mostra as marcações do dia", () => {
    useEspelhoDePontoMock.mockReturnValue(
      estadoDeSucesso({
        dados: [
          { id: "m1", datahoraMarcacao: "2026-07-26T08:00:00Z", canal: "web", nsr: 42 },
          { id: "m2", datahoraMarcacao: "2026-07-26T12:00:00Z", canal: "web", nsr: 43 },
        ],
        paginacao: { temMais: false, limite: 100 },
      }),
    );
    useSaldoBancoHorasMock.mockReturnValue(
      estadoDeSucesso({ saldoMinutos: 90, contaCodigo: "principal" }),
    );

    render(<PainelDoColaborador />);

    expect(screen.getByText((_, elemento) => elemento?.textContent === "NSR 42 · Web")).toBeInTheDocument();
    expect(screen.getByText((_, elemento) => elemento?.textContent === "NSR 43 · Web")).toBeInTheDocument();
    expect(screen.getByText("Saldo credor")).toBeInTheDocument();
  });

  it("estado de erro mostra mensagem amigável, nunca uma tela quebrada", () => {
    useEspelhoDePontoMock.mockReturnValue(
      estadoDeErro(
        new ErroDaApi(500, {
          type: "about:blank",
          title: "Erro interno",
          status: 500,
          codigo: "PONTO-INT-001",
        }),
      ),
    );
    useSaldoBancoHorasMock.mockReturnValue(estadoDeSucesso({ saldoMinutos: 0 }));

    render(<PainelDoColaborador />);

    expect(screen.getByText("Não foi possível carregar suas marcações")).toBeInTheDocument();
  });

  it("saldo 404 (sem conta de banco de horas) mostra estado vazio, não o alerta de erro", () => {
    useEspelhoDePontoMock.mockReturnValue(
      estadoDeSucesso({ dados: [], paginacao: { temMais: false, limite: 100 } }),
    );
    useSaldoBancoHorasMock.mockReturnValue(
      estadoDeErro(
        new ErroDaApi(404, {
          type: "about:blank",
          title: "Recurso nao encontrado",
          status: 404,
          codigo: "PONTO-REC-001",
        }),
      ),
    );

    render(<PainelDoColaborador />);

    expect(screen.getByText("Sem conta de banco de horas para este perfil.")).toBeInTheDocument();
    expect(screen.queryByText("Não foi possível carregar seu saldo")).not.toBeInTheDocument();
  });

  it('tem um link de destaque para "/eu/registrar"', () => {
    useEspelhoDePontoMock.mockReturnValue(
      estadoDeSucesso({ dados: [], paginacao: { temMais: false, limite: 100 } }),
    );
    useSaldoBancoHorasMock.mockReturnValue(estadoDeSucesso({ saldoMinutos: 0 }));

    render(<PainelDoColaborador />);

    const link = screen.getByRole("link", { name: "Registrar ponto" });
    expect(link).toHaveAttribute("href", "/eu/registrar");
  });
});
