import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { Slot } from "radix-ui";

import { cn } from "@/lib/utils";

/**
 * Botao — primitivo de formulario (T3 do PCF F09a).
 *
 * Todo valor de cor, raio, tamanho e movimento vem de token semantico (nunca
 * primitivo, nunca literal). O anel de foco NAO e redeclarado aqui: o
 * `:focus-visible` global de `src/estilos/globais.css` ja aplica o anel do
 * contrato (2 px, deslocamento 2 px, `tema.<t>.borda.foco`) a todo elemento
 * focavel — por isso este componente nunca usa `outline-none` nem `ring-*`,
 * que brigariam com essa regra unica.
 *
 * Nota de contrato: `tema.<t>.acao` define `primariaFundoHover` E
 * `primariaFundoAtivo`, mas NAO define um tom de "ativo" separado para
 * `secundaria`, `sutil` ou `destrutiva` — so hover. Onde o contrato nao
 * distingue, `active:` reaproveita o mesmo token de `hover:` (nao inventa cor
 * nova); registrado em `docs/backlog.md` como possivel lacuna do contrato.
 */
const buttonVariants = cva(
  cn(
    "inline-flex shrink-0 items-center justify-center gap-2 rounded-pequeno",
    "estilo-rotulo whitespace-nowrap",
    "transition-colors duration-imediata ease-padrao",
    "disabled:pointer-events-none disabled:cursor-not-allowed",
    "disabled:border-borda-sutil disabled:bg-fundo-desabilitado disabled:text-texto-desabilitado",
    "[&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
  ),
  {
    variants: {
      variant: {
        primaria: cn(
          "bg-acao-primaria-fundo text-acao-primaria-texto",
          "hover:bg-acao-primaria-fundo-hover active:bg-acao-primaria-fundo-ativo",
        ),
        secundaria: cn(
          "border border-acao-secundaria-borda bg-acao-secundaria-fundo text-acao-secundaria-texto",
          "hover:bg-acao-secundaria-fundo-hover active:bg-acao-secundaria-fundo-hover",
        ),
        sutil: cn(
          "bg-acao-sutil-fundo text-acao-sutil-texto",
          "hover:bg-fundo-enfase active:bg-fundo-enfase",
        ),
        destrutiva: cn(
          "bg-acao-destrutiva-fundo text-acao-destrutiva-texto",
          "hover:bg-acao-destrutiva-fundo-hover active:bg-acao-destrutiva-fundo-hover",
        ),
      },
      tamanho: {
        padrao: "h-[var(--dimensao-altura-controle)] px-4",
        compacto: "h-[var(--dimensao-altura-controle-compacta)] px-3",
        toque: "h-[var(--dimensao-altura-controle-toque)] px-5",
        icone: "size-[var(--dimensao-altura-controle)] p-0",
        "icone-toque": "size-[var(--dimensao-alvo-toque)] p-0",
      },
    },
    defaultVariants: {
      variant: "primaria",
      tamanho: "padrao",
    },
  },
);

interface BotaoProps
  extends React.ComponentProps<"button">,
    VariantProps<typeof buttonVariants> {
  /** Renderiza no elemento filho em vez de `<button>` (padrao Radix `Slot`). */
  asChild?: boolean;
}

function Botao({ className, variant, tamanho, asChild = false, ...props }: BotaoProps) {
  const Comp = asChild ? Slot.Root : "button";
  return (
    <Comp
      data-slot="botao"
      data-variant={variant}
      data-tamanho={tamanho}
      className={cn(buttonVariants({ variant, tamanho, className }))}
      {...props}
    />
  );
}

export { Botao, buttonVariants };
