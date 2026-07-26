import type { Meta, StoryObj } from "@storybook/nextjs";

import {
  Paginacao,
  PaginacaoAnterior,
  PaginacaoConteudo,
  PaginacaoItem,
  PaginacaoLink,
  PaginacaoProxima,
  PaginacaoReticencias,
} from "./pagination";

const meta = {
  title: "Primitivos/Paginacao",
  component: Paginacao,
} satisfies Meta<typeof Paginacao>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Padrao: Story = {
  render: () => (
    <Paginacao>
      <PaginacaoConteudo>
        <PaginacaoItem>
          <PaginacaoAnterior href="#" />
        </PaginacaoItem>
        <PaginacaoItem>
          <PaginacaoLink href="#" ativa>
            1
          </PaginacaoLink>
        </PaginacaoItem>
        <PaginacaoItem>
          <PaginacaoLink href="#">2</PaginacaoLink>
        </PaginacaoItem>
        <PaginacaoItem>
          <PaginacaoReticencias />
        </PaginacaoItem>
        <PaginacaoItem>
          <PaginacaoProxima href="#" />
        </PaginacaoItem>
      </PaginacaoConteudo>
    </Paginacao>
  ),
};
