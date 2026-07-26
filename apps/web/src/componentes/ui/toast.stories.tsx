import type { Meta, StoryObj } from "@storybook/nextjs";

import {
  Notificacao,
  NotificacaoAcao,
  NotificacaoDescricao,
  NotificacaoFechar,
  NotificacaoProvedor,
  NotificacaoTitulo,
  NotificacaoViewport,
  type VarianteDeNotificacao,
} from "./toast";

/**
 * `Notificacao` precisa ser filho direto de `NotificacaoViewport` (que
 * renderiza um `<ol>` — Radix Toast exige que cada notificacao seja um
 * `<li>` dentro dele, nao um portal automatico para um elemento irmao).
 */
const meta = {
  title: "Primitivos/Notificacao",
  component: Notificacao,
  decorators: [(Story) => <NotificacaoProvedor><Story /></NotificacaoProvedor>],
} satisfies Meta<typeof Notificacao>;

export default meta;
type Story = StoryObj<typeof meta>;

function notificacaoAberta(variante: VarianteDeNotificacao, titulo: string, descricao: string): Story {
  return {
    render: () => (
      <NotificacaoViewport className="static flex w-full max-w-sm flex-col p-0">
        <Notificacao variante={variante} open>
          <NotificacaoTitulo>{titulo}</NotificacaoTitulo>
          <NotificacaoDescricao>{descricao}</NotificacaoDescricao>
          <NotificacaoAcao altText="desfazer">Desfazer</NotificacaoAcao>
          <NotificacaoFechar />
        </Notificacao>
      </NotificacaoViewport>
    ),
  };
}

export const Sucesso: Story = notificacaoAberta(
  "sucesso",
  "Marcacao registrada",
  "NSR 48219 gravado com sucesso as 08:02.",
);

export const Atencao: Story = notificacaoAberta(
  "atencao",
  "Fora da geocerca",
  "O registro foi aceito, mas fora do perimetro configurado da unidade.",
);

export const Erro: Story = notificacaoAberta(
  "erro",
  "Falha ao enviar",
  "Nao foi possivel confirmar o registro — ele permanece na fila offline.",
);

export const Info: Story = notificacaoAberta(
  "info",
  "Sincronizando",
  "3 marcacoes da fila offline estao sendo enviadas.",
);
