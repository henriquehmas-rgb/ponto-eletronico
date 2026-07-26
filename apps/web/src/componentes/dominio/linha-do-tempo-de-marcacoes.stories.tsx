import type { Meta, StoryObj } from "@storybook/nextjs";

import { LinhaDoTempoDeMarcacoes, type MarcacaoDaLinhaDoTempo } from "./linha-do-tempo-de-marcacoes";

const meta: Meta<typeof LinhaDoTempoDeMarcacoes> = {
  title: "Domínio/LinhaDoTempoDeMarcacoes",
  component: LinhaDoTempoDeMarcacoes,
  parameters: { layout: "padded" },
};

export default meta;
type Story = StoryObj<typeof LinhaDoTempoDeMarcacoes>;

export const DiaVazio: Story = {
  args: { marcacoes: [] },
};

export const MarcacaoImpar: Story = {
  name: "Marcação ímpar (três marcações, sem sentido inferido)",
  args: {
    marcacoes: [
      {
        id: "1",
        datahoraMarcacao: "2026-07-25T08:02:00-03:00",
        canal: "mobile",
        nsr: 100234,
        scoreConfianca: 96,
        classificacaoConfianca: "alta",
      },
      {
        id: "2",
        datahoraMarcacao: "2026-07-25T12:00:00-03:00",
        canal: "terminal",
        nsr: 100235,
        scoreConfianca: 100,
        classificacaoConfianca: "alta",
      },
      {
        id: "3",
        datahoraMarcacao: "2026-07-25T13:01:00-03:00",
        canal: "terminal",
        nsr: 100236,
        scoreConfianca: 100,
        classificacaoConfianca: "alta",
      },
    ] satisfies MarcacaoDaLinhaDoTempo[],
  },
};

export const MarcacaoSuspeita: Story = {
  args: {
    marcacoes: [
      {
        id: "1",
        datahoraMarcacao: "2026-07-25T08:02:00-03:00",
        canal: "mobile",
        nsr: 100234,
        scoreConfianca: 42,
        classificacaoConfianca: "baixa",
        estado: "suspeita",
      },
    ] satisfies MarcacaoDaLinhaDoTempo[],
  },
};

export const MarcacaoOfflinePendente: Story = {
  name: "Marcação pendente de envio offline",
  args: {
    marcacoes: [
      {
        id: "1",
        datahoraMarcacao: "2026-07-25T08:02:00-03:00",
        canal: "mobile",
        estado: "pendenteEnvioOffline",
      },
    ] satisfies MarcacaoDaLinhaDoTempo[],
  },
};
