import type { Meta, StoryObj } from "@storybook/nextjs";

import { Separador } from "./separator";

const meta = {
  title: "Primitivos/Separador",
  component: Separador,
} satisfies Meta<typeof Separador>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Horizontal: Story = {
  render: () => (
    <div className="w-64">
      <p className="estilo-corpo">Marcacoes</p>
      <Separador className="my-2" />
      <p className="estilo-corpo">Tratamentos</p>
    </div>
  ),
};

export const Vertical: Story = {
  render: () => (
    <div className="flex h-8 items-center gap-3">
      <span className="estilo-corpo">Terminal</span>
      <Separador orientation="vertical" />
      <span className="estilo-corpo">Mobile</span>
    </div>
  ),
};
