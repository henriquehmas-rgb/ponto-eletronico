"use client";

import * as React from "react";
import { Switch as SwitchPrimitive } from "radix-ui";

import { cn } from "@/lib/utils";

interface InterruptorProps extends React.ComponentProps<typeof SwitchPrimitive.Root> {
  tamanho?: "padrao" | "toque";
}

/** Interruptor (`switch`) — primitivo de formulario (T3). */
function Interruptor({ className, tamanho = "padrao", ...props }: InterruptorProps) {
  const controle = (
    <SwitchPrimitive.Root
      data-slot="interruptor"
      className={cn(
        "peer inline-flex h-5 w-9 shrink-0 items-center rounded-pleno border border-transparent p-0.5",
        "transition-colors duration-imediata ease-padrao",
        "disabled:cursor-not-allowed disabled:border-borda-sutil disabled:bg-fundo-desabilitado",
        "data-[state=checked]:bg-acao-primaria-fundo data-[state=unchecked]:bg-fundo-enfase",
        className,
      )}
      {...props}
    >
      <SwitchPrimitive.Thumb
        data-slot="interruptor-marcador"
        className={cn(
          "pointer-events-none block size-4 rounded-pleno bg-fundo-superficie shadow-baixa",
          "transition-transform duration-imediata ease-padrao",
          "data-[state=checked]:translate-x-4 data-[state=unchecked]:translate-x-0",
        )}
      />
    </SwitchPrimitive.Root>
  );

  if (tamanho === "padrao") return controle;

  return (
    <span className="inline-flex size-[var(--dimensao-alvo-toque)] items-center justify-center">
      {controle}
    </span>
  );
}

export { Interruptor };
