import type { Meta, StoryObj } from "@storybook/nextjs";

import { ConfirmacaoDeRegistro } from "./confirmacao-de-registro";

const meta = {
  title: "F8/RegistroWebcam/ConfirmacaoDeRegistro",
  component: ConfirmacaoDeRegistro,
} satisfies Meta<typeof ConfirmacaoDeRegistro>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Sucesso: Story = {
  args: {
    variante: "sucesso",
    numeroDoComprovante: "2026072500001842",
    nsr: 1842,
    horario: "08:02",
  },
};

export const SucessoComRevisao: Story = {
  args: {
    variante: "sucesso_com_revisao",
    numeroDoComprovante: "2026072500001843",
    nsr: 1843,
    horario: "08:05",
  },
};

/** Mesmo texto de `PONTO-SCORE-004` (T8) — o catálogo marca este código como `expoe_regra: true`. */
export const CameraVirtualDetectada: Story = {
  args: {
    variante: "recusado",
    mensagem:
      "Câmera virtual detectada. Encerre o software de câmera virtual e repita usando sua webcam física.",
  },
};

export const ErroDeRede: Story = {
  args: {
    variante: "recusado",
    mensagem:
      "Não foi possível concluir o registro agora. Verifique sua conexão e tente novamente.",
  },
};
