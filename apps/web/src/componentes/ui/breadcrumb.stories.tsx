import type { Meta, StoryObj } from "@storybook/nextjs";

import { Trilha, TrilhaItem, TrilhaLink, TrilhaLista, TrilhaPagina, TrilhaSeparador } from "./breadcrumb";

const meta = {
  title: "Primitivos/Trilha",
  component: Trilha,
} satisfies Meta<typeof Trilha>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Padrao: Story = {
  render: () => (
    <Trilha>
      <TrilhaLista>
        <TrilhaItem>
          <TrilhaLink href="#">Colaboradores</TrilhaLink>
        </TrilhaItem>
        <TrilhaSeparador />
        <TrilhaItem>
          <TrilhaLink href="#">Maria Silva</TrilhaLink>
        </TrilhaItem>
        <TrilhaSeparador />
        <TrilhaItem>
          <TrilhaPagina>Banco de horas</TrilhaPagina>
        </TrilhaItem>
      </TrilhaLista>
    </Trilha>
  ),
};
