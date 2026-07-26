import type { Meta, StoryObj } from "@storybook/nextjs";

import { AreaDeTexto } from "./textarea";

const meta = {
  title: "Primitivos/AreaDeTexto",
  component: AreaDeTexto,
  args: { placeholder: "Motivo do tratamento..." },
} satisfies Meta<typeof AreaDeTexto>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Padrao: Story = {};
export const Invalida: Story = { args: { "aria-invalid": true, defaultValue: "" } };
export const SomenteLeitura: Story = { args: { readOnly: true, defaultValue: "Texto fixo, nao editavel." } };
export const Desabilitada: Story = { args: { disabled: true, defaultValue: "Texto fixo, nao editavel." } };
