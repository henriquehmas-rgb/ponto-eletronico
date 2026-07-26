import { describe, expect, it } from "vitest";

import { formatarSaldo, sinalDoSaldo } from "./saldo";

describe("sinalDoSaldo", () => {
  it("classifica saldo positivo como credor", () => {
    expect(sinalDoSaldo(120)).toBe("credor");
  });

  it("classifica saldo negativo como devedor", () => {
    expect(sinalDoSaldo(-120)).toBe("devedor");
  });

  it("classifica zero como neutro", () => {
    expect(sinalDoSaldo(0)).toBe("neutro");
  });
});

describe("formatarSaldo", () => {
  it("formata saldo credor com sinal de mais", () => {
    expect(formatarSaldo(90)).toEqual({
      sinal: "credor",
      textoHHMM: "1:30",
      textoDecimal: "1,50",
      textoComSinal: "+1:30",
    });
  });

  it("formata saldo devedor com sinal de menos", () => {
    expect(formatarSaldo(-90)).toEqual({
      sinal: "devedor",
      textoHHMM: "1:30",
      textoDecimal: "1,50",
      textoComSinal: "-1:30",
    });
  });

  it("formata saldo neutro sem sinal", () => {
    expect(formatarSaldo(0)).toEqual({
      sinal: "neutro",
      textoHHMM: "0:00",
      textoDecimal: "0,00",
      textoComSinal: "0:00",
    });
  });
});
