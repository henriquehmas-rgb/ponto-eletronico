import * as React from "react";

import { cn } from "@/lib/utils";

/**
 * Entrada (`<input>`) — primitivo de formulario (T3).
 *
 * `outline-none`/`ring-*` propositalmente ausentes: o anel de foco vem do
 * `:focus-visible` global (`src/estilos/globais.css`), token
 * `tema.<t>.borda.foco`. `aria-invalid` e `readonly` mudam a borda por token;
 * `disabled` muda fundo e texto por token (nunca so opacidade).
 */
function Entrada({ className, type, ...props }: React.ComponentProps<"input">) {
  return (
    <input
      type={type}
      data-slot="entrada"
      className={cn(
        "h-[var(--dimensao-altura-controle)] w-full min-w-0 rounded-pequeno border border-borda-controle",
        "bg-fundo-superficie px-3 estilo-corpo text-texto-primario",
        "transition-colors duration-imediata ease-padrao",
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

export { Entrada };
