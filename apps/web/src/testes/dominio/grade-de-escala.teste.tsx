import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { GradeDeEscala, type LinhaDeColaboradorNaGrade } from "@/componentes/dominio/grade-de-escala";

/** 12x36: dois dias no ciclo, atravessando a virada de julho para agosto. */
const DATAS_ATRAVESSANDO_MES = ["2026-07-30", "2026-07-31", "2026-08-01", "2026-08-02"];

const TURNO_12X36 = { id: "t1", nome: "Plantão 12h", cor: "#4C5FCA" };

const LINHA_12X36: LinhaDeColaboradorNaGrade = {
  colaboradorId: "c1",
  nomeColaborador: "Maria Souza",
  celulas: [
    { data: "2026-07-30", turno: TURNO_12X36, tipoDia: "trabalho", cruzaMeiaNoite: true },
    { data: "2026-07-31", tipoDia: "folga" },
    { data: "2026-08-01", turno: TURNO_12X36, tipoDia: "trabalho", cruzaMeiaNoite: true },
    { data: "2026-08-02", tipoDia: "folga" },
  ],
};

describe("GradeDeEscala", () => {
  it("renderiza 12x36 atravessando a virada de mes", () => {
    render(<GradeDeEscala datas={DATAS_ATRAVESSANDO_MES} linhas={[LINHA_12X36]} />);

    expect(screen.getByText("Maria Souza")).toBeInTheDocument();
    const linha = screen.getByRole("row", { name: /Maria Souza/ });
    expect(within(linha).getAllByText("Plantão 12h")).toHaveLength(2);
    expect(within(linha).getAllByText("Folga")).toHaveLength(2);
    // A celula de virada de meia-noite carrega a seta, indicando que o turno
    // continua no dia seguinte, sem criar uma segunda celula para ele.
    expect(within(linha).getAllByLabelText("continua no dia seguinte")).toHaveLength(2);
  });

  it("marca o cabecalho de cada dia com data e dia da semana", () => {
    render(<GradeDeEscala datas={DATAS_ATRAVESSANDO_MES} linhas={[LINHA_12X36]} />);
    const cabecalhos = screen.getAllByRole("columnheader");
    // Primeira coluna e "Colaborador"; as demais são as datas.
    expect(cabecalhos[0]).toHaveTextContent("Colaborador");
    expect(cabecalhos[1]).toHaveTextContent("30");
    expect(cabecalhos[3]).toHaveTextContent("01");
  });

  it("distingue feriado e DSR por texto, nao so por cor", () => {
    const linha: LinhaDeColaboradorNaGrade = {
      colaboradorId: "c2",
      nomeColaborador: "João Lima",
      celulas: [
        { data: "2026-07-30", tipoDia: "feriado" },
        { data: "2026-07-31", tipoDia: "dsr" },
        { data: "2026-08-01", tipoDia: "compensado" },
        { data: "2026-08-02", turno: TURNO_12X36, tipoDia: "trabalho" },
      ],
    };
    render(<GradeDeEscala datas={DATAS_ATRAVESSANDO_MES} linhas={[linha]} />);
    expect(screen.getByText("Feriado")).toBeInTheDocument();
    expect(screen.getByText("DSR")).toBeInTheDocument();
    expect(screen.getByText("Compensado")).toBeInTheDocument();
  });
});
