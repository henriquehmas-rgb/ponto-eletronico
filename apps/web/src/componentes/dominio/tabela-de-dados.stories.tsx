import type { Meta, StoryObj } from "@storybook/nextjs";

import { TabelaDeDados, type ColunaDeTabela } from "./tabela-de-dados";

interface LinhaDeApuracao {
  id: string;
  colaborador: string;
  data: string;
  saldoMinutos: number;
}

const LINHAS: LinhaDeApuracao[] = [
  { id: "1", colaborador: "Ana Paula", data: "2026-07-21", saldoMinutos: 30 },
  { id: "2", colaborador: "Beatriz Silva", data: "2026-07-21", saldoMinutos: -15 },
  { id: "3", colaborador: "Carlos Souza", data: "2026-07-21", saldoMinutos: 0 },
  { id: "4", colaborador: "Diego Ramos", data: "2026-07-22", saldoMinutos: 90 },
  { id: "5", colaborador: "Elaine Costa", data: "2026-07-22", saldoMinutos: -45 },
];

const COLUNAS: ColunaDeTabela<LinhaDeApuracao>[] = [
  {
    id: "colaborador",
    cabecalho: "Colaborador",
    renderizarCelula: (linha) => linha.colaborador,
    ordenavel: true,
    valorDeOrdenacao: (linha) => linha.colaborador,
  },
  { id: "data", cabecalho: "Data", renderizarCelula: (linha) => linha.data, larguraPx: 120 },
  {
    id: "saldo",
    cabecalho: "Saldo (min)",
    renderizarCelula: (linha) => String(linha.saldoMinutos),
    ordenavel: true,
    valorDeOrdenacao: (linha) => linha.saldoMinutos,
    larguraPx: 120,
  },
];

const meta: Meta<typeof TabelaDeDados<LinhaDeApuracao>> = {
  title: "Domínio/TabelaDeDados",
  component: TabelaDeDados<LinhaDeApuracao>,
  parameters: { layout: "padded" },
  args: {
    linhas: LINHAS,
    colunas: COLUNAS,
    obterId: (linha: LinhaDeApuracao) => linha.id,
    alturaContainerPx: 260,
  },
};

export default meta;
type Story = StoryObj<typeof TabelaDeDados<LinhaDeApuracao>>;

export const Padrao: Story = {};

export const Selecionavel: Story = {
  args: { selecionaveis: true },
};

export const EstadoVazio: Story = {
  name: "Estado vazio",
  args: { linhas: [] },
};

export const EstadoDeCarregamento: Story = {
  name: "Estado de carregamento",
  args: { carregando: true },
};
