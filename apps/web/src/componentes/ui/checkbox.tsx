"use client";

import * as React from "react";
import { CheckIcon } from "lucide-react";
import { Checkbox as CheckboxPrimitive } from "radix-ui";

import { cn } from "@/lib/utils";

interface CaixaDeSelecaoProps extends React.ComponentProps<typeof CheckboxPrimitive.Root> {
  /**
   * `toque` envolve o controle visual (16 px) num alvo de 44x44 px
   * (`--dimensao-alvo-toque`), sem alterar o tamanho VISUAL da caixa — o
   * requisito e area de toque, nao caixa gigante (criterio 2.5.8).
   */
  tamanho?: "padrao" | "toque";
}

/** Caixa de selecao — primitivo de formulario (T3). */
function CaixaDeSelecao({ className, tamanho = "padrao", ...props }: CaixaDeSelecaoProps) {
  const caixa = (
    <CheckboxPrimitive.Root
      data-slot="caixa-de-selecao"
      className={cn(
        "peer size-4 shrink-0 rounded-pequeno border border-borda-controle bg-fundo-superficie",
        "transition-colors duration-imediata ease-padrao",
        "hover:border-borda-forte",
        "disabled:cursor-not-allowed disabled:border-borda-sutil disabled:bg-fundo-desabilitado",
        "aria-invalid:border-estado-erro-borda",
        "data-[state=checked]:border-acao-primaria-fundo data-[state=checked]:bg-acao-primaria-fundo",
        "data-[state=checked]:text-acao-primaria-texto",
        className,
      )}
      {...props}
    >
      <CheckboxPrimitive.Indicator
        data-slot="caixa-de-selecao-indicador"
        className="grid place-content-center text-current"
      >
        <CheckIcon className="size-3.5" />
      </CheckboxPrimitive.Indicator>
    </CheckboxPrimitive.Root>
  );

  if (tamanho === "padrao") return caixa;

  return (
    <span className="inline-flex size-[var(--dimensao-alvo-toque)] items-center justify-center">
      {caixa}
    </span>
  );
}

export { CaixaDeSelecao };
