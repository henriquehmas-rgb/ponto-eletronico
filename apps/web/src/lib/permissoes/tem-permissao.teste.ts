import { describe, expect, it } from "vitest";

import { temAlgumaPermissao, temPermissao } from "./tem-permissao";

describe("temPermissao (T1 — RBAC no cliente)", () => {
  it("verdadeiro quando a permissão exata está presente", () => {
    expect(
      temPermissao({ permissoes: ["empresas.ler", "empresas.editar"] }, "empresas.editar"),
    ).toBe(true);
  });

  it("falso quando a permissão está ausente", () => {
    expect(temPermissao({ permissoes: ["empresas.ler"] }, "empresas.excluir")).toBe(false);
  });

  it("falso quando a sessão ainda não carregou (undefined)", () => {
    expect(temPermissao(undefined, "empresas.ler")).toBe(false);
  });

  it("falso quando a sessão é null", () => {
    expect(temPermissao(null, "empresas.ler")).toBe(false);
  });

  it("falso quando `permissoes` está ausente da sessão", () => {
    expect(temPermissao({}, "empresas.ler")).toBe(false);
  });

  it("não confunde prefixo: 'empresas.ler' não satisfaz 'empresas.ler_sensivel'", () => {
    expect(temPermissao({ permissoes: ["empresas.ler"] }, "empresas.ler_sensivel")).toBe(false);
  });
});

describe("temAlgumaPermissao (OR de permissões)", () => {
  it("verdadeiro se qualquer uma das permissões está presente", () => {
    expect(
      temAlgumaPermissao({ permissoes: ["ocorrencias.ler"] }, ["apuracoes.ler", "ocorrencias.ler"]),
    ).toBe(true);
  });

  it("falso se nenhuma das permissões está presente", () => {
    expect(
      temAlgumaPermissao({ permissoes: ["colaboradores.ler"] }, [
        "apuracoes.ler",
        "ocorrencias.ler",
      ]),
    ).toBe(false);
  });

  it("falso para lista vazia de permissões exigidas", () => {
    expect(temAlgumaPermissao({ permissoes: ["colaboradores.ler"] }, [])).toBe(false);
  });
});
