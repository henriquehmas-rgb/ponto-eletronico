import type { Meta, StoryObj } from "@storybook/nextjs";

import { GrupoDeRadio, ItemDeRadio } from "./radio-group";
import { Rotulo } from "./label";

const meta = {
  title: "Primitivos/GrupoDeRadio",
  component: GrupoDeRadio,
} satisfies Meta<typeof GrupoDeRadio>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Padrao: Story = {
  render: () => (
    <GrupoDeRadio defaultValue="6x1" aria-label="Ciclo de escala">
      {(["5x2", "6x1", "12x36"] as const).map((ciclo) => (
        <div key={ciclo} className="flex items-center gap-2">
          <ItemDeRadio value={ciclo} id={`ciclo-${ciclo}`} />
          <Rotulo htmlFor={`ciclo-${ciclo}`}>{ciclo}</Rotulo>
        </div>
      ))}
    </GrupoDeRadio>
  ),
};

export const Desabilitado: Story = { ...Padrao, args: { disabled: true } };

export const AlvoDeToque: Story = {
  name: "Alvo de toque (44x44)",
  render: () => (
    <GrupoDeRadio defaultValue="6x1" aria-label="Ciclo de escala">
      {(["5x2", "6x1", "12x36"] as const).map((ciclo) => (
        <div key={ciclo} className="flex items-center gap-2">
          <ItemDeRadio value={ciclo} id={`ciclo-toque-${ciclo}`} tamanho="toque" />
          <Rotulo htmlFor={`ciclo-toque-${ciclo}`}>{ciclo}</Rotulo>
        </div>
      ))}
    </GrupoDeRadio>
  ),
};
