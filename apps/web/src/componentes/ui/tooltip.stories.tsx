import type { Meta, StoryObj } from "@storybook/nextjs";

import { Botao } from "./button";
import { Dica, DicaConteudo, DicaGatilho, ProvedorDeDica } from "./tooltip";

const meta = {
  title: "Primitivos/Dica",
  component: Dica,
  decorators: [(Story) => <ProvedorDeDica><Story /></ProvedorDeDica>],
} satisfies Meta<typeof Dica>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Padrao: Story = {
  render: () => (
    <Dica>
      <DicaGatilho asChild>
        <Botao variant="sutil" tamanho="icone" aria-label="Ajuda sobre o NSR">
          ?
        </Botao>
      </DicaGatilho>
      <DicaConteudo>Numero Sequencial de Registro — nunca tem lacuna.</DicaConteudo>
    </Dica>
  ),
};
