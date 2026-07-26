import type { Meta, StoryObj } from "@storybook/nextjs";

import { MensagemDeErro } from "./mensagem-de-erro";

const meta = {
  title: "Primitivos/MensagemDeErro",
  component: MensagemDeErro,
  args: { children: "CPF invalido — confira o digito verificador." },
} satisfies Meta<typeof MensagemDeErro>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Padrao: Story = {};
