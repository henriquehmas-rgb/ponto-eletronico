import { describe, expect, it } from "vitest";

import { mascararCnpj, mascararCpf, mascararPis } from "./documentos";

describe("mascararCpf", () => {
  it("mostra os 3 primeiros e os 2 ultimos digitos", () => {
    expect(mascararCpf("12345678901")).toBe("123.•••.•••-01");
  });

  it("aceita entrada ja formatada", () => {
    expect(mascararCpf("123.456.789-01")).toBe("123.•••.•••-01");
  });

  it("rejeita quantidade errada de digitos", () => {
    expect(() => mascararCpf("123")).toThrow();
  });
});

describe("mascararCnpj", () => {
  it("mostra os 2 primeiros e os 2 ultimos digitos", () => {
    expect(mascararCnpj("12345678000199")).toBe("12.•••.•••/••••-99");
  });

  it("aceita entrada ja formatada", () => {
    expect(mascararCnpj("12.345.678/0001-99")).toBe("12.•••.•••/••••-99");
  });
});

describe("mascararPis", () => {
  it("mostra os 3 primeiros e o digito verificador", () => {
    expect(mascararPis("12345678901")).toBe("123.•••••.••-1");
  });
});
