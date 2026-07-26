import type { Meta, StoryObj } from "@storybook/nextjs";

import { Esqueleto } from "./skeleton";

const meta = {
  title: "Primitivos/Esqueleto",
  component: Esqueleto,
} satisfies Meta<typeof Esqueleto>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Padrao: Story = {
  render: () => (
    <div className="flex items-center gap-3">
      <Esqueleto className="size-10 rounded-pleno" />
      <div className="grid gap-2">
        <Esqueleto className="h-4 w-40" />
        <Esqueleto className="h-3 w-24" />
      </div>
    </div>
  ),
};
