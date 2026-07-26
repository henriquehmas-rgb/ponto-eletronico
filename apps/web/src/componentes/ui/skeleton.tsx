import * as React from "react";

import { cn } from "@/lib/utils";

/** Esqueleto (`skeleton`) — T4. `motion-reduce:animate-none` reforca a regra global de `prefers-reduced-motion`. */
function Esqueleto({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="esqueleto"
      aria-hidden="true"
      className={cn("animate-pulse rounded-pequeno bg-fundo-enfase motion-reduce:animate-none", className)}
      {...props}
    />
  );
}

export { Esqueleto };
