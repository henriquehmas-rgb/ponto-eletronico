import type { Meta, StoryObj } from "@storybook/nextjs";

import { DesafioDeProvaDeVida } from "./desafio-de-prova-de-vida";

const meta = {
  title: "F8/RegistroWebcam/DesafioDeProvaDeVida",
  component: DesafioDeProvaDeVida,
} satisfies Meta<typeof DesafioDeProvaDeVida>;

export default meta;
type Story = StoryObj<typeof meta>;

export const CarregandoModelo: Story = {
  args: { situacao: "carregando_modelo", desafio: null, tentativa: 1, segundosRestantes: 4 },
};

export const DesafioAtivoPiscar: Story = {
  args: {
    situacao: "em_andamento",
    desafio: "piscar_duas_vezes",
    tentativa: 1,
    segundosRestantes: 3,
  },
};

export const DesafioAtivoVirarEsquerda: Story = {
  args: { situacao: "em_andamento", desafio: "virar_esquerda", tentativa: 1, segundosRestantes: 2 },
};

export const ReprovadoNestaTentativa: Story = {
  args: {
    situacao: "reprovado_tentativa",
    desafio: "virar_direita",
    tentativa: 2,
    segundosRestantes: 0,
  },
};
