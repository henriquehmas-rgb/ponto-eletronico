import { describe, expect, it } from "vitest";

import {
  calcularDuracaoEmMinutos,
  duracaoTurnoMinutos,
  minutosParaDecimal,
  minutosParaHHMM,
} from "./tempo";

describe("minutosParaHHMM", () => {
  it("converte 90 minutos em 1:30 (arredondamento 90min -> 1:30)", () => {
    expect(minutosParaHHMM(90)).toBe("1:30");
  });

  it("preenche minutos com zero a esquerda", () => {
    expect(minutosParaHHMM(65)).toBe("1:05");
  });

  it("cobre duracao negativa com o sinal antes das horas", () => {
    expect(minutosParaHHMM(-90)).toBe("-1:30");
    expect(minutosParaHHMM(-5)).toBe("-0:05");
  });

  it("cobre duracao acima de 24h sem normalizar para hora do dia", () => {
    expect(minutosParaHHMM(1500)).toBe("25:00");
  });

  it("trata zero", () => {
    expect(minutosParaHHMM(0)).toBe("0:00");
  });

  it("rejeita valor nao finito", () => {
    expect(() => minutosParaHHMM(Number.NaN)).toThrow();
  });
});

describe("minutosParaDecimal", () => {
  it("converte 90 minutos em 1,50 (90min -> 1:30 -> 1,50)", () => {
    expect(minutosParaDecimal(90)).toBe("1,50");
  });

  it("arredonda para duas casas com virgula pt-BR", () => {
    expect(minutosParaDecimal(100)).toBe("1,67");
  });

  it("cobre duracao negativa", () => {
    expect(minutosParaDecimal(-90)).toBe("-1,50");
  });

  it("cobre duracao acima de 24h", () => {
    expect(minutosParaDecimal(1500)).toBe("25,00");
  });

  it("nao produz -0,00 para valores muito pequenos", () => {
    expect(minutosParaDecimal(-0.05)).toBe("0,00");
  });
});

describe("duracaoTurnoMinutos", () => {
  it("calcula turno dentro do mesmo dia", () => {
    expect(duracaoTurnoMinutos("07:00", "19:00")).toBe(720);
  });

  it("cobre virada de meia-noite (turno noturno 12x36)", () => {
    expect(duracaoTurnoMinutos("19:00", "07:00")).toBe(720);
  });

  it("cobre virada de meia-noite com faixa noturna padrao 22h-05h", () => {
    expect(duracaoTurnoMinutos("22:00", "06:00")).toBe(480);
  });

  it("trata inicio igual a fim como 24h corridas", () => {
    expect(duracaoTurnoMinutos("07:00", "07:00")).toBe(1440);
  });

  it("rejeita formato invalido", () => {
    expect(() => duracaoTurnoMinutos("25:00", "07:00")).toThrow();
    expect(() => duracaoTurnoMinutos("7:00", "07:00")).toThrow();
  });
});

describe("calcularDuracaoEmMinutos", () => {
  it("calcula diferenca simples", () => {
    const inicio = new Date("2026-07-25T08:00:00-03:00");
    const fim = new Date("2026-07-25T17:00:00-03:00");
    expect(calcularDuracaoEmMinutos(inicio, fim)).toBe(540);
  });

  it("cobre virada de meia-noite entre datas civis diferentes", () => {
    const inicio = new Date("2026-07-25T22:00:00-03:00");
    const fim = new Date("2026-07-26T06:00:00-03:00");
    expect(calcularDuracaoEmMinutos(inicio, fim)).toBe(480);
  });

  it("cobre duracao negativa quando fim precede inicio (inconsistencia, nao corrigida)", () => {
    const inicio = new Date("2026-07-25T17:00:00-03:00");
    const fim = new Date("2026-07-25T08:00:00-03:00");
    expect(calcularDuracaoEmMinutos(inicio, fim)).toBe(-540);
  });

  it("cobre duracao acima de 24h", () => {
    const inicio = new Date("2026-07-25T08:00:00-03:00");
    const fim = new Date("2026-07-27T10:00:00-03:00");
    expect(calcularDuracaoEmMinutos(inicio, fim)).toBe(2 * 24 * 60 + 120);
  });
});
