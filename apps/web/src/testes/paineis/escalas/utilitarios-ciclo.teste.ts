import { describe, expect, it } from "vitest";

import {
  calcularPosicaoInicial,
  datasDoIntervalo,
  diasEntreIso,
  ehDataFutura,
  hojeIso,
  mapearTipoDia,
  mesAnteriorComoPeriodo,
  mesAtualComoPeriodo,
} from "@/componentes/paineis/escalas/utilitarios-ciclo";

describe("mapearTipoDia", () => {
  it("deixa o componente inferir 'trabalho' a partir do turno quando temTurno e verdadeiro", () => {
    expect(mapearTipoDia("util", true)).toBeUndefined();
    expect(mapearTipoDia("nao_apurado", true)).toBeUndefined();
    expect(mapearTipoDia("feriado", true)).toBeUndefined();
  });

  it("mapeia os 5 valores que GradeDeEscala conhece 1:1 quando nao ha turno", () => {
    expect(mapearTipoDia("dsr", false)).toBe("dsr");
    expect(mapearTipoDia("folga", false)).toBe("folga");
    expect(mapearTipoDia("feriado", false)).toBe("feriado");
    expect(mapearTipoDia("compensado", false)).toBe("compensado");
  });

  it("mapeia os valores fora do enum estreito de GradeDeEscala para 'folga'", () => {
    expect(mapearTipoDia("util", false)).toBe("folga");
    expect(mapearTipoDia("ponto_facultativo", false)).toBe("folga");
    expect(mapearTipoDia("afastamento", false)).toBe("folga");
    expect(mapearTipoDia("nao_apurado", false)).toBe("folga");
    expect(mapearTipoDia(undefined, false)).toBe("folga");
  });
});

describe("diasEntreIso", () => {
  it("calcula diferenca simples de dias corridos", () => {
    expect(diasEntreIso("2026-08-01", "2026-08-10")).toBe(9);
  });

  it("e negativo quando b precede a", () => {
    expect(diasEntreIso("2026-08-10", "2026-08-01")).toBe(-9);
  });

  it("e zero para a mesma data", () => {
    expect(diasEntreIso("2026-08-01", "2026-08-01")).toBe(0);
  });

  it("atravessa virada de mes e de ano sem erro de fuso (ancora em meio-dia UTC)", () => {
    expect(diasEntreIso("2026-12-30", "2027-01-02")).toBe(3);
  });
});

describe("datasDoIntervalo", () => {
  it("enumera as datas inclusive nas duas pontas", () => {
    expect(datasDoIntervalo("2026-08-01", "2026-08-03")).toEqual([
      "2026-08-01",
      "2026-08-02",
      "2026-08-03",
    ]);
  });

  it("cobre um unico dia quando inicio e fim coincidem", () => {
    expect(datasDoIntervalo("2026-08-01", "2026-08-01")).toEqual(["2026-08-01"]);
  });

  it("atravessa virada de mes", () => {
    expect(datasDoIntervalo("2026-08-30", "2026-09-01")).toEqual([
      "2026-08-30",
      "2026-08-31",
      "2026-09-01",
    ]);
  });
});

describe("ehDataFutura", () => {
  it("verdadeiro para data posterior a hoje", () => {
    expect(ehDataFutura("2026-08-02", "2026-08-01")).toBe(true);
  });

  it("falso para hoje e para o passado", () => {
    expect(ehDataFutura("2026-08-01", "2026-08-01")).toBe(false);
    expect(ehDataFutura("2026-07-31", "2026-08-01")).toBe(false);
  });
});

describe("calcularPosicaoInicial", () => {
  it("mantem a mesma posicao quando a nova vigencia cai na mesma data de origem", () => {
    expect(calcularPosicaoInicial("2026-08-01", 1, "2026-08-01", 2)).toBe(1);
  });

  it("avanca a posicao no ciclo 12x36 (2 posicoes) um dia a frente", () => {
    // Origem na posicao 1 (trabalho); um dia depois cai na posicao 2 (folga).
    expect(calcularPosicaoInicial("2026-08-01", 1, "2026-08-02", 2)).toBe(2);
    // Dois dias depois volta a posicao 1 (o ciclo girou uma volta inteira).
    expect(calcularPosicaoInicial("2026-08-01", 1, "2026-08-03", 2)).toBe(1);
  });

  it("funciona com vigencia de destino ANTERIOR a origem (deslocamento negativo)", () => {
    expect(calcularPosicaoInicial("2026-08-10", 1, "2026-08-09", 2)).toBe(2);
  });

  it("cobre ciclo de 7 posicoes (6x1) preservando a fase do vinculo de referencia", () => {
    // Referencia estava na posicao 3 (DSR) num sabado; 7 dias depois (mesmo
    // dia da semana) volta a posicao 3.
    expect(calcularPosicaoInicial("2026-08-01", 3, "2026-08-08", 7)).toBe(3);
    // 3 dias depois avanca 3 posicoes: 3 -> 4 -> 5 -> 6.
    expect(calcularPosicaoInicial("2026-08-01", 3, "2026-08-04", 7)).toBe(6);
  });

  it("rejeita diasCiclo menor que 1", () => {
    expect(() => calcularPosicaoInicial("2026-08-01", 1, "2026-08-02", 0)).toThrow();
  });
});

describe("hojeIso", () => {
  it("usa componentes locais, nunca UTC (ex.: 23h59 local nao deve virar o dia seguinte)", () => {
    const referencia = new Date(2026, 6, 25, 23, 59, 0); // 25/jul/2026 local, mes 0-indexado
    expect(hojeIso(referencia)).toBe("2026-07-25");
  });

  it("preenche mes e dia com zero a esquerda", () => {
    const referencia = new Date(2026, 0, 5, 10, 0, 0); // 05/jan/2026
    expect(hojeIso(referencia)).toBe("2026-01-05");
  });
});

describe("mesAtualComoPeriodo", () => {
  it("cobre do primeiro ao ultimo dia do mes (31 dias)", () => {
    const referencia = new Date(2026, 6, 15); // julho/2026 (31 dias)
    expect(mesAtualComoPeriodo(referencia)).toEqual({ inicio: "2026-07-01", fim: "2026-07-31" });
  });

  it("cobre fevereiro em ano bissexto (29 dias)", () => {
    const referencia = new Date(2028, 1, 10); // fevereiro/2028, bissexto
    expect(mesAtualComoPeriodo(referencia)).toEqual({ inicio: "2028-02-01", fim: "2028-02-29" });
  });

  it("cobre fevereiro em ano nao bissexto (28 dias)", () => {
    const referencia = new Date(2026, 1, 10); // fevereiro/2026
    expect(mesAtualComoPeriodo(referencia)).toEqual({ inicio: "2026-02-01", fim: "2026-02-28" });
  });
});

describe("mesAnteriorComoPeriodo", () => {
  it("volta um mes dentro do mesmo ano", () => {
    const referencia = new Date(2026, 7, 15); // agosto/2026
    expect(mesAnteriorComoPeriodo(referencia)).toEqual({ inicio: "2026-07-01", fim: "2026-07-31" });
  });

  it("atravessa virada de ano (janeiro -> dezembro do ano anterior)", () => {
    const referencia = new Date(2026, 0, 15); // janeiro/2026
    expect(mesAnteriorComoPeriodo(referencia)).toEqual({ inicio: "2025-12-01", fim: "2025-12-31" });
  });
});
