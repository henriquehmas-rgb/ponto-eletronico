import type { Meta, StoryObj } from "@storybook/nextjs";

import { Avatar, AvatarContingencia, AvatarGrupo, AvatarImagem } from "./avatar";

const meta = {
  title: "Primitivos/Avatar",
  component: Avatar,
} satisfies Meta<typeof Avatar>;

export default meta;
type Story = StoryObj<typeof meta>;

export const ComContingencia: Story = {
  render: () => (
    <Avatar>
      <AvatarImagem src="" alt="" />
      <AvatarContingencia>MS</AvatarContingencia>
    </Avatar>
  ),
};

export const Tamanhos: Story = {
  render: () => (
    <div className="flex items-center gap-3">
      <Avatar size="pequeno">
        <AvatarContingencia>MS</AvatarContingencia>
      </Avatar>
      <Avatar size="padrao">
        <AvatarContingencia>MS</AvatarContingencia>
      </Avatar>
      <Avatar size="grande">
        <AvatarContingencia>MS</AvatarContingencia>
      </Avatar>
    </div>
  ),
};

export const Grupo: Story = {
  render: () => (
    <AvatarGrupo>
      <Avatar>
        <AvatarContingencia>MS</AvatarContingencia>
      </Avatar>
      <Avatar>
        <AvatarContingencia>JP</AvatarContingencia>
      </Avatar>
      <Avatar>
        <AvatarContingencia>+8</AvatarContingencia>
      </Avatar>
    </AvatarGrupo>
  ),
};
