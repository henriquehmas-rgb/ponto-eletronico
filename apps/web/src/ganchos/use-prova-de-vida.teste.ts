import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { JANELA_DO_DESAFIO_MS, MAXIMO_DE_TENTATIVAS } from "@/lib/deteccao/prova-de-vida";
import type { QuadroDeDeteccaoFacial } from "@/lib/deteccao/tipos";

import { useProvaDeVida, type DetectorFacial } from "./use-prova-de-vida";

/**
 * O agendador de quadros é injetado como uma FILA síncrona controlada pelo
 * teste (nunca `requestAnimationFrame` real): cada chamada a
 * `processarProximoQuadro()` roda exatamente um quadro do laço de detecção,
 * com tempo simulado por `avancarRelogio(ms)`. Isto torna o teste
 * determinístico e rápido, sem esperar os 4 s reais da janela do desafio.
 */
function criarAgendadorControlado() {
  let pendente: (() => void) | null = null;
  return {
    agendarProximoQuadro: (callback: () => void): number => {
      pendente = callback;
      return 1;
    },
    cancelarQuadroAgendado: (): void => {
      pendente = null;
    },
    processarProximoQuadro: (): void => {
      const callback = pendente;
      pendente = null;
      callback?.();
    },
    hasPendente: (): boolean => pendente !== null,
  };
}

function relogioControlado(inicioMs = 0) {
  let agora = inicioMs;
  return {
    agora: () => agora,
    avancar: (ms: number) => {
      agora += ms;
    },
  };
}

/** Detector falso: devolve, quadro a quadro, os itens de uma fila fixada pelo teste. */
function detectorFalso(
  quadros: Array<Pick<QuadroDeDeteccaoFacial, "landmarks" | "matrizTransformacaoFacial">>,
): DetectorFacial & { liberar: ReturnType<typeof vi.fn> } {
  let indice = 0;
  const liberar = vi.fn();
  return {
    detectarQuadro: () => {
      const quadro = quadros[Math.min(indice, quadros.length - 1)];
      indice += 1;
      return quadro ?? { landmarks: null, matrizTransformacaoFacial: null };
    },
    liberar,
  };
}

const QUADRO_NEUTRO = { landmarks: null, matrizTransformacaoFacial: null };

