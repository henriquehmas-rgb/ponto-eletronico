import type { Meta, StoryObj } from "@storybook/nextjs";

import { Botao } from "./button";
import { Popover, PopoverConteudo, PopoverGatilho } from "./popover";

const meta = {
  title: "Primitivos/Popover",
  component: Popover,
} satisfies Meta<typeof Popover>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Padrao: Story = {
  render: () => (
    <Popover>
      <PopoverGatilho asChild>
        <Botao variant="secundaria">Score de confianca</Botao>
      </PopoverGatilho>
      <PopoverConteudo>
        <p className="estilo-titulo-cartao">Score 82</p>
        <p className="estilo-corpo mt-1 text-texto-secundario">
          Composto a partir de attestation, RASP, mock location e coerencia geografica.
        </p>
      </PopoverConteudo>
    </Popover>
  ),
};
