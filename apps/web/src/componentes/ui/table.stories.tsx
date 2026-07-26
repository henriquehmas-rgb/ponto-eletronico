import type { Meta, StoryObj } from "@storybook/nextjs";

import {
  TabelaBase,
  TabelaBaseCabecalho,
  TabelaBaseCabecalhoDeColuna,
  TabelaBaseCelula,
  TabelaBaseCorpo,
  TabelaBaseLegenda,
  TabelaBaseLinha,
} from "./table";

const meta = {
  title: "Primitivos/TabelaBase",
  component: TabelaBase,
} satisfies Meta<typeof TabelaBase>;

export default meta;
type Story = StoryObj<typeof meta>;

const LINHAS = [
  { colaborador: "Maria Silva", canal: "terminal", nsr: "000482", situacao: "normal" },
  { colaborador: "Joao Pereira", canal: "mobile", nsr: "000483", situacao: "suspeita" },
];

export const Padrao: Story = {
  render: () => (
    <TabelaBase>
      <TabelaBaseLegenda>Marcacoes do dia 24/07/2026</TabelaBaseLegenda>
      <TabelaBaseCabecalho>
        <TabelaBaseLinha>
          <TabelaBaseCabecalhoDeColuna aria-sort="none">Colaborador</TabelaBaseCabecalhoDeColuna>
          <TabelaBaseCabecalhoDeColuna>Canal</TabelaBaseCabecalhoDeColuna>
          <TabelaBaseCabecalhoDeColuna>NSR</TabelaBaseCabecalhoDeColuna>
          <TabelaBaseCabecalhoDeColuna>Situacao</TabelaBaseCabecalhoDeColuna>
        </TabelaBaseLinha>
      </TabelaBaseCabecalho>
      <TabelaBaseCorpo>
        {LINHAS.map((linha) => (
          <TabelaBaseLinha key={linha.nsr}>
            <TabelaBaseCelula>{linha.colaborador}</TabelaBaseCelula>
            <TabelaBaseCelula>{linha.canal}</TabelaBaseCelula>
            <TabelaBaseCelula className="estilo-identificador">{linha.nsr}</TabelaBaseCelula>
            <TabelaBaseCelula>{linha.situacao}</TabelaBaseCelula>
          </TabelaBaseLinha>
        ))}
      </TabelaBaseCorpo>
    </TabelaBase>
  ),
};
