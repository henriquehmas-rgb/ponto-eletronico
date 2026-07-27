import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { CelulaDeApuracao } from "@/componentes/paineis/apuracao/celula-de-apuracao";
import type { Esquema } from "@/lib/api";

/**
 * Prova de T9 (PCF §6): a célula da grade é colorida E ROTULADA — nunca só
 * cor (WCAG 1.4.1). Cada estado carrega um marcador de forma (texto,
 * `aria-hidden`) e um rótulo acessível completo (`aria-label`), nunca
 * dependendo só da classe de cor para transmitir sentido.
 */
describe("CelulaDeApuracao (T9) — cor nunca é o único portador de informação", () => {
  function apuracao(sobrescritas: Partial<Esquema<"ApuracaoDia">> = {}): Esquema<"ApuracaoDia"> {
    return {
      id: "ap-1",
      vinculoId: "v-1",
      colaboradorId: "c-1",
      data: "2026-07-20",
      tipoDia: "util",
      status: "apurado",
      previstoMinutos: 480,
      trabalhadoMinutos: 480,
      marcacoesImpares: false,
      ...sobrescritas,
    };
  }

  it("dia apurado normal: mostra marcador de tipo de dia E rótulo acessível com tipo + status", () => {
    render(
      <CelulaDeApuracao
        data="2026-07-20"
        apuracao={apuracao()}
        temOcorrenciaAberta={false}
        onClick={vi.fn()}
      />,
    );
    const botao = screen.getByRole("button");
    expect(botao.getAttribute("aria-label")).toMatch(/Dia útil/i);
    expect(botao.getAttribute("aria-label")).toMatch(/Apurado/i);
  });

  it("dia com ocorrência aberta: rótulo acessível menciona a ocorrência, não só muda a cor", () => {
    render(
      <CelulaDeApuracao
        data="2026-07-20"
        apuracao={apuracao({ status: "com_ocorrencia" })}
        temOcorrenciaAberta
        onClick={vi.fn()}
      />,
    );
    const botao = screen.getByRole("button");
    expect(botao.getAttribute("aria-label")).toMatch(/ocorrência aberta/i);
    // O ícone de atenção aparece como texto visível (não é decoração pura de cor).
    expect(botao.textContent).toContain("⚠");
  });

  it("marcações ímpares: rótulo acessível avisa explicitamente, além da cor de status", () => {
    render(
      <CelulaDeApuracao
        data="2026-07-20"
        apuracao={apuracao({ marcacoesImpares: true })}
        temOcorrenciaAberta={false}
        onClick={vi.fn()}
      />,
    );
    expect(screen.getByRole("button").getAttribute("aria-label")).toMatch(/marcações ímpares/i);
  });

  it("dia sem apuração (sem registro): continua clicável e com rótulo honesto, nunca um status inventado", () => {
    render(
      <CelulaDeApuracao
        data="2026-07-20"
        apuracao={undefined}
        temOcorrenciaAberta={false}
        onClick={vi.fn()}
      />,
    );
    const botao = screen.getByRole("button");
    expect(botao.getAttribute("aria-label")).toMatch(/sem apuração/i);
  });

  it("dispara onClick ao ser ativada (mouse ou teclado, nativo de <button>)", async () => {
    const aoClicar = vi.fn();
    render(
      <CelulaDeApuracao
        data="2026-07-20"
        apuracao={apuracao()}
        temOcorrenciaAberta={false}
        onClick={aoClicar}
      />,
    );
    screen.getByRole("button").click();
    expect(aoClicar).toHaveBeenCalledTimes(1);
  });

  it("tipos de dia diferentes têm marcadores de FORMA diferentes (não só cor)", () => {
    const { rerender } = render(
      <CelulaDeApuracao
        data="2026-07-20"
        apuracao={apuracao({ tipoDia: "util" })}
        temOcorrenciaAberta={false}
        onClick={vi.fn()}
      />,
    );
    const marcadorUtil = screen.getByRole("button").textContent;

    rerender(
      <CelulaDeApuracao
        data="2026-07-20"
        apuracao={apuracao({ tipoDia: "feriado" })}
        temOcorrenciaAberta={false}
        onClick={vi.fn()}
      />,
    );
    const marcadorFeriado = screen.getByRole("button").textContent;

    expect(marcadorUtil).not.toEqual(marcadorFeriado);
  });
});
