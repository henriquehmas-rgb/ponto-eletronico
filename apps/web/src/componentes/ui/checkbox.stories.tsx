import type { Meta, StoryObj } from "@storybook/nextjs";

import { CaixaDeSelecao } from "./checkbox";
import { Rotulo } from "./label";

const meta = {
  title: "Primitivos/CaixaDeSelecao",
  component: CaixaDeSelecao,
} satisfies Meta<typeof CaixaDeSelecao>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Padrao: Story = {
  render: (args) => (
    <div className="flex items-center gap-2">
      <CaixaDeSelecao id="cs-padrao" {...args} />
      <Rotulo htmlFor="cs-padrao">Aceito os termos de consentimento LGPD</Rotulo>
    </div>
  ),
};

export const Marcada: Story = { ...Padrao, args: { defaultChecked: true } };
export const Desabilitada: Story = { ...Padrao, args: { disabled: true } };
export const Invalida: Story = { ...Padrao, args: { "aria-invalid": true } };

export const AlvoDeToque: Story = {
  name: "Alvo de toque (44x44)",
  render: (args) => (
    <div className="flex items-center gap-2">
      <CaixaDeSelecao id="cs-toque" tamanho="toque" {...args} />
      <Rotulo htmlFor="cs-toque">Marcar item (variante de toque)</Rotulo>
    </div>
  ),
};
