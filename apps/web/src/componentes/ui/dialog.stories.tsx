import type { Meta, StoryObj } from "@storybook/nextjs";

import { Botao } from "./button";
import {
  Dialogo,
  DialogoCabecalho,
  DialogoConteudo,
  DialogoDescricao,
  DialogoRodape,
  DialogoTitulo,
  DialogoGatilho,
  DialogoFechar,
} from "./dialog";

const meta = {
  title: "Primitivos/Dialogo",
  component: Dialogo,
} satisfies Meta<typeof Dialogo>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Padrao: Story = {
  render: () => (
    <Dialogo>
      <DialogoGatilho asChild>
        <Botao>Abrir tratamento</Botao>
      </DialogoGatilho>
      <DialogoConteudo>
        <DialogoCabecalho>
          <DialogoTitulo>Registrar tratamento</DialogoTitulo>
          <DialogoDescricao>
            O tratamento se soma a marcacao na apuracao; a marcacao original nunca e alterada.
          </DialogoDescricao>
        </DialogoCabecalho>
        <DialogoRodape>
          <DialogoFechar asChild>
            <Botao variant="secundaria">Cancelar</Botao>
          </DialogoFechar>
          <Botao>Salvar tratamento</Botao>
        </DialogoRodape>
      </DialogoConteudo>
    </Dialogo>
  ),
};

export const AbertoPorPadrao: Story = { ...Padrao, args: { defaultOpen: true } };
