import type { Meta, StoryObj } from "@storybook/nextjs";

import { CapturaDeVideo } from "./captura-de-video";

/**
 * Estados presentacionais, dirigidos por `estado` fixo — nunca por captura
 * de câmera real dentro do Storybook (T10 do PCF F08). O estado "concedida"
 * (vídeo ao vivo) depende de uma `MediaStream` real e não tem uma história
 * própria por isso; os três estados de permissão abaixo cobrem toda a
 * variação presentacional deste componente.
 */
const meta = {
  title: "F8/RegistroWebcam/CapturaDeVideo",
  component: CapturaDeVideo,
  args: { stream: null },
} satisfies Meta<typeof CapturaDeVideo>;

export default meta;
type Story = StoryObj<typeof meta>;

export const AguardandoPermissao: Story = {
  args: { estado: "solicitando" },
};

export const PermissaoNegada: Story = {
  args: { estado: "negada", aoSolicitarNovamente: () => {} },
};

export const CameraIndisponivel: Story = {
  args: { estado: "indisponivel" },
};
