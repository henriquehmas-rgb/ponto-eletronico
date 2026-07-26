import type { ComponentProps } from "react";
import type { Meta, StoryObj } from "@storybook/nextjs";

import { Alerta, AlertaDescricao, AlertaTitulo } from "./alert";

const meta = {
  title: "Primitivos/Alerta",
  component: Alerta,
} satisfies Meta<typeof Alerta>;

export default meta;
type Story = StoryObj<typeof meta>;

function alerta(variant: NonNullable<ComponentProps<typeof Alerta>["variant"]>, titulo: string, descricao: string): Story {
  return {
    args: { variant },
    render: (args) => (
      <Alerta {...args}>
        <AlertaTitulo>{titulo}</AlertaTitulo>
        <AlertaDescricao>{descricao}</AlertaDescricao>
      </Alerta>
    ),
  };
}

export const Neutro: Story = alerta("neutro", "Periodo em conferencia", "O espelho previo ainda pode mudar.");
export const Sucesso: Story = alerta("sucesso", "Fechamento concluido", "Nenhuma ocorrencia pendente neste periodo.");
export const Atencao: Story = alerta("atencao", "Banco de horas vencendo", "42 minutos credores vencem em 12 dias.");
export const Erro: Story = alerta("erro", "Falha no envio do AFD", "O arquivo nao foi assinado — tente novamente.");
export const Info: Story = alerta("info", "Sincronizacao em andamento", "3 itens da fila offline sendo processados.");
