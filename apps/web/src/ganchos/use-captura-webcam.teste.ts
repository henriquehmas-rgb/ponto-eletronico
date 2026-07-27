import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useCapturaWebcam } from "./use-captura-webcam";

/** Dublê mínimo de `MediaStreamTrack` — só o que o gancho usa. */
function criarTrilhaFalsa(): MediaStreamTrack {
  return { stop: vi.fn(), readyState: "live" } as unknown as MediaStreamTrack;
}

/** Dublê mínimo de `MediaStream` — só o que o gancho usa. */
function criarStreamFalso(trilha: MediaStreamTrack): MediaStream {
  return {
    getTracks: () => [trilha],
    getVideoTracks: () => [trilha],
  } as unknown as MediaStream;
}

describe("useCapturaWebcam", () => {
  const getUserMediaOriginal = navigator.mediaDevices?.getUserMedia;

  afterEach(() => {
    vi.restoreAllMocks();
    if (getUserMediaOriginal) {
      Object.defineProperty(navigator.mediaDevices, "getUserMedia", {
        value: getUserMediaOriginal,
        configurable: true,
      });
    }
  });

  beforeEach(() => {
    if (!navigator.mediaDevices) {
      Object.defineProperty(navigator, "mediaDevices", { value: {}, configurable: true });
    }
  });

  it("concede a câmera e expõe o stream quando getUserMedia resolve", async () => {
    const trilha = criarTrilhaFalsa();
    const stream = criarStreamFalso(trilha);
    const getUserMedia = vi.fn().mockResolvedValue(stream);
    Object.defineProperty(navigator.mediaDevices, "getUserMedia", {
      value: getUserMedia,
      configurable: true,
    });

    const { result } = renderHook(() => useCapturaWebcam());

    expect(result.current.estado).toBe("solicitando");

    await waitFor(() => expect(result.current.estado).toBe("concedida"));
    expect(result.current.stream).toBe(stream);
    expect(result.current.trilhaDeVideo).toBe(trilha);
    expect(getUserMedia).toHaveBeenCalledWith({ video: { facingMode: "user" }, audio: false });
  });

  it("marca 'negada' quando o colaborador nega a permissão", async () => {
    const getUserMedia = vi.fn().mockRejectedValue(new DOMException("negado", "NotAllowedError"));
    Object.defineProperty(navigator.mediaDevices, "getUserMedia", {
      value: getUserMedia,
      configurable: true,
    });

    const { result } = renderHook(() => useCapturaWebcam());

    await waitFor(() => expect(result.current.estado).toBe("negada"));
  });

  it("marca 'indisponivel' quando nenhuma câmera é encontrada", async () => {
    const getUserMedia = vi.fn().mockRejectedValue(new DOMException("sem camera", "NotFoundError"));
    Object.defineProperty(navigator.mediaDevices, "getUserMedia", {
      value: getUserMedia,
      configurable: true,
    });

    const { result } = renderHook(() => useCapturaWebcam());

    await waitFor(() => expect(result.current.estado).toBe("indisponivel"));
  });

  it("marca 'indisponivel' quando o navegador não tem getUserMedia", async () => {
    Object.defineProperty(navigator, "mediaDevices", { value: undefined, configurable: true });

    const { result } = renderHook(() => useCapturaWebcam());

    await waitFor(() => expect(result.current.estado).toBe("indisponivel"));
  });

  it("para todas as trilhas ao desmontar (nunca deixa a câmera ligada)", async () => {
    const trilha = criarTrilhaFalsa();
    const stream = criarStreamFalso(trilha);
    const getUserMedia = vi.fn().mockResolvedValue(stream);
    Object.defineProperty(navigator.mediaDevices, "getUserMedia", {
      value: getUserMedia,
      configurable: true,
    });

    const { result, unmount } = renderHook(() => useCapturaWebcam());
    await waitFor(() => expect(result.current.estado).toBe("concedida"));

    unmount();

    expect(trilha.stop).toHaveBeenCalledTimes(1);
  });

  it("solicitarNovamente pede a câmera de novo", async () => {
    const trilha1 = criarTrilhaFalsa();
    const getUserMedia = vi.fn().mockResolvedValue(criarStreamFalso(trilha1));
    Object.defineProperty(navigator.mediaDevices, "getUserMedia", {
      value: getUserMedia,
      configurable: true,
    });

    const { result } = renderHook(() => useCapturaWebcam());
    await waitFor(() => expect(result.current.estado).toBe("concedida"));
    expect(getUserMedia).toHaveBeenCalledTimes(1);

    act(() => {
      result.current.solicitarNovamente();
    });

    await waitFor(() => expect(getUserMedia).toHaveBeenCalledTimes(2));
  });
});
