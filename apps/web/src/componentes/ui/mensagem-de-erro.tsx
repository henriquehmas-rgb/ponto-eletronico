import * as React from "react";
import { AlertCircle } from "lucide-react";

import { cn } from "@/lib/utils";

/**
 * Mensagem de erro de campo (T3).
 *
 * Sempre com icone: cor nunca e o unico portador de informacao (WCAG 2.2,
 * 1.4.1). Use `role="alert"` so leitor de tela anuncia o erro quando ele
 * aparece apos a validacao (nao no primeiro render, quando o campo ainda nao
 * foi tocado — isso e responsabilidade de quem usa o componente).
 */
function MensagemDeErro({ className, children, ...props }: React.ComponentProps<"p">) {
  if (!children) return null;
  return (
    <p
      role="alert"
      data-slot="mensagem-de-erro"
      className={cn(
        "estilo-legenda flex items-center gap-[var(--espacamento-mini)] text-estado-erro-texto",
        className,
      )}
      {...props}
    >
      <AlertCircle className="size-3.5 shrink-0 text-estado-erro-icone" aria-hidden="true" />
      {children}
    </p>
  );
}

export { MensagemDeErro };
