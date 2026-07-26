"use client";

import * as React from "react";
import { Separator as SeparatorPrimitive } from "radix-ui";

import { cn } from "@/lib/utils";

/** Separador — T4. */
function Separador({
  className,
  orientation = "horizontal",
  decorative = true,
  ...props
}: React.ComponentProps<typeof SeparatorPrimitive.Root>) {
  return (
    <SeparatorPrimitive.Root
      data-slot="separador"
      decorative={decorative}
      orientation={orientation}
      className={cn(
        "shrink-0 bg-borda-sutil",
        "data-[orientation=horizontal]:h-[var(--dimensao-espessura-borda)] data-[orientation=horizontal]:w-full",
        "data-[orientation=vertical]:h-full data-[orientation=vertical]:w-[var(--dimensao-espessura-borda)]",
        className,
      )}
      {...props}
    />
  );
}

export { Separador };
