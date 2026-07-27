import { describe, expect, it } from "vitest";

import { validarRetornoSeguro } from "@/lib/sessao/retorno-seguro";

describe("validarRetornoSeguro (T1 — proteção contra open redirect)", () => {
  it("aceita um caminho relativo simples", () => {
    expect(validarRetornoSeguro("/painel")).toBe("/painel");
  });

  it("aceita um caminho relativo com sub-rota e query string", () => {
    expect(validarRetornoSeguro("/eu/extrato?periodo=mes-atual")).toBe(
      "/eu/extrato?periodo=mes-atual",
    );
  });

  it("rejeita URL protocol-relative (//evil.com)", () => {
    expect(validarRetornoSeguro("//evil.com")).toBeNull();
  });

  it("rejeita URL absoluta com esquema https", () => {
    expect(validarRetornoSeguro("https://evil.com")).toBeNull();
  });

  it("rejeita URL absoluta com esquema http", () => {
    expect(validarRetornoSeguro("http://evil.com/painel")).toBeNull();
  });

  it("rejeita esquema javascript", () => {
    expect(validarRetornoSeguro("javascript:alert(1)")).toBeNull();
  });

  it("rejeita caminho com barra invertida (variação de protocol-relative)", () => {
    expect(validarRetornoSeguro("/\\evil.com")).toBeNull();
  });

  it("rejeita string vazia", () => {
    expect(validarRetornoSeguro("")).toBeNull();
  });

  it("rejeita ausência de valor (null/undefined)", () => {
    expect(validarRetornoSeguro(null)).toBeNull();
    expect(validarRetornoSeguro(undefined)).toBeNull();
  });

  it("rejeita caminho que não começa com barra", () => {
    expect(validarRetornoSeguro("painel")).toBeNull();
  });
});
