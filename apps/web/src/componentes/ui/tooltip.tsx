"use client";

import * as React from "react";
import { Tooltip as TooltipPrimitive } from "radix-ui";

import { cn } from "@/lib/utils";

/** Dica (`tooltip`) — T4. Empilhamento em `camada.dica`, o mais alto depois de notificacao. */

function ProvedorDeDica({
  delayDuration = 300,
  ...props
}: React.ComponentProps<typeof TooltipPrimitive.Provider>) {
  return <TooltipPrimitive.Provider data-slot="provedor-de-dica" delayDuration={delayDuration} {...props} />;
}

function Dica({ ...props }: React.ComponentProps<typeof TooltipPrimitive.Root>) {
  return <TooltipPrimitive.Root data-slot="dica" {...props} />;
}

function DicaGatilho({ ...props }: React.ComponentProps<typeof TooltipPrimitive.Trigger>) {
  return <TooltipPrimitive.Trigger data-slot="dica-gatilho" {...props} />;
}

function DicaConteudo({
  className,
  sideOffset = 6,
  children,
  ...props
}: React.ComponentProps<typeof TooltipPrimitive.Content>) {
  return (
    <TooltipPrimitive.Portal>
      <TooltipPrimitive.Content
        data-slot="dica-conteudo"
        sideOffset={sideOffset}
        className={cn(
          "z-[var(--camada-dica)] w-fit origin-(--radix-tooltip-content-transform-origin)",
          "rounded-pequeno bg-fundo-inverso px-3 py-1.5 estilo-legenda text-texto-inverso",
          "data-[state=delayed-open]:animate-in data-[state=delayed-open]:fade-in-0 data-[state=delayed-open]:zoom-in-95",
          "data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:zoom-out-95",
          "data-[side=bottom]:slide-in-from-top-2 data-[side=top]:slide-in-from-bottom-2",
          "data-[side=left]:slide-in-from-right-2 data-[side=right]:slide-in-from-left-2",
          className,
        )}
        {...props}
      >
        {children}
        <TooltipPrimitive.Arrow className="size-2.5 -translate-y-px rotate-45 bg-fundo-inverso fill-fundo-inverso" />
      </TooltipPrimitive.Content>
    </TooltipPrimitive.Portal>
  );
}

export { ProvedorDeDica, Dica, DicaGatilho, DicaConteudo };
