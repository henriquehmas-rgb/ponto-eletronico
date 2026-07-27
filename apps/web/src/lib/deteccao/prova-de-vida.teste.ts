import { describe, expect, it } from "vitest";

import {
  calcularAnguloDeGuinadaGraus,
  calcularEar,
  DESAFIOS_DISPONIVEIS,
  avaliarSequenciaDeQuadros,
  sortearDesafio,
} from "./prova-de-vida";
import type { MatrizDeTransformacao, PontoDeMarco, QuadroDeDeteccaoFacial } from "./tipos";

const TOTAL_DE_MARCOS = 478;

/**
 * Sequências SINTÉTICAS, fixadas neste arquivo — nunca capturadas de webcam
 * real (T7, "pronto quando"). Só os índices lidos por `calcularEar`
 * (MARCOS_OLHO_*, ver prova-de-vida.ts) importam; o resto é preenchido com
 * um ponto neutro qualquer.
 */
function landmarksComOlhos(estado: "aberto" | "fechado"): PontoDeMarco[] {
  const pontos: PontoDeMarco[] = Array.from({ length: TOTAL_DE_MARCOS }, () => ({ x: 0, y: 0 }));

  const metadeVertical = estado === "aberto" ? 0.02 : 0.005;
  function aplicarOlho(
    indices: readonly [number, number, number, number, number, number],
    deslocamentoX: number,
  ): void {
    const [externo, superior1, superior2, interno, inferior2, inferior1] = indices;
    pontos[externo] = { x: deslocamentoX, y: 0 };
    pontos[interno] = { x: deslocamentoX + 0.1, y: 0 };
    pontos[superior1] = { x: deslocamentoX + 0.03, y: -metadeVertical };
    pontos[inferior1] = { x: deslocamentoX + 0.03, y: metadeVertical };
    pontos[superior2] = { x: deslocamentoX + 0.07, y: -metadeVertical };
    pontos[inferior2] = { x: deslocamentoX + 0.07, y: metadeVertical };
  }
  aplicarOlho([33, 160, 158, 133, 153, 144], 0);
  aplicarOlho([362, 385, 387, 263, 373, 380], 0.5);

  return pontos;
}

function matrizComGuinada(graus: number): MatrizDeTransformacao {
  const radianos = (graus * Math.PI) / 180;
  const data: number[] = new Array(16).fill(0);
  data[8] = Math.sin(radianos);
  data[10] = Math.cos(radianos);
  data[15] = 1;
  return { rows: 4, columns: 4, data };
}

function quadro(
  timestampMs: number,
  opcoes: { olhos?: "aberto" | "fechado"; guinadaGraus?: number } = {},
): QuadroDeDeteccaoFacial {
  return {
    timestampMs,
    landmarks: opcoes.olhos ? landmarksComOlhos(opcoes.olhos) : null,
    matrizTransformacaoFacial:
      opcoes.guinadaGraus === undefined ? null : matrizComGuinada(opcoes.guinadaGraus),
  };
}

describe("calcularEar", () => {
  it("devolve um valor acima do limiar para olhos abertos", () => {
    expect(calcularEar(landmarksComOlhos("aberto"))).toBeGreaterThan(0.2);
  });

  it("devolve um valor abaixo do limiar para olhos fechados", () => {
    expect(calcularEar(landmarksComOlhos("fechado"))).toBeLessThan(0.2);
  });
});

describe("calcularAnguloDeGuinadaGraus", () => {
  it("devolve ~0 graus para a matriz neutra", () => {
    expect(calcularAnguloDeGuinadaGraus(matrizComGuinada(0))).toBeCloseTo(0, 5);
  });

  it("devolve um ângulo positivo para guinada para a direita", () => {
    expect(calcularAnguloDeGuinadaGraus(matrizComGuinada(20))).toBeCloseTo(20, 5);
  });

  it("devolve um ângulo negativo para guinada para a esquerda", () => {
    expect(calcularAnguloDeGuinadaGraus(matrizComGuinada(-20))).toBeCloseTo(-20, 5);
  });
});

describe("sortearDesafio", () => {
  it("mapeia geradores diferentes para desafios diferentes (não é sempre o mesmo)", () => {
    const resultado0 = sortearDesafio(() => 0);
    const resultado1 = sortearDesafio(() => 0.4);
    const resultado2 = sortearDesafio(() => 0.99);
    const distintos = new Set([resultado0, resultado1, resultado2]);
    expect(distintos.size).toBeGreaterThan(1);
    for (const resultado of [resultado0, resultado1, resultado2]) {
      expect(DESAFIOS_DISPONIVEIS).toContain(resultado);
    }
  });

  it("com Math.random real, produz mais de um desafio distinto em várias execuções", () => {
    const amostras = new Set(Array.from({ length: 40 }, () => sortearDesafio()));
    expect(amostras.size).toBeGreaterThan(1);
  });
});

