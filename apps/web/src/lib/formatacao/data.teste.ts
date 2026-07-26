import { describe, expect, it } from "vitest";

import { formatarData, formatarDataHora, formatarDiaDaSemanaAbreviado, formatarHora } from "./data";

const FUSO_SAO_PAULO = "America/Sao_Paulo";
const FUSO_MANAUS = "America/Manaus";

describe("formatarData", () => {
  it("formata em pt-BR dd/mm/aaaa", () => {
    expect(formatarData("2026-07-25T14:05:00-03:00")).toBe("25/07/2026");
  });
});

describe("formatarHora", () => {
  it("formata em 24h, sem AM/PM", () => {
    expect(formatarHora("2026-07-25T14:05:00-03:00")).toBe("14:05");
  });

  it("respeita o fuso horario da unidade, nao o fuso local do processo", () => {
    // 23:30 em Manaus (UTC-4) e 00:30 do dia seguinte em Sao Paulo (UTC-3).
    const instante = "2026-07-25T23:30:00-04:00";
    expect(formatarHora(instante, FUSO_MANAUS)).toBe("23:30");
    expect(formatarHora(instante, FUSO_SAO_PAULO)).toBe("00:30");
  });

  it("cobre virada de meia-noite na formatacao de data quando o fuso muda o dia civil", () => {
    const instante = "2026-07-25T23:30:00-04:00";
    expect(formatarData(instante, FUSO_MANAUS)).toBe("25/07/2026");
    expect(formatarData(instante, FUSO_SAO_PAULO)).toBe("26/07/2026");
  });
});

describe("formatarDataHora", () => {
  it("combina data e hora", () => {
    expect(formatarDataHora("2026-07-25T14:05:00-03:00")).toBe("25/07/2026 14:05");
  });
});

describe("formatarDiaDaSemanaAbreviado", () => {
  it("devolve o rotulo curto sem pontuacao", () => {
    // 2026-07-25 e sabado.
    expect(formatarDiaDaSemanaAbreviado("2026-07-25T12:00:00-03:00")).toBe("sáb");
  });
});
