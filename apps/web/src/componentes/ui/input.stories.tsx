import type { Meta, StoryObj } from "@storybook/nextjs";

import { Entrada } from "./input";
import { Rotulo } from "./label";
import { MensagemDeErro } from "./mensagem-de-erro";

const meta = {
  title: "Primitivos/Entrada",
  component: Entrada,
  args: { placeholder: "00.000.000/0000-00" },
} satisfies Meta<typeof Entrada>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Padrao: Story = {};

export const ComRotulo: Story = {
  render: (args) => (
    <div className="grid gap-1.5">
      <Rotulo htmlFor="cnpj-story">CNPJ da empresa</Rotulo>
      <Entrada id="cnpj-story" {...args} />
    </div>
  ),
};

export const Invalida: Story = {
  render: (args) => (
    <div className="grid gap-1.5">
      <Rotulo htmlFor="cnpj-invalido">CNPJ da empresa</Rotulo>
      <Entrada id="cnpj-invalido" aria-invalid defaultValue="12.345.678/0001-00" {...args} />
      <MensagemDeErro>CNPJ invalido — confira o digito verificador.</MensagemDeErro>
    </div>
  ),
};

export const SomenteLeitura: Story = { args: { readOnly: true, defaultValue: "12.345.678/0001-99" } };
export const Desabilitada: Story = { args: { disabled: true, defaultValue: "12.345.678/0001-99" } };
export const Obrigatoria: Story = {
  render: (args) => (
    <div className="grid gap-1.5">
      <Rotulo htmlFor="obrigatoria-story">
        E-mail <span aria-hidden="true">*</span>
      </Rotulo>
      <Entrada id="obrigatoria-story" required type="email" {...args} placeholder="voce@empresa.com.br" />
    </div>
  ),
};
