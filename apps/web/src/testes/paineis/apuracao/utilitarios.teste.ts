import { describe, expect, it } from "vitest";

import {
  agruparApuracoesPorVinculo,
  hojeIso,
  mensagemDeErroApi,
  mesAnteriorComoPeriodo,
  mesAtualComoPeriodo,
  obterDiasDoIntervalo,
  paramsSemUndefined,
} from "@/componentes/paineis/apuracao/utilitarios";
import type { Esquema } from "@/lib/api";

describe("paramsSemUndefined (T9) — remove só as chaves undefined, preserva as obrigatórias", () => {
  it("remove chaves com valor undefined", () => {
    const resultado = paramsSemUndefined({ a: "1", b: undefined, c: 2 });
    expect(resultado).toEqual({ a: "1", c: 2 });
    expect("b" in resultado).toBe(false);
  });

  it("mantém valores falsy que não são undefined (0, false, string vazia)", () => {
    const resultado = paramsSemUndefined({ zero: 0, falso: false, vazio: "" });
    expect(resultado).toEqual({ zero: 0, falso: false, vazio: "" });
  });

  it("compila com um campo obrigatório (não-opcional) presente, sem exigir cast externo", () => {
    // Prova de tipo tanto quanto de valor — este é exatamente o padrão que
    // `useApuracoes` (de/ate obrigatórios) usa; se `paramsSemUndefined`
    // voltar a tornar tudo opcional, o `tsc` desta suíte falha primeiro.
    const resultado = paramsSemUndefined({
      de: "2026-07-01",
      ate: "2026-07-31",
      empresaId: undefined,
    });
    expect(resultado).toEqual({ de: "2026-07-01", ate: "2026-07-31" });
  });
});

describe("obterDiasDoIntervalo (T9)", () => {
  it("lista os dias inclusive nas duas pontas", () => {
    expect(obterDiasDoIntervalo("2026-07-01", "2026-07-03")).toEqual([
      "2026-07-01",
      "2026-07-02",
      "2026-07-03",
    ]);
  });

  it("um único dia (de === ate) devolve uma lista de um elemento", () => {
    expect(obterDiasDoIntervalo("2026-07-15", "2026-07-15")).toEqual(["2026-07-15"]);
  });

  it("mês de 31 dias devolve exatamente 31 datas", () => {
    expect(obterDiasDoIntervalo("2026-07-01", "2026-07-31")).toHaveLength(31);
  });

  it("atravessa a virada de mês corretamente", () => {
    expect(obterDiasDoIntervalo("2026-01-30", "2026-02-02")).toEqual([
      "2026-01-30",
      "2026-01-31",
      "2026-02-01",
      "2026-02-02",
    ]);
  });
});

describe("mesAtualComoPeriodo / mesAnteriorComoPeriodo / hojeIso (T9)", () => {
  it("mesAtualComoPeriodo devolve o primeiro e o último dia do mês informado", () => {
    expect(mesAtualComoPeriodo(new Date(2026, 6, 15))).toEqual({
      inicio: "2026-07-01",
      fim: "2026-07-31",
    });
  });

  it("mesAtualComoPeriodo lida com fevereiro bissexto", () => {
    expect(mesAtualComoPeriodo(new Date(2028, 1, 10))).toEqual({
      inicio: "2028-02-01",
      fim: "2028-02-29",
    });
  });

  it("mesAnteriorComoPeriodo volta um mês (com virada de ano)", () => {
    expect(mesAnteriorComoPeriodo(new Date(2026, 0, 10))).toEqual({
      inicio: "2025-12-01",
      fim: "2025-12-31",
    });
  });

  it("hojeIso usa componentes locais (não desloca por fuso)", () => {
    expect(hojeIso(new Date(2026, 6, 5, 0, 30))).toBe("2026-07-05");
  });
});

describe("agruparApuracoesPorVinculo (T9)", () => {
  const base: Esquema<"ApuracaoDia"> = {
    id: "a",
    vinculoId: "v1",
    colaboradorId: "c1",
    data: "2026-07-01",
  };

  it("agrupa várias apurações do mesmo vínculo em UMA linha, indexada por dia", () => {
    const linhas = agruparApuracoesPorVinculo([
      { ...base, data: "2026-07-01", status: "apurado" },
      { ...base, id: "b", data: "2026-07-02", status: "pendente" },
    ]);
    expect(linhas).toHaveLength(1);
    expect(linhas[0]?.vinculoId).toBe("v1");
    expect(linhas[0]?.porDia.size).toBe(2);
    expect(linhas[0]?.porDia.get("2026-07-01")?.status).toBe("apurado");
    expect(linhas[0]?.porDia.get("2026-07-02")?.status).toBe("pendente");
  });

  it("dois vínculos diferentes viram DUAS linhas (mesmo que do mesmo colaborador)", () => {
    const linhas = agruparApuracoesPorVinculo([
      { ...base, vinculoId: "v1" },
      { ...base, id: "b", vinculoId: "v2" },
    ]);
    expect(linhas).toHaveLength(2);
  });

  it("ignora entradas sem vinculoId (não quebra, só não gera linha)", () => {
    const { vinculoId: _vinculoId, ...semVinculo } = base;
    const linhas = agruparApuracoesPorVinculo([semVinculo]);
    expect(linhas).toHaveLength(0);
  });
});

describe("mensagemDeErroApi (T9)", () => {
  it("erro que não é da API devolve mensagem genérica", () => {
    expect(mensagemDeErroApi(new Error("qualquer coisa"))).toMatch(/não foi possível/i);
  });
});
