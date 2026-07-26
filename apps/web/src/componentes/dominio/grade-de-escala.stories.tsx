import type { Meta, StoryObj } from "@storybook/nextjs";

import { GradeDeEscala, type LinhaDeColaboradorNaGrade } from "./grade-de-escala";

const meta: Meta<typeof GradeDeEscala> = {
  title: "Domínio/GradeDeEscala",
  component: GradeDeEscala,
  parameters: { layout: "padded" },
};

export default meta;
type Story = StoryObj<typeof GradeDeEscala>;

const TURNO_DIA = { id: "t-dia", nome: "Plantão dia", cor: "#4C5FCA" };
const TURNO_NOITE = { id: "t-noite", nome: "Plantão noite", cor: "#591F97" };

const DATAS = ["2026-07-29", "2026-07-30", "2026-07-31", "2026-08-01", "2026-08-02", "2026-08-03"];

const LINHAS: LinhaDeColaboradorNaGrade[] = [
  {
    colaboradorId: "c1",
    nomeColaborador: "Maria Souza",
    celulas: [
      { data: "2026-07-29", turno: TURNO_DIA, tipoDia: "trabalho", cruzaMeiaNoite: true },
      { data: "2026-07-30", tipoDia: "folga" },
      { data: "2026-07-31", turno: TURNO_DIA, tipoDia: "trabalho", cruzaMeiaNoite: true },
      { data: "2026-08-01", tipoDia: "folga" },
      { data: "2026-08-02", turno: TURNO_DIA, tipoDia: "trabalho", cruzaMeiaNoite: true },
      { data: "2026-08-03", tipoDia: "folga" },
    ],
  },
  {
    colaboradorId: "c2",
    nomeColaborador: "João Lima",
    celulas: [
      { data: "2026-07-29", tipoDia: "folga" },
      { data: "2026-07-30", turno: TURNO_NOITE, tipoDia: "trabalho", cruzaMeiaNoite: true },
      { data: "2026-07-31", tipoDia: "folga" },
      { data: "2026-08-01", tipoDia: "feriado" },
      { data: "2026-08-02", tipoDia: "folga" },
      { data: "2026-08-03", turno: TURNO_NOITE, tipoDia: "trabalho", cruzaMeiaNoite: true },
    ],
  },
];

export const Escala12x36AtravessandoMes: Story = {
  name: "Escala 12x36 atravessando a virada de mês",
  args: { datas: DATAS, linhas: LINHAS },
};
