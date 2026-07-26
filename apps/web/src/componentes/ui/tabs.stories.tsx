import type { Meta, StoryObj } from "@storybook/nextjs";

import { Abas, AbaGatilho, ConteudoDaAba, ListaDeAbas } from "./tabs";

const meta = {
  title: "Primitivos/Abas",
  component: Abas,
} satisfies Meta<typeof Abas>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Padrao: Story = {
  render: () => (
    <Abas defaultValue="apuracao" className="w-96">
      <ListaDeAbas>
        <AbaGatilho value="apuracao">Apuracao</AbaGatilho>
        <AbaGatilho value="banco-de-horas">Banco de horas</AbaGatilho>
        <AbaGatilho value="ocorrencias" disabled>
          Ocorrencias
        </AbaGatilho>
      </ListaDeAbas>
      <ConteudoDaAba value="apuracao">Horas normais, extras e adicional noturno do dia.</ConteudoDaAba>
      <ConteudoDaAba value="banco-de-horas">Saldo credor/devedor e vencimento.</ConteudoDaAba>
      <ConteudoDaAba value="ocorrencias">Sem ocorrencias no periodo.</ConteudoDaAba>
    </Abas>
  ),
};
