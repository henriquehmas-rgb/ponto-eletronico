import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { Slot } from "radix-ui";

import { cn } from "@/lib/utils";

/**
 * Selo (`badge`) — T4.
 *
 * As variantes de estado usam par fundo+borda+texto do MESMO grupo semantico
 * (nunca so a cor de fundo isolada) — a borda de contraste 3:1 medida no
 * contrato (`estado.<x>Borda`) e o texto 4.5:1 (`estado.<x>Texto`) garantem
 * que o selo se sustenta mesmo em modo de alto contraste ou impressao P&B. O
 * selo sempre carrega um rotulo de texto (nunca so uma amostra de cor).
 */
const badgeVariants = cva(
  cn(
    "inline-flex w-fit shrink-0 items-center justify-center gap-1 overflow-hidden rounded-pleno border",
    "px-2 py-0.5 estilo-legenda whitespace-nowrap",
    "[&>svg]:pointer-events-none [&>svg]:size-3",
  ),
  {
    variants: {
      variant: {
        neutro: "border-borda-padrao bg-fundo-sutil text-texto-secundario",
        primario: "border-transparent bg-acao-primaria-fundo text-acao-primaria-texto",
        sucesso: "border-estado-sucesso-borda bg-estado-sucesso-fundo text-estado-sucesso-texto",
        atencao: "border-estado-atencao-borda bg-estado-atencao-fundo text-estado-atencao-texto",
        erro: "border-estado-erro-borda bg-estado-erro-fundo text-estado-erro-texto",
        info: "border-estado-info-borda bg-estado-info-fundo text-estado-info-texto",
      },
    },
    defaultVariants: {
      variant: "neutro",
    },
  },
);

interface SeloProps
  extends React.ComponentProps<"span">,
    VariantProps<typeof badgeVariants> {
  asChild?: boolean;
}

function Selo({ className, variant, asChild = false, ...props }: SeloProps) {
  const Comp = asChild ? Slot.Root : "span";
  return (
    <Comp
      data-slot="selo"
      data-variant={variant}
      className={cn(badgeVariants({ variant, className }))}
      {...props}
    />
  );
}

export { Selo, badgeVariants };
