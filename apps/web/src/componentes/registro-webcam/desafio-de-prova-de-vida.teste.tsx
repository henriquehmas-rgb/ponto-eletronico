import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { DesafioDeProvaDeVida } from "./desafio-de-prova-de-vida";

describe("DesafioDeProvaDeVida", () => {
  it("mostra o estado de carregamento do modelo", () => {
    render(
      <DesafioDeProvaDeVida
        situacao="carregando_modelo"
        desafio={null}
        tentativa={1}
        segundosRestantes={4}
      />,
    );
    expect(screen.getByText(/carregando verificação de presença/i)).toBeInTheDocument();
  });

  it("mostra a instrução do desafio e o contador regressivo", () => {
    render(
      <DesafioDeProvaDeVida
        situacao="em_andamento"
        desafio="piscar_duas_vezes"
        tentativa={1}
        segundosRestantes={3}
      />,
    );
    expect(screen.getByText(/pisque duas vezes/i)).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText(/tentativa 1 de 3/i)).toBeInTheDocument();
  });

  it("mostra as instruções corretas para virar à esquerda e à direita", () => {
    const { rerender } = render(
      <DesafioDeProvaDeVida
        situacao="em_andamento"
        desafio="virar_esquerda"
        tentativa={1}
        segundosRestantes={4}
      />,
    );
    expect(screen.getByText(/vire o rosto para a esquerda/i)).toBeInTheDocument();

    rerender(
      <DesafioDeProvaDeVida
        situacao="em_andamento"
        desafio="virar_direita"
        tentativa={1}
        segundosRestantes={4}
      />,
    );
    expect(screen.getByText(/vire o rosto para a direita/i)).toBeInTheDocument();
  });

  it("mostra um aviso neutro ao reprovar uma tentativa (não é a mensagem final)", () => {
    render(
      <DesafioDeProvaDeVida
        situacao="reprovado_tentativa"
        desafio="piscar_duas_vezes"
        tentativa={2}
        segundosRestantes={0}
      />,
    );
    expect(screen.getByText(/não foi dessa vez/i)).toBeInTheDocument();
  });
});
