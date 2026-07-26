import type { Meta, StoryObj } from "@storybook/nextjs";

import { Botao } from "./button";
import { Cartao, CartaoCabecalho, CartaoConteudo, CartaoDescricao, CartaoRodape, CartaoTitulo } from "./card";

const meta = {
  title: "Primitivos/Cartao",
  component: Cartao,
} satisfies Meta<typeof Cartao>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Padrao: Story = {
  render: () => (
    <Cartao className="w-80">
      <CartaoCabecalho>
        <CartaoTitulo>Saldo de banco de horas</CartaoTitulo>
        <CartaoDescricao>Vinculo — Maria Silva</CartaoDescricao>
      </CartaoCabecalho>
      <CartaoConteudo>
        <p className="estilo-numero-destaque">12:40</p>
        <p className="estilo-legenda text-texto-terciario">Saldo credor</p>
      </CartaoConteudo>
      <CartaoRodape>
        <Botao variant="sutil" tamanho="compacto">
          Ver extrato
        </Botao>
      </CartaoRodape>
    </Cartao>
  ),
};
