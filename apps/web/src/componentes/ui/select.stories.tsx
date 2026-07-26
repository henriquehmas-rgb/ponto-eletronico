import type { Meta, StoryObj } from "@storybook/nextjs";

import {
  Selecao,
  SelecaoConteudo,
  SelecaoGrupo,
  SelecaoItem,
  SelecaoRotulo,
  SelecaoSeparador,
  SelecaoGatilho,
  SelecaoValor,
} from "./select";

const meta = {
  title: "Primitivos/Selecao",
  component: Selecao,
} satisfies Meta<typeof Selecao>;

export default meta;
type Story = StoryObj<typeof meta>;

function ExemploDeCanais() {
  return (
    <Selecao defaultValue="terminal">
      <SelecaoGatilho aria-label="Canal da marcacao">
        <SelecaoValor placeholder="Selecione o canal" />
      </SelecaoGatilho>
      <SelecaoConteudo>
        <SelecaoGrupo>
          <SelecaoRotulo>Canal de origem</SelecaoRotulo>
          <SelecaoItem value="terminal">Terminal</SelecaoItem>
          <SelecaoItem value="mobile">Mobile</SelecaoItem>
          <SelecaoItem value="web">Web</SelecaoItem>
          <SelecaoSeparador />
          <SelecaoItem value="totem">Totem</SelecaoItem>
          <SelecaoItem value="api">API</SelecaoItem>
        </SelecaoGrupo>
      </SelecaoConteudo>
    </Selecao>
  );
}

export const Padrao: Story = { render: () => <ExemploDeCanais /> };

export const Desabilitada: Story = {
  render: () => (
    <Selecao disabled>
      <SelecaoGatilho aria-label="Canal da marcacao">
        <SelecaoValor placeholder="Indisponivel" />
      </SelecaoGatilho>
      <SelecaoConteudo>
        <SelecaoItem value="terminal">Terminal</SelecaoItem>
      </SelecaoConteudo>
    </Selecao>
  ),
};

export const Compacta: Story = {
  render: () => (
    <Selecao defaultValue="terminal">
      <SelecaoGatilho tamanho="compacto" aria-label="Canal da marcacao">
        <SelecaoValor />
      </SelecaoGatilho>
      <SelecaoConteudo>
        <SelecaoItem value="terminal">Terminal</SelecaoItem>
        <SelecaoItem value="mobile">Mobile</SelecaoItem>
      </SelecaoConteudo>
    </Selecao>
  ),
};
