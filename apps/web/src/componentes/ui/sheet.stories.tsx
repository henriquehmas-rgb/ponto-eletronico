import type { Meta, StoryObj } from "@storybook/nextjs";

import { Botao } from "./button";
import { Folha, FolhaCabecalho, FolhaConteudo, FolhaDescricao, FolhaTitulo, FolhaGatilho } from "./sheet";

const meta = {
  title: "Primitivos/Folha",
  component: Folha,
} satisfies Meta<typeof Folha>;

export default meta;
type Story = StoryObj<typeof meta>;

export const LadoDireito: Story = {
  render: () => (
    <Folha>
      <FolhaGatilho asChild>
        <Botao>Ver detalhes do vinculo</Botao>
      </FolhaGatilho>
      <FolhaConteudo lado="right">
        <FolhaCabecalho>
          <FolhaTitulo>Vinculo — Maria Silva</FolhaTitulo>
          <FolhaDescricao>Jornada, escala e conta de banco de horas do vinculo.</FolhaDescricao>
        </FolhaCabecalho>
      </FolhaConteudo>
    </Folha>
  ),
};

export const LadoEsquerdo: Story = {
  render: () => (
    <Folha>
      <FolhaGatilho asChild>
        <Botao variant="secundaria">Abrir da esquerda</Botao>
      </FolhaGatilho>
      <FolhaConteudo lado="left">
        <FolhaCabecalho>
          <FolhaTitulo>Filtros</FolhaTitulo>
        </FolhaCabecalho>
      </FolhaConteudo>
    </Folha>
  ),
};

export const AbertoPorPadrao: Story = { ...LadoDireito, args: { defaultOpen: true } };
