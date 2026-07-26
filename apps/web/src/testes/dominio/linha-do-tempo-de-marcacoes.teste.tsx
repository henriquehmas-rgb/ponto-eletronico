import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  LinhaDoTempoDeMarcacoes,
  type MarcacaoDaLinhaDoTempo,
} from "@/componentes/dominio/linha-do-tempo-de-marcacoes";

const MARCACAO_BASE: MarcacaoDaLinhaDoTempo = {
  id: "m1",
  datahoraMarcacao: "2026-07-25T08:00:00-03:00",
  canal: "mobile",
  nsr: 1001,
  scoreConfianca: 96,
  classificacaoConfianca: "alta",
};

describe("LinhaDoTempoDeMarcacoes", () => {
  it("mostra mensagem quando o dia esta vazio", () => {
    render(<LinhaDoTempoDeMarcacoes marcacoes={[]} />);
    expect(screen.getByText("Nenhuma marcação neste período.")).toBeInTheDocument();
  });

  it("renderiza uma quantidade impar de marcacoes sem inferir entrada/saida", () => {
    const marcacoes: MarcacaoDaLinhaDoTempo[] = [
      { ...MARCACAO_BASE, id: "m1", datahoraMarcacao: "2026-07-25T08:00:00-03:00", nsr: 1001 },
      {
        ...MARCACAO_BASE,
        id: "m2",
        datahoraMarcacao: "2026-07-25T12:00:00-03:00",
        nsr: 1002,
        canal: "terminal",
      },
      {
        ...MARCACAO_BASE,
        id: "m3",
        datahoraMarcacao: "2026-07-25T13:00:00-03:00",
        nsr: 1003,
        canal: "terminal",
      },
    ];
    render(<LinhaDoTempoDeMarcacoes marcacoes={marcacoes} />);

    const itens = screen.getAllByRole("listitem");
    expect(itens).toHaveLength(3);
    // Nenhum rotulo de "entrada"/"saida" deduzido: nenhuma marcacao trouxe sentidoInformado.
    expect(screen.queryByText(/entrada informada/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/saída informada/i)).not.toBeInTheDocument();
  });

  it("mostra sentido apenas quando o coletor informou explicitamente", () => {
    const marcacoes: MarcacaoDaLinhaDoTempo[] = [
      { ...MARCACAO_BASE, sentidoInformado: "entrada" },
    ];
    render(<LinhaDoTempoDeMarcacoes marcacoes={marcacoes} />);
    expect(screen.getByText("Entrada informada")).toBeInTheDocument();
  });

  it("sinaliza marcacao suspeita com texto, nao so com cor", () => {
    const marcacoes: MarcacaoDaLinhaDoTempo[] = [{ ...MARCACAO_BASE, estado: "suspeita" }];
    render(<LinhaDoTempoDeMarcacoes marcacoes={marcacoes} />);
    expect(screen.getByText("Suspeita")).toBeInTheDocument();
  });

  it("sinaliza marcacao pendente de envio offline", () => {
    // Sem `nsr`: uma marcacao na fila offline ainda nao foi confirmada pelo REP-P.
    const { nsr: _nsr, ...semNsr } = MARCACAO_BASE;
    const marcacoes: MarcacaoDaLinhaDoTempo[] = [{ ...semNsr, estado: "pendenteEnvioOffline" }];
    render(<LinhaDoTempoDeMarcacoes marcacoes={marcacoes} />);
    expect(screen.getByText("Pendente de envio (offline)")).toBeInTheDocument();
    // Sem NSR: ainda nao confirmada pelo REP-P.
    expect(screen.queryByText(/NSR/)).not.toBeInTheDocument();
  });

  it("formata a hora no fuso horario informado", () => {
    render(
      <LinhaDoTempoDeMarcacoes
        marcacoes={[{ ...MARCACAO_BASE, datahoraMarcacao: "2026-07-25T23:30:00-04:00" }]}
        fusoHorario="America/Sao_Paulo"
      />,
    );
    expect(screen.getByText("00:30")).toBeInTheDocument();
  });
});
