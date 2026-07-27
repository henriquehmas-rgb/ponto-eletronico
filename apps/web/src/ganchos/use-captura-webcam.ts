"use client";

import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Captura ao vivo via `getUserMedia` — T6 do PCF F08.
 *
 * Encapsula TODO o ciclo de vida da `MediaStream`: pede a câmera ao montar,
 * para as trilhas ao desmontar (§9, proibição 11 — vazamento de câmera
 * ligada é falha grave de privacidade, não só detalhe técnico) e nunca
 * expõe um caminho de upload de arquivo — é sempre a câmera ao vivo (§9,
 * proibição 1).
 */
export type EstadoDaPermissaoDeCamera = "solicitando" | "concedida" | "negada" | "indisponivel";

export interface UsoDeCapturaWebcam {
  estado: EstadoDaPermissaoDeCamera;
  stream: MediaStream | null;
  trilhaDeVideo: MediaStreamTrack | null;
  mensagemDeErro: string | null;
  /** Pede a câmera de novo (ex.: colaborador negou por engano e clicou em "tentar novamente"). */
  solicitarNovamente: () => void;
}

function nomeDoErro(erro: unknown): string {
  if (erro instanceof DOMException) return erro.name;
  return "";
}

export function useCapturaWebcam(): UsoDeCapturaWebcam {
  const [estado, setEstado] = useState<EstadoDaPermissaoDeCamera>("solicitando");
  const [stream, setStream] = useState<MediaStream | null>(null);
  const [mensagemDeErro, setMensagemDeErro] = useState<string | null>(null);
  const [tentativa, setTentativa] = useState(0);
  const streamRef = useRef<MediaStream | null>(null);

  useEffect(() => {
    let cancelado = false;

    async function abrirCamera(): Promise<void> {
      setEstado("solicitando");
      setMensagemDeErro(null);

      if (typeof navigator === "undefined" || !navigator.mediaDevices?.getUserMedia) {
        if (!cancelado) setEstado("indisponivel");
        return;
      }

      try {
        const novoStream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: "user" },
          audio: false,
        });

        if (cancelado) {
          novoStream.getTracks().forEach((trilha) => trilha.stop());
          return;
        }

        streamRef.current = novoStream;
        setStream(novoStream);
        setEstado("concedida");
      } catch (erro) {
        if (cancelado) return;

        const nome = nomeDoErro(erro);
        if (
          nome === "NotAllowedError" ||
          nome === "PermissionDeniedError" ||
          nome === "SecurityError"
        ) {
          setEstado("negada");
        } else {
          // NotFoundError, DevicesNotFoundError, NotReadableError (câmera em
          // uso por outro app), OverconstrainedError etc. — tratados como a
          // mesma mensagem de "câmera indisponível" (T6, três estados).
          setEstado("indisponivel");
        }
        setMensagemDeErro(
          erro instanceof Error ? erro.message : "Falha desconhecida ao acessar a câmera.",
        );
      }
    }

    void abrirCamera();

    return () => {
      cancelado = true;
      streamRef.current?.getTracks().forEach((trilha) => trilha.stop());
      streamRef.current = null;
      setStream(null);
    };
  }, [tentativa]);

  const solicitarNovamente = useCallback(() => setTentativa((valor) => valor + 1), []);

  const primeiraTrilhaDeVideo = stream?.getVideoTracks()[0];
  const trilhaDeVideo = primeiraTrilhaDeVideo ?? null;

  return { estado, stream, trilhaDeVideo, mensagemDeErro, solicitarNovamente };
}
