import type { Meta, StoryObj } from "@storybook/nextjs";
import { Mail } from "lucide-react";

import { Botao } from "./button";

/**
 * Botao — primitivo de formulario. Quatro variantes (`primaria`, `secundaria`,
 * `sutil`, `destrutiva`) e cinco tamanhos, os tres primeiros vindos direto de
 * `--dimensao-altura-controle` (36 px), `--dimensao-altura-controle-compacta`
 * (28 px) e `--dimensao-altura-controle-toque` (44 px).
 */
const meta = {
  title: "Primitivos/Botao",
  component: Botao,
  args: {
    children: "Registrar marcacao",
    variant: "primaria",
    tamanho: "padrao",
  },
  argTypes: {
    variant: {
      control: "select",
      options: ["primaria", "secundaria", "sutil", "destrutiva"],
    },
    tamanho: {
      control: "select",
      options: ["padrao", "compacto", "toque", "icone", "icone-toque"],
    },
  },
} satisfies Meta<typeof Botao>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Primaria: Story = { args: { variant: "primaria" } };
export const Secundaria: Story = { args: { variant: "secundaria" } };
export const Sutil: Story = { args: { variant: "sutil" } };
export const Destrutiva: Story = { args: { variant: "destrutiva", children: "Excluir cadastro" } };

export const Desabilitado: Story = {
  args: { variant: "primaria", disabled: true },
};

export const Toque: Story = {
  name: "Alvo de toque (44x44)",
  args: { variant: "primaria", tamanho: "toque" },
};

export const Icone: Story = {
  args: { variant: "secundaria", tamanho: "icone", children: <Mail aria-hidden="true" /> },
  render: (args) => (
    <Botao {...args} aria-label="Enviar e-mail">
      <Mail aria-hidden="true" />
    </Botao>
  ),
};

export const TodasAsVariantes: Story = {
  render: () => (
    <div className="flex flex-wrap items-center gap-3">
      <Botao variant="primaria">Primaria</Botao>
      <Botao variant="secundaria">Secundaria</Botao>
      <Botao variant="sutil">Sutil</Botao>
      <Botao variant="destrutiva">Destrutiva</Botao>
      <Botao variant="primaria" disabled>
        Desabilitado
      </Botao>
    </div>
  ),
};
