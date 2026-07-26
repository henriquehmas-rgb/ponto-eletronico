import type { Meta, StoryObj } from "@storybook/nextjs";

import { CartaoDeSaldoDeBanco } from "./cartao-de-saldo-de-banco";

const DATA_REFERENCIA = new Date("2026-07-25T12:00:00-03:00");

const meta: Meta<typeof CartaoDeSaldoDeBanco> = {
  title: "Domínio/CartaoDeSaldoDeBanco",
  component: CartaoDeSaldoDeBanco,
  parameters: { layout: "padded" },
  args: { dataReferencia: DATA_REFERENCIA, contaCodigo: "principal" },
};

export default meta;
type Story = StoryObj<typeof CartaoDeSaldoDeBanco>;

export const SaldoCredor: Story = {
  args: { saldoMinutos: 690, variacaoMinutos: 60 },
};

export const SaldoDevedor: Story = {
  args: { saldoMinutos: -125, variacaoMinutos: -30 },
};

export const SaldoZerado: Story = {
  args: { saldoMinutos: 0 },
};

export const VencimentoEmMenosDe30Dias: Story = {
  name: "Vencimento em menos de 30 dias",
  args: {
    saldoMinutos: 900,
    aVencer30Minutos: 240,
    proximoVencimentoEm: "2026-08-10T00:00:00-03:00",
  },
};
