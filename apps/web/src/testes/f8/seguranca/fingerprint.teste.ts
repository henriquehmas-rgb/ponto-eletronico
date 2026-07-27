import { readFileSync } from "node:fs";
import { join } from "node:path";

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  calcularFingerprint,
  CHAVE_FINGERPRINT_NO_ARMAZENAMENTO,
} from "@/lib/seguranca/fingerprint";

/**
 * T11 do PCF F08 — critérios da seção "Pronto quando":
 *  1. Duas chamadas seguidas no mesmo ambiente devolvem o mesmo valor
 *     (estabilidade via `localStorage`, não recalculado a cada chamada).
 *  2. O valor muda quando um dos insumos muda (fuso horário simulado
 *     diferente, neste teste).
 *  3. Nenhuma biblioteca de fingerprinting de terceiros foi adicionada ao
 *     `package.json`.
 */

beforeEach(() => {
  window.localStorage.clear();
});

afterEach(() => {
  vi.restoreAllMocks();
  window.localStorage.clear();
});

describe("calcularFingerprint", () => {
  it("devolve o mesmo valor em duas chamadas seguidas (estabilidade via localStorage)", async () => {
    const primeiro = await calcularFingerprint();
    const segundo = await calcularFingerprint();

    expect(segundo).toBe(primeiro);
    expect(window.localStorage.getItem(CHAVE_FINGERPRINT_NO_ARMAZENAMENTO)).toBe(primeiro);
  });

  it("não recalcula o hash na segunda chamada — só lê o valor persistido", async () => {
    await calcularFingerprint();
    const espiaoDigest = vi.spyOn(crypto.subtle, "digest");

    await calcularFingerprint();

    expect(espiaoDigest).not.toHaveBeenCalled();
  });

  it("devolve um valor hexadecimal de 64 caracteres (SHA-256)", async () => {
    const fingerprint = await calcularFingerprint();
    expect(fingerprint).toMatch(/^[0-9a-f]{64}$/);
  });

  it("muda quando um dos insumos muda (fuso horário simulado diferente)", async () => {
    const comFusoOriginal = await calcularFingerprint();
    window.localStorage.clear();

    // O código só usa `Intl.DateTimeFormat().resolvedOptions().timeZone` —
    // simular só esse retorno é suficiente para variar o insumo.
    vi.spyOn(Intl, "DateTimeFormat").mockImplementation(
      () =>
        ({
          resolvedOptions: () => ({ timeZone: "America/Noronha" }),
        }) as unknown as Intl.DateTimeFormat,
    );

    const comFusoDiferente = await calcularFingerprint();

    expect(comFusoDiferente).not.toBe(comFusoOriginal);
  });

  it("nenhuma biblioteca de fingerprinting de terceiros foi adicionada ao package.json", () => {
    const caminho = join(import.meta.dirname, "../../../../package.json");
    const pacote = JSON.parse(readFileSync(caminho, "utf8")) as {
      dependencies?: Record<string, string>;
      devDependencies?: Record<string, string>;
    };
    const todasAsDependencias = {
      ...(pacote.dependencies ?? {}),
      ...(pacote.devDependencies ?? {}),
    };
    const nomesProibidos = [
      "fingerprintjs",
      "@fingerprintjs/fingerprintjs",
      "clientjs",
      "fingerprintjs2",
    ];
    for (const nome of nomesProibidos) {
      expect(todasAsDependencias[nome]).toBeUndefined();
    }
  });
});
