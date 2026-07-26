import * as React from "react";

import { cn } from "@/lib/utils";

/** Area de texto — mesma linguagem visual de `Entrada` (T3). */
function AreaDeTexto({ className, ...props }: React.ComponentProps<"textarea">) {
  return (
    <textarea
      data-slot="area-de-texto"
      className={cn(
        "flex field-sizing-content min-h-[calc(var(--dimensao-altura-controle)*2)] w-full",
        "rounded-pequeno border border-borda-controle bg-fundo-superficie px-3 py-2",
        "estilo-corpo text-texto-primario transition-colors duration-imediata ease-padrao",
        "placeholder:text-texto-terciario",
        "hover:border-borda-forte",
        "read-only:border-borda-sutil read-only:bg-fundo-sutil",
        "disabled:cursor-not-allowed disabled:border-borda-sutil disabled:bg-fundo-desabilitado disabled:text-texto-desabilitado",
        "aria-invalid:border-estado-erro-borda aria-invalid:text-estado-erro-texto",
        className,
      )}
      {...props}
    />
  );
}

export { AreaDeTexto };
