import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";

import { SeletorDePeriodo, type AtalhoDePeriodo } from "@/componentes/dominio/seletor-de-periodo";

function SeletorControlado({ atalhos = [] }: { atalhos?: AtalhoDePeriodo[] }) {
  const [intervalo, setIntervalo] = useState<{ inicio: string | null; fim: string | null }>({
    inicio: null,
    fim: null,
  });
  return (
    <SeletorDePeriodo
      inicio={intervalo.inicio}
      fim={intervalo.fim}
      atalhos={atalhos}
      mesInicial={{ ano: 2026, mes: 7 }}
      aoSelecionarIntervalo={(inicio, fim) => {
        setIntervalo({ inicio, fim });
      }}
    />
  );
}

describe("SeletorDePeriodo", () => {
  it("tem um aria-label por dia com a data completa", () => {
    render(<SeletorControlado />);
    expect(screen.getByRole("button", { name: "15/07/2026" })).toBeInTheDocument();
  });

  it("e inteiramente operavel pelo teclado: seta para a direita move o foco um dia", async () => {
    const usuario = userEvent.setup();
    render(<SeletorControlado />);

    const dia1 = screen.getByRole("button", { name: "01/07/2026" });
    dia1.focus();
    expect(dia1).toHaveFocus();

    await usuario.keyboard("{ArrowRight}");
    expect(screen.getByRole("button", { name: "02/07/2026" })).toHaveFocus();
  });

  it("PageDown avanca um mes mantendo a navegacao por teclado", async () => {
    const usuario = userEvent.setup();
    render(<SeletorControlado />);

    const dia1 = screen.getByRole("button", { name: "01/07/2026" });
    dia1.focus();
    await usuario.keyboard("{PageDown}");

    expect(screen.getByText(/agosto de 2026/)).toBeInTheDocument();
  });

  it("seleciona um intervalo com dois cliques e anuncia o resultado", async () => {
    const usuario = userEvent.setup();
    render(<SeletorControlado />);

    await usuario.click(screen.getByRole("button", { name: "10/07/2026" }));
    await usuario.click(screen.getByRole("button", { name: "15/07/2026" }));

    expect(screen.getByRole("status")).toHaveTextContent(
      "Intervalo selecionado: de 10/07/2026 até 15/07/2026",
    );
  });

  it("valida intervalo invertido sem aceitar a selecao", async () => {
    const usuario = userEvent.setup();
    render(<SeletorControlado />);

    await usuario.click(screen.getByRole("button", { name: "15/07/2026" }));
    await usuario.click(screen.getByRole("button", { name: "10/07/2026" }));

    expect(screen.getByRole("alert")).toHaveTextContent(/não pode ser anterior/i);
    // O intervalo nao avancou: ainda so ha o dia 15 selecionado (dia unico), sem fim antes do inicio.
    expect(screen.getByRole("status")).toHaveTextContent("Dia selecionado: 15/07/2026");
  });

  it("aplica atalho de periodo", async () => {
    const usuario = userEvent.setup();
    const atalhos: AtalhoDePeriodo[] = [
      { id: "mes-corrente", rotulo: "Mês corrente", inicio: "2026-07-01", fim: "2026-07-31" },
    ];
    render(<SeletorControlado atalhos={atalhos} />);

    await usuario.click(screen.getByRole("button", { name: "Mês corrente" }));

    expect(screen.getByRole("status")).toHaveTextContent(
      "Intervalo selecionado: de 01/07/2026 até 31/07/2026",
    );
  });
});
