import { describe, expect, it } from "vitest";

import { DICIONARIO_DE_ERROS, mensagemDoErro } from "@/lib/seguranca/dicionario-de-erros";

/**
 * T13 do PCF F08. Critérios da seção "Pronto quando":
 *  1. Todo `codigo` citado na §3 do PCF tem entrada no dicionário (teste de
 *     cobertura, não promessa).
 *  2. Mensagem de código ausente cai no fallback (nunca quebra a tela).
 *  3. Para os códigos `expoe_regra: false`, a mensagem nunca cita o
 *     parâmetro interno (faixa CIDR, limiar de score, geocerca).
 */

/** Exatamente a lista de códigos exigida pela §3 do PCF F08 (o mesmo recorte
 *  fechado de leitura de `packages/contracts/errors.yaml` para esta fase). */
const CODIGOS_EXIGIDOS_PELA_FASE = [
  "PONTO-AUTH-001",
  "PONTO-AUTH-002",
  "PONTO-AUTH-003",
  "PONTO-AUTH-004",
  "PONTO-AUTH-006",
  "PONTO-AUTH-010",
  "PONTO-AUTH-011",
  "PONTO-AUTH-013",
  "PONTO-SCORE-001",
  "PONTO-SCORE-002",
  "PONTO-SCORE-003",
  "PONTO-SCORE-004",
  "PONTO-REDE-001",
  "PONTO-REDE-002",
  "PONTO-GEO-001",
  "PONTO-GEO-002",
  "PONTO-GEO-003",
  "PONTO-DISP-001",
  "PONTO-DISP-002",
  "PONTO-MARC-001",
  "PONTO-MARC-002",
  "PONTO-MARC-003",
  "PONTO-MARC-004",
  "PONTO-MARC-005",
  "PONTO-MARC-006",
  "PONTO-MARC-007",
  "PONTO-MARC-008",
  "PONTO-MARC-009",
  "PONTO-MARC-010",
  "PONTO-IDEM-001",
  "PONTO-IDEM-002",
  "PONTO-IDEM-003",
  "PONTO-VAL-001",
  "PONTO-VAL-005",
  "PONTO-VAL-006",
  "PONTO-VAL-007",
  "PONTO-VAL-009",
  "PONTO-VAL-010",
  "PONTO-VAL-011",
  "PONTO-PERM-001",
  "PONTO-PERM-002",
  "PONTO-PERM-004",
  "PONTO-PERM-005",
  "PONTO-TEN-001",
  "PONTO-TEN-002",
  "PONTO-TEN-003",
  "PONTO-TEN-004",
  "PONTO-RATE-001",
  "PONTO-CONF-001",
  "PONTO-REC-001",
  "PONTO-LGPD-001",
];

/** Códigos com `expoe_regra: false` no catálogo (`errors.yaml`) — a
 *  mensagem para eles nunca pode citar o parâmetro interno correspondente. */
const CODIGOS_QUE_NAO_EXPOEM_REGRA: Record<string, RegExp> = {
  "PONTO-AUTH-001": /usu[aá]rio n[aã]o existe|conta n[aã]o existe/i,
  "PONTO-REDE-001": /cidr|faixa de ip|\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}/i,
  "PONTO-GEO-001": /raio|coordenada|latitude|longitude/i,
  "PONTO-SCORE-001": /score|limiar/i,
  "PONTO-SCORE-002": /score|limiar/i,
  "PONTO-SCORE-003": /score|limiar|similaridade de \d/i,
  "PONTO-REC-001": /tabela|tenant|uuid/i,
  "PONTO-PERM-002": /hierarquia|escopo interno/i,
  "PONTO-TEN-002": /token|jwt/i,
  "PONTO-TEN-004": /row level security|rls|cross-tenant/i,
};

describe("DICIONARIO_DE_ERROS", () => {
  it.each(CODIGOS_EXIGIDOS_PELA_FASE)("tem entrada para %s", (codigo) => {
    expect(DICIONARIO_DE_ERROS[codigo]).toBeTruthy();
    expect(typeof DICIONARIO_DE_ERROS[codigo]).toBe("string");
  });

  it("cobre exatamente a lista exigida — nenhum código a menos", () => {
    const chavesFaltando = CODIGOS_EXIGIDOS_PELA_FASE.filter(
      (codigo) => !(codigo in DICIONARIO_DE_ERROS),
    );
    expect(chavesFaltando).toEqual([]);
  });

  it.each(Object.entries(CODIGOS_QUE_NAO_EXPOEM_REGRA))(
    "%s (expoe_regra: false) não cita o parâmetro interno na mensagem",
    (codigo, padraoProibido) => {
      const mensagem = DICIONARIO_DE_ERROS[codigo];
      expect(mensagem).toBeDefined();
      expect(mensagem ?? "").not.toMatch(padraoProibido);
    },
  );

  it("nunca usa os termos proibidos do glossário (marcação nunca é 'batida'/'editada'/'corrigida')", () => {
    const textoCompleto = Object.values(DICIONARIO_DE_ERROS).join(" ").toLowerCase();
    expect(textoCompleto).not.toMatch(/\bbatida\b/);
    expect(textoCompleto).not.toMatch(/editar marca[cç][aã]o|corrigir marca[cç][aã]o/);
    expect(textoCompleto).not.toMatch(/\bfuncion[aá]rio\b/);
  });
});

describe("mensagemDoErro", () => {
  it("devolve a mensagem do dicionário para um código conhecido", () => {
    expect(mensagemDoErro("PONTO-AUTH-011")).toBe(DICIONARIO_DE_ERROS["PONTO-AUTH-011"]);
  });

  it("nunca quebra para um código ausente do dicionário — devolve o fallback genérico", () => {
    const mensagem = mensagemDoErro("PONTO-CODIGO-INEXISTENTE-999");
    expect(mensagem).toBeTruthy();
    expect(typeof mensagem).toBe("string");
  });

  it("devolve o fallback genérico quando o código é ausente (undefined)", () => {
    expect(mensagemDoErro(undefined)).toBeTruthy();
  });
});
