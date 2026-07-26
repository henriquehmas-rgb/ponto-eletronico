import { useState } from "react";

import type { Meta, StoryObj } from "@storybook/nextjs";

import { SeletorDePeriodo, type AtalhoDePeriodo } from "./seletor-de-periodo";

const ATALHOS: AtalhoDePeriodo[] = [
  { id: "mes-corrente", rotulo: "Mês corrente", inicio: "2026-07-01", fim: "2026-07-31" },
  { id: "mes-anterior", rotulo: "Mês anterior", inicio: "2026-06-01", fim: "2026-06-30" },
  { id: "periodo-apuracao", rotulo: "Período de apuração", inicio: "2026-07-21", fim: "2026-08-20" },
];

function SeletorDePeriodoComEstado(props: { atalhos?: AtalhoDePeriodo[] }) {
  const [intervalo, setIntervalo] = useState<{ inicio: string | null; fim: string | null }>({
    inicio: null,
    fim: null,
  });
  return (
    <SeletorDePeriodo
      inicio={intervalo.inicio}
      fim={intervalo.fim}
      atalhos={props.atalhos ?? []}
      mesInicial={{ ano: 2026, mes: 7 }}
      aoSelecionarIntervalo={(inicio, fim) => {
        setIntervalo({ inicio, fim });
      }}
    />
  );
}

const meta: Meta<typeof SeletorDePeriodoComEstado> = {
  title: "Domínio/SeletorDePeriodo",
  component: SeletorDePeriodoComEstado,
  parameters: { layout: "padded" },
};

export default meta;
type Story = StoryObj<typeof SeletorDePeriodoComEstado>;

export const ComAtalhos: Story = {
  name: "Com atalhos de período",
  args: { atalhos: ATALHOS },
};

export const SemAtalhos: Story = {
  args: { atalhos: [] },
};
