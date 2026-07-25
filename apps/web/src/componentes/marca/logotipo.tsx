import type { HTMLAttributes } from "react";

import { cn } from "@/lib/utils";

import { SimboloSeegPonto } from "./simbolo";

interface LogotipoSeegPontoProps extends HTMLAttributes<HTMLSpanElement> {
  /** Omite o texto "SEEG PONTO", deixando so o simbolo (favicon, app icon, espaco apertado). */
  somenteSimbolo?: boolean;
}

/**
 * Logotipo oficial: simbolo + nome, em texto real (nao SVG <text>) — herda o
 * fluxo do documento, e selecionavel/pesquisavel e escala com `font-size` do
 * container. O nome usa a voz de display (Schibsted Grotesk).
 *
 * Area de protecao (Manual de Marca): nunca menor que a altura do proprio
 * traco em todos os lados — o `gap` deste componente ja e essa distancia
 * minima; nao reduza para encaixar em espaco apertado, use `somenteSimbolo`.
 */
export function LogotipoSeegPonto({
  somenteSimbolo = false,
  className,
  ...props
}: LogotipoSeegPontoProps) {
  return (
    <span className={cn("inline-flex items-center gap-2 text-texto-link", className)} {...props}>
      <SimboloSeegPonto className="h-[1.1em] w-[1.1em] shrink-0" />
      {!somenteSimbolo && (
        <span className="font-display text-[1.05em] font-bold tracking-tight text-texto-primario">
          SEEG PONTO
        </span>
      )}
    </span>
  );
}
