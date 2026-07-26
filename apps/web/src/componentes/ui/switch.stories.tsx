import type { Meta, StoryObj } from "@storybook/nextjs";

import { Interruptor } from "./switch";
import { Rotulo } from "./label";

const meta = {
  title: "Primitivos/Interruptor",
  component: Interruptor,
} satisfies Meta<typeof Interruptor>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Padrao: Story = {
  render: (args) => (
    <div className="flex items-center gap-2">
      <Interruptor id="int-padrao" {...args} />
      <Rotulo htmlFor="int-padrao">Notificar por e-mail</Rotulo>
    </div>
  ),
};

export const Ligado: Story = { ...Padrao, args: { defaultChecked: true } };
export const Desabilitado: Story = { ...Padrao, args: { disabled: true } };

export const AlvoDeToque: Story = {
  name: "Alvo de toque (44x44)",
  render: (args) => (
    <div className="flex items-center gap-2">
      <Interruptor id="int-toque" tamanho="toque" {...args} />
      <Rotulo htmlFor="int-toque">Notificar por e-mail (variante de toque)</Rotulo>
    </div>
  ),
};