describe("avaliarSequenciaDeQuadros — piscar_duas_vezes", () => {
  it("aprova duas piscadas dentro da janela", () => {
    const quadros = [
      quadro(0, { olhos: "aberto" }),
      quadro(100, { olhos: "aberto" }),
      quadro(200, { olhos: "fechado" }),
      quadro(300, { olhos: "fechado" }),
      quadro(400, { olhos: "aberto" }), // 1ª piscada contada aqui
      quadro(500, { olhos: "aberto" }),
      quadro(600, { olhos: "fechado" }),
      quadro(700, { olhos: "fechado" }),
      quadro(800, { olhos: "aberto" }), // 2ª piscada contada aqui
    ];
    const resultado = avaliarSequenciaDeQuadros("piscar_duas_vezes", quadros);
    expect(resultado.aprovado).toBe(true);
    expect(resultado.evidencia.piscadasDetectadas).toBe(2);
  });

  it("reprova por tempo esgotado quando só uma piscada ocorre até o fim da janela", () => {
    const quadros = [
      quadro(0, { olhos: "aberto" }),
      quadro(500, { olhos: "fechado" }),
      quadro(700, { olhos: "fechado" }),
      quadro(900, { olhos: "aberto" }), // 1ª piscada, nenhuma segunda depois
      quadro(2000, { olhos: "aberto" }),
      quadro(4000, { olhos: "aberto" }),
    ];
    const resultado = avaliarSequenciaDeQuadros("piscar_duas_vezes", quadros);
    expect(resultado.aprovado).toBe(false);
    expect(resultado.motivoReprovacao).toBe("tempo_esgotado");
  });

  it("reprova por movimento insuficiente quando os olhos nunca fecham na janela inteira", () => {
    const quadros = [
      quadro(0, { olhos: "aberto" }),
      quadro(1000, { olhos: "aberto" }),
      quadro(2000, { olhos: "aberto" }),
      quadro(3000, { olhos: "aberto" }),
      quadro(4000, { olhos: "aberto" }),
    ];
    const resultado = avaliarSequenciaDeQuadros("piscar_duas_vezes", quadros);
    expect(resultado.aprovado).toBe(false);
    expect(resultado.motivoReprovacao).toBe("movimento_insuficiente");
  });
});

describe("avaliarSequenciaDeQuadros — virar_direita", () => {
  it("aprova quando a guinada sustenta >=15° por >=3 quadros consecutivos", () => {
    const quadros = [
      quadro(0, { guinadaGraus: 0 }),
      quadro(100, { guinadaGraus: 0 }),
      quadro(200, { guinadaGraus: 20 }),
      quadro(300, { guinadaGraus: 20 }),
      quadro(400, { guinadaGraus: 20 }),
    ];
    const resultado = avaliarSequenciaDeQuadros("virar_direita", quadros);
    expect(resultado.aprovado).toBe(true);
  });

  it("reprova por tempo esgotado quando a guinada toca o limiar mas não sustenta", () => {
    const quadros = [
      quadro(0, { guinadaGraus: 0 }),
      quadro(1000, { guinadaGraus: 20 }),
      quadro(1100, { guinadaGraus: 20 }),
      quadro(1200, { guinadaGraus: 0 }),
      quadro(2500, { guinadaGraus: 0 }),
      quadro(4000, { guinadaGraus: 0 }),
    ];
    const resultado = avaliarSequenciaDeQuadros("virar_direita", quadros);
    expect(resultado.aprovado).toBe(false);
    expect(resultado.motivoReprovacao).toBe("tempo_esgotado");
  });

  it("reprova por movimento insuficiente quando a guinada nunca se aproxima do limiar", () => {
    const quadros = [
      quadro(0, { guinadaGraus: 0 }),
      quadro(1000, { guinadaGraus: 3 }),
      quadro(2000, { guinadaGraus: -2 }),
      quadro(3000, { guinadaGraus: 4 }),
      quadro(4000, { guinadaGraus: 0 }),
    ];
    const resultado = avaliarSequenciaDeQuadros("virar_direita", quadros);
    expect(resultado.aprovado).toBe(false);
    expect(resultado.motivoReprovacao).toBe("movimento_insuficiente");
  });
});

describe("avaliarSequenciaDeQuadros — virar_esquerda", () => {
  it("aprova quando a guinada sustenta <=-15° por >=3 quadros consecutivos", () => {
    const quadros = [
      quadro(0, { guinadaGraus: 0 }),
      quadro(100, { guinadaGraus: -20 }),
      quadro(200, { guinadaGraus: -20 }),
      quadro(300, { guinadaGraus: -20 }),
    ];
    const resultado = avaliarSequenciaDeQuadros("virar_esquerda", quadros);
    expect(resultado.aprovado).toBe(true);
  });

  it("não aprova guinada para o lado errado (virar_direita não satisfaz virar_esquerda)", () => {
    const quadros = [
      quadro(0, { guinadaGraus: 0 }),
      quadro(100, { guinadaGraus: 20 }),
      quadro(200, { guinadaGraus: 20 }),
      quadro(300, { guinadaGraus: 20 }),
      quadro(4000, { guinadaGraus: 20 }),
    ];
    const resultado = avaliarSequenciaDeQuadros("virar_esquerda", quadros);
    expect(resultado.aprovado).toBe(false);
  });
});

describe("avaliarSequenciaDeQuadros — sem quadros", () => {
  it("reprova por movimento insuficiente quando a sequência está vazia", () => {
    const resultado = avaliarSequenciaDeQuadros("piscar_duas_vezes", []);
    expect(resultado.aprovado).toBe(false);
    expect(resultado.motivoReprovacao).toBe("movimento_insuficiente");
    expect(resultado.evidencia.quadrosAnalisados).toBe(0);
  });
});
