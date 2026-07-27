import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ConfirmacaoDeRegistro } from "./confirmacao-de-registro";

describe("ConfirmacaoDeRegistro", () => {
  it("mostra o comprovante, o NSR e o horário em caso de sucesso", () => {
    render(
      <ConfirmacaoDeRegistro
        variante="sucesso"
        numeroDoComprovante="123"
        nsr={42}
        horario="08:02"
      />,
    );
    expect(screen.getByText(/ponto registrado/i)).toBeInTheDocument();
    expect(screen.getByText(/123/)).toBeInTheDocument();
    expect(screen.getByText(/42/)).toBeInTheDocument();
    expect(screen.getByText(/08:02/)).toBeInTheDocument();
    expect(screen.queryByText(/gestor vai revisar/i)).not.toBeInTheDocument();
  });

  it("mostra uma nota neutra (nunca alarmante) em sucesso com revisão", () => {
    render(
      <ConfirmacaoDeRegistro
        variante="sucesso_com_revisao"
        numeroDoComprovante="123"
        nsr={42}
        horario="08:02"
      />,
    );
    expect(screen.getByText(/gestor vai revisar/i)).toBeInTheDocument();
  });

  it("mostra a mensagem do dicionário de erros quando recusado", () => {
    render(<ConfirmacaoDeRegistro variante="recusado" mensagem="Câmera virtual detectada." />);
    expect(screen.getByText(/não foi possível confirmar o registro/i)).toBeInTheDocument();
    expect(screen.getByText(/câmera virtual detectada/i)).toBeInTheDocument();
  });

  it("anuncia a confirmação via aria-live (nunca atrasada por animação)", () => {
    render(
      <ConfirmacaoDeRegistro
        variante="sucesso"
        numeroDoComprovante="123"
        nsr={42}
        horario="08:02"
      />,
    );
    expect(screen.getByRole("alert")).toHaveAttribute("aria-live", "polite");
  });
});
