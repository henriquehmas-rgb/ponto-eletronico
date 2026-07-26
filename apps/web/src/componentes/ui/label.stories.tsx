import type { Meta, StoryObj } from "@storybook/nextjs";

import { Entrada } from "./input";
import { Rotulo } from "./label";

const meta = {
  title: "Primitivos/Rotulo",
  component: Rotulo,
} satisfies Meta<typeof Rotulo>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Padrao: Story = {
  render: () => (
    <div className="grid gap-1.5">
      <Rotulo htmlFor="rotulo-story">Matricula</Rotulo>
      <Entrada id="rotulo-story" placeholder="000123" />
    </div>
  ),
};