describe("useProvaDeVida", () => {
  it("começa em 'carregando_modelo' e passa para 'em_andamento' após o detector carregar", async () => {
    const relogio = relogioControlado();
    const agendador = criarAgendadorControlado();
    const detector = detectorFalso([QUADRO_NEUTRO]);
    // Criado UMA vez, fora do corpo do hook: se recriado a cada render, a
    // dependência `video` do efeito mudaria de referência a cada render e o
    // laço de detecção reiniciaria sem parar.
    const video = document.createElement("video");

    const { result } = renderHook(() =>
      useProvaDeVida(video, true, {
        criarDetector: () => Promise.resolve(detector),
        gerarAleatorio: () => 0, // sempre "piscar_duas_vezes"
        agora: relogio.agora,
        agendarProximoQuadro: agendador.agendarProximoQuadro,
        cancelarQuadroAgendado: agendador.cancelarQuadroAgendado,
      }),
    );

    expect(result.current.situacao).toBe("carregando_modelo");

    await waitFor(() => expect(result.current.situacao).toBe("em_andamento"));
    expect(result.current.desafio).toBe("piscar_duas_vezes");
    expect(result.current.tentativa).toBe(1);
  });

  it("aprova quando os quadros satisfazem o desafio sorteado", async () => {
    const relogio = relogioControlado();
    const agendador = criarAgendadorControlado();

    // Geometria de olho igual à do teste do módulo puro (prova-de-vida.teste.ts):
    // [externo, superior1, superior2, interno, inferior2, inferior1].
    function landmarksComEstadoDosOlhos(
      estado: "aberto" | "fechado",
    ): QuadroDeDeteccaoFacial["landmarks"] {
      const pontos = Array.from({ length: 478 }, () => ({ x: 0, y: 0 }));
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

    const sequenciaDeDoisPiscares = (
      [
        "aberto",
        "aberto",
        "fechado",
        "fechado",
        "aberto",
        "aberto",
        "fechado",
        "fechado",
        "aberto",
      ] as const
    ).map((estado) => ({
      landmarks: landmarksComEstadoDosOlhos(estado),
      matrizTransformacaoFacial: null,
    }));

    const detector = detectorFalso(sequenciaDeDoisPiscares);
    const video = document.createElement("video");

    const { result } = renderHook(() =>
      useProvaDeVida(video, true, {
        criarDetector: () => Promise.resolve(detector),
        gerarAleatorio: () => 0,
        agora: relogio.agora,
        agendarProximoQuadro: agendador.agendarProximoQuadro,
        cancelarQuadroAgendado: agendador.cancelarQuadroAgendado,
      }),
    );

    await waitFor(() => expect(result.current.situacao).toBe("em_andamento"));

    for (let i = 0; i < sequenciaDeDoisPiscares.length; i++) {
      act(() => {
        relogio.avancar(100);
        agendador.processarProximoQuadro();
      });
    }

    await waitFor(() => expect(result.current.situacao).toBe("aprovado"));
    expect(result.current.resultado?.aprovado).toBe(true);
  });

  it("reprova a tentativa por tempo esgotado e tenta de novo até o máximo, depois reprova em definitivo", async () => {
    const relogio = relogioControlado();
    const agendador = criarAgendadorControlado();
    // Nunca fecha os olhos: nenhuma piscada em nenhuma tentativa.
    const detector = detectorFalso([QUADRO_NEUTRO]);
    const video = document.createElement("video");

    const { result } = renderHook(() =>
      useProvaDeVida(video, true, {
        criarDetector: () => Promise.resolve(detector),
        gerarAleatorio: () => 0,
        agora: relogio.agora,
        agendarProximoQuadro: agendador.agendarProximoQuadro,
        cancelarQuadroAgendado: agendador.cancelarQuadroAgendado,
        pausaEntreTentativasMs: 0,
      }),
    );

    await waitFor(() => expect(result.current.situacao).toBe("em_andamento"));
    expect(result.current.tentativa).toBe(1);

    // Esgota a janela da 1ª tentativa processando um quadro além do limite.
    act(() => {
      relogio.avancar(JANELA_DO_DESAFIO_MS + 100);
      agendador.processarProximoQuadro();
    });

    await waitFor(() => expect(result.current.tentativa).toBe(2));
    expect(
      result.current.situacao === "em_andamento" ||
        result.current.situacao === "reprovado_tentativa",
    ).toBe(true);

    // Repete até esgotar as tentativas restantes.
    for (let tentativaAtual = 2; tentativaAtual <= MAXIMO_DE_TENTATIVAS; tentativaAtual++) {
      await waitFor(() => expect(result.current.situacao).toBe("em_andamento"));
      act(() => {
        relogio.avancar(JANELA_DO_DESAFIO_MS + 100);
        agendador.processarProximoQuadro();
      });
    }

    await waitFor(() => expect(result.current.situacao).toBe("reprovado_final"));
    expect(result.current.tentativa).toBe(MAXIMO_DE_TENTATIVAS);
  });

  it("libera o detector ao desmontar (nunca deixa recurso do modelo aberto)", async () => {
    const relogio = relogioControlado();
    const agendador = criarAgendadorControlado();
    const detector = detectorFalso([QUADRO_NEUTRO]);
    const video = document.createElement("video");

    const { result, unmount } = renderHook(() =>
      useProvaDeVida(video, true, {
        criarDetector: () => Promise.resolve(detector),
        gerarAleatorio: () => 0,
        agora: relogio.agora,
        agendarProximoQuadro: agendador.agendarProximoQuadro,
        cancelarQuadroAgendado: agendador.cancelarQuadroAgendado,
      }),
    );

    await waitFor(() => expect(result.current.situacao).toBe("em_andamento"));

    unmount();

    expect(detector.liberar).toHaveBeenCalledTimes(1);
  });

  it("não roda nada quando 'ativo' é falso (economiza câmera/CPU antes da hora)", () => {
    const criarDetector = vi.fn();
    renderHook(() => useProvaDeVida(document.createElement("video"), false, { criarDetector }));
    expect(criarDetector).not.toHaveBeenCalled();
  });
});
