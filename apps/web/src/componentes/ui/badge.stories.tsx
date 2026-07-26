import type { Meta, StoryObj } from "@storybook/nextjs";

import { Selo } from "./badge";

const meta = {
  title: "Primitivos/Selo",
  component: Selo,
  args: { children: "Aprovado" },
} satisfies Meta<typeof Selo>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Neutro: Story = { args: { variant: "neutro" } };
export const Primario: Story = { args: { variant: "primario" } };
export const Sucesso: Story = { args: { variant: "sucesso", children: "Fechamento sem pendencia" } };
export const Atencao: Story = { args: { variant: "atencao", children: "Vence em 20 dias" } };
export const Erro: Story = { args: { variant: "erro", children: "Marcacao suspeita" } };
export const Info: Story = { args: { variant: "info", children: "Processando" } };

export const TodasAsVariantes: Story = {
  render: () => (
    <div className="flex flex-wrap gap-2">
      <Selo variant="neutro">Neutro</Selo>
      <Selo variant="primario">Primario</Selo>
      <Selo variant="sucesso">Sucesso</Selo>
      <Selo variant="atencao">Atencao</Selo>
      <Selo variant="erro">Erro</Selo>
      <Selo variant="info">Info</Selo>
    </div>
  ),
};
