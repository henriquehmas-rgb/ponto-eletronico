"use client";

import * as React from "react";
import { Label as LabelPrimitive } from "radix-ui";

import { cn } from "@/lib/utils";

/** Rotulo de campo (T3). Tipografia vem de `.estilo-rotulo` (nunca redefinida a mao). */
function Rotulo({ className, ...props }: React.ComponentProps<typeof LabelPrimitive.Root>) {
  return (
    <LabelPrimitive.Root
      data-slot="rotulo"
      className={cn(
        "estilo-rotulo flex items-center gap-2 text-texto-secundario select-none",
        "group-data-[disabled=true]:pointer-events-none group-data-[disabled=true]:text-texto-desabilitado",
        "peer-disabled:cursor-not-allowed peer-disabled:text-texto-desabilitado",
        className,
      )}
      {...props}
    />
  );
}

export { Rotulo };
