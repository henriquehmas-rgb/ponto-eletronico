import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { CartaoDeSaldoDeBanco } from "@/componentes/dominio/cartao-de-saldo-de-banco";

const AGORA = new Date("2026-07-25T12:00:00-03:00");

describe("CartaoDeSaldoDeBanco", () => {
  it("mostra saldo credor com rotulo textual, nao so cor", () => {
    render(<CartaoDeSaldoDeBanco saldoMinutos={90} dataReferencia={AGORA} />);
    expect(screen.getByText("Saldo credor")).toBeInTheDocument();
    expect(screen.getByText("+1:30")).toBeInTheDocument();
  });

  it("mostra saldo devedor com rotulo textual", () => {
    render(<CartaoDeSaldoDeBanco saldoMinutos={-90} dataReferencia={AGORA} />);
    expect(screen.getByText("Saldo devedor")).toBeInTheDocument();
    expect(screen.getByText("-1:30")).toBeInTheDocument();
  });

  it("mostra saldo zerado", () => {
    render(<CartaoDeSaldoDeBanco saldoMinutos={0} dataReferencia={AGORA} />);
    expect(screen.getByText("Saldo zerado")).toBeInTheDocument();
    expect(screen.getByText("0:00")).toBeInTheDocument();
  });

  it("destaca vencimento em menos de 30 dias", () => {
    render(
      <CartaoDeSaldoDeBanco
        saldoMinutos={600}
        aVencer30Minutos={120}
        proximoVencimentoEm="2026-08-10T00:00:00-03:00"
        dataReferencia={AGORA}
      />,
    );
    expect(screen.getByRole("status")).toHaveTextContent(/vencem em 16 dias/);
  });

  it("nao destaca vencimento quando falta mais de 30 dias", () => {
    render(
      <CartaoDeSaldoDeBanco
        saldoMinutos={600}
        aVencer30Minutos={120}
        proximoVencimentoEm="2026-12-25T00:00:00-03:00"
        dataReferencia={AGORA}
      />,
    );
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("mostra a variacao no periodo com sinal explicito", () => {
    render(<CartaoDeSaldoDeBanco saldoMinutos={600} variacaoMinutos={-30} dataReferencia={AGORA} />);
    expect(screen.getByText(/-0:30 no período/)).toBeInTheDocument();
  });
});
