"use client";

import { useEffect, useRef } from "react";

import { Alerta, AlertaDescricao, AlertaTitulo } from "@/componentes/ui/alert";
import { Botao } from "@/componentes/ui/button";
import { Cartao } from "@/componentes/ui/card";
import { Esqueleto } from "@/componentes/ui/skeleton";
import type { EstadoDaPermissaoDeCamera } from "@/ganchos/use-captura-webcam";

/**
 * Captura de vídeo ao vivo — T6 do PCF F08.
 *
 * Puramente apresentacional: recebe o `estado`/`stream` de
 * `useCapturaWebcam` e renderiza os TRÊS estados de permissão pedidos pelo
 * PCF (concedida, negada, indisponível), cada um com mensagem clara.
 *
 * NUNCA existe `<input type="file">` aqui nem em nenhum componente desta
 * fase (§9, proibição 1) — é sempre a câmera ao vivo via `getUserMedia`
 * (`useCapturaWebcam`, T6), nunca uma imagem enviada de outro lugar.
 */
export interface CapturaDeVideoProps {
  estado: EstadoDaPermissaoDeCamera;
  stream: MediaStream | null;
  onVideoPronto?: (video: HTMLVideoElement) => void;
  aoSolicitarNovamente?: () => void;
}

export function CapturaDeVideo({
  estado,
  stream,
  onVideoPronto,
  aoSolicitarNovamente,
}: CapturaDeVideoProps) {
  const videoRef = useRef<HTMLVideoElement | null>(null);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    video.srcObject = stream;
    return () => {
      video.srcObject = null;
    };
  }, [stream]);

  if (estado === "solicitando") {
    return (
      <Cartao
        role="status"
        aria-live="polite"
        className="items-center gap-[var(--espacamento-2)] rounded-suave p-[var(--espacamento-4)] shadow-flutuante-cartao"
      >
        <Esqueleto className="aspect-video w-full" />
        <p className="estilo-legenda text-texto-secundario">Aguardando permissão da câmera…</p>
      </Cartao>
    );
  }

  if (estado === "negada") {
    return (
      <Alerta variant="atencao" className="rounded-suave shadow-flutuante-cartao">
        <AlertaTitulo>Permissão de câmera negada</AlertaTitulo>
        <AlertaDescricao>
          Para registrar o ponto pela webcam, autorize o acesso à câmera nas configurações do
          navegador e tente novamente.
        </AlertaDescricao>
        {aoSolicitarNovamente && (
          <Botao
            type="button"
            variant="secundaria"
            tamanho="compacto"
            className="mt-[var(--espacamento-1)] w-fit"
            onClick={aoSolicitarNovamente}
          >
            Tentar novamente
          </Botao>
        )}
      </Alerta>
    );
  }

  if (estado === "indisponivel") {
    return (
      <Alerta variant="erro" className="rounded-suave shadow-flutuante-cartao">
        <AlertaTitulo>Câmera indisponível</AlertaTitulo>
        <AlertaDescricao>
          Não encontramos uma câmera neste dispositivo. Use um computador ou celular com câmera para
          registrar o ponto por aqui.
        </AlertaDescricao>
      </Alerta>
    );
  }

  // Estado "concedida": renderizado dentro do painel escuro fixo de captura
  // (`FluxoDeRegistro`) — a moldura oval, o vinheteamento e o recorte
  // arredondado já vêm do contêiner pai, então o `<video>` aqui só precisa
  // preencher o espaço disponível.
  return (
    <video
      ref={(elemento) => {
        videoRef.current = elemento;
        if (elemento) onVideoPronto?.(elemento);
      }}
      autoPlay
      playsInline
      muted
      aria-label="Captura ao vivo da câmera para registro de ponto"
      className="-scale-x-100 size-full object-cover"
    />
  );
}
