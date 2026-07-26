import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { Botao } from "@/componentes/ui/button";
import { CaixaDeSelecao } from "@/componentes/ui/checkbox";
import { Entrada } from "@/componentes/ui/input";
import { GrupoDeRadio, ItemDeRadio } from "@/componentes/ui/radio-group";
import { Interruptor } from "@/componentes/ui/switch";

/**
 * T3 do PCF F09a — "teste de teclado prova que cada controle recebe foco por
 * `Tab`, ativa por `Enter`/`Espaco` quando aplicavel, e que o grupo de radio
 * navega por setas".
 */

describe("navegacao por teclado — primitivos de formulario", () => {
  it("Botao recebe foco por Tab e ativa por Enter e por Espaco", async () => {
    const usuario = userEvent.setup();
    const aoClicar = vi.fn();
    render(<Botao onClick={aoClicar}>Registrar</Botao>);

    await usuario.tab();
    expect(screen.getByRole("button", { name: "Registrar" })).toHaveFocus();

    await usuario.keyboard("{Enter}");
    expect(aoClicar).toHaveBeenCalledTimes(1);

    await usuario.keyboard(" ");
    expect(aoClicar).toHaveBeenCalledTimes(2);
  });

  it("Botao desabilitado nao recebe foco por Tab", async () => {
    const usuario = userEvent.setup();
    render(
      <>
        <Botao disabled>Indisponivel</Botao>
        <Botao>Proximo</Botao>
      </>,
    );
    await usuario.tab();
    expect(screen.getByRole("button", { name: "Proximo" })).toHaveFocus();
  });

  it("Entrada recebe foco por Tab e aceita digitacao", async () => {
    const usuario = userEvent.setup();
    render(<Entrada aria-label="Matricula" />);
    await usuario.tab();
    const campo = screen.getByLabelText("Matricula");
    expect(campo).toHaveFocus();
    await usuario.keyboard("000123");
    expect(campo).toHaveValue("000123");
  });

  it("CaixaDeSelecao recebe foco por Tab e alterna por Espaco", async () => {
    const usuario = userEvent.setup();
    render(<CaixaDeSelecao aria-label="Aceito os termos" />);
    await usuario.tab();
    const caixa = screen.getByRole("checkbox", { name: "Aceito os termos" });
    expect(caixa).toHaveFocus();
    expect(caixa).toHaveAttribute("aria-checked", "false");
    await usuario.keyboard(" ");
    expect(caixa).toHaveAttribute("aria-checked", "true");
  });

  it("Interruptor recebe foco por Tab e alterna por Espaco", async () => {
    const usuario = userEvent.setup();
    render(<Interruptor aria-label="Notificar por e-mail" />);
    await usuario.tab();
    const interruptor = screen.getByRole("switch", { name: "Notificar por e-mail" });
    expect(interruptor).toHaveFocus();
    expect(interruptor).toHaveAttribute("aria-checked", "false");
    await usuario.keyboard(" ");
    expect(interruptor).toHaveAttribute("aria-checked", "true");
  });

  function GrupoDeRadioControlavel() {
    const [valor, setValor] = useState("5x2");
    return (
      <GrupoDeRadio aria-label="Ciclo de escala" value={valor} onValueChange={setValor}>
        <ItemDeRadio value="5x2" aria-label="5x2" />
        <ItemDeRadio value="6x1" aria-label="6x1" />
        <ItemDeRadio value="12x36" aria-label="12x36" />
      </GrupoDeRadio>
    );
  }

  it("GrupoDeRadio navega entre itens pelas setas do teclado", async () => {
    const usuario = userEvent.setup();
    render(<GrupoDeRadioControlavel />);

    await usuario.tab();
    expect(screen.getByRole("radio", { name: "5x2" })).toHaveFocus();

    await usuario.keyboard("{ArrowDown}");
    expect(screen.getByRole("radio", { name: "6x1" })).toHaveFocus();

    await usuario.keyboard("{ArrowDown}");
    expect(screen.getByRole("radio", { name: "12x36" })).toHaveFocus();

    await usuario.keyboard("{ArrowUp}");
    expect(screen.getByRole("radio", { name: "6x1" })).toHaveFocus();
  });

  it("ItemDeRadio ativa por Espaco quando focado", async () => {
    const usuario = userEvent.setup();
    render(<GrupoDeRadioControlavel />);

    // Tab entra no grupo no item JA selecionado (roving tabindex — 5x2 e o
    // `value` controlado); navega ate um item ainda nao selecionado e ativa
    // explicitamente por teclado.
    await usuario.tab();
    await usuario.keyboard("{ArrowDown}"); // foco em 6x1
    const item6x1 = screen.getByRole("radio", { name: "6x1" });
    expect(item6x1).toHaveFocus();

    await usuario.keyboard(" ");
    await waitFor(() => {
      expect(item6x1).toHaveAttribute("aria-checked", "true");
    });
    expect(screen.getByRole("radio", { name: "5x2" })).toHaveAttribute("aria-checked", "false");
  });
});
