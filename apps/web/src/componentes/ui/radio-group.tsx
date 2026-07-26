"use client";

import * as React from "react";
import { CircleIcon } from "lucide-react";
import { RadioGroup as RadioGroupPrimitive } from "radix-ui";

import { cn } from "@/lib/utils";

/** Grupo de radio — navega por setas nativamente (Radix). */
function GrupoDeRadio({
  className,
  ...props
}: React.ComponentProps<typeof RadioGroupPrimitive.Root>) {
  return (
    <RadioGroupPrimitive.Root
      data-slot="grupo-de-radio"
      className={cn("grid gap-[var(--espacamento-1x5)]", className)}
      {...props}
    />
  );
}

interface ItemDeRadioProps extends React.ComponentProps<typeof RadioGroupPrimitive.Item> {
  /** Ver nota de `CaixaDeSelecao.tamanho` — mesmo racional de alvo de toque. */
  tamanho?: "padrao" | "toque";
}

function ItemDeRadio({ className, tamanho = "padrao", ...props }: ItemDeRadioProps) {
  const botao = (
    <RadioGroupPrimitive.Item
      data-slot="item-de-radio"
      className={cn(
        "aspect-square size-4 shrink-0 rounded-pleno border border-borda-controle bg-fundo-superficie",
        "text-acao-primaria-fundo transition-colors duration-imediata ease-padrao",
        "hover:border-borda-forte",
        "disabled:cursor-not-allowed disabled:border-borda-sutil disabled:bg-fundo-desabilitado",
        "aria-invalid:border-estado-erro-borda",
        "data-[state=checked]:border-acao-primaria-fundo",
        className,
      )}
      {...props}
    >
      <RadioGroupPrimitive.Indicator
        data-slot="item-de-radio-indicador"
        className="relative flex items-center justify-center"
      >
        <CircleIcon className="absolute top-1/2 left-1/2 size-2 -translate-x-1/2 -translate-y-1/2 fill-acao-primaria-fundo" />
      </RadioGroupPrimitive.Indicator>
    </RadioGroupPrimitive.Item>
  );

  if (tamanho === "padrao") return botao;

  return (
    <span className="inline-flex size-[var(--dimensao-alvo-toque)] items-center justify-center">
      {botao}
    </span>
  );
}

export { GrupoDeRadio, ItemDeRadio };
