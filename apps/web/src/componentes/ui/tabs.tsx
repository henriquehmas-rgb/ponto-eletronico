"use client";

import * as React from "react";
import { Tabs as TabsPrimitive } from "radix-ui";

import { cn } from "@/lib/utils";

/** Abas (`tabs`) — T4. Setas navegam entre abas (comportamento nativo do Radix). */

function Abas({
  className,
  orientation = "horizontal",
  ...props
}: React.ComponentProps<typeof TabsPrimitive.Root>) {
  return (
    <TabsPrimitive.Root
      data-slot="abas"
      orientation={orientation}
      className={cn("group/abas flex gap-2 data-[orientation=horizontal]:flex-col", className)}
      {...props}
    />
  );
}

function ListaDeAbas({ className, ...props }: React.ComponentProps<typeof TabsPrimitive.List>) {
  return (
    <TabsPrimitive.List
      data-slot="lista-de-abas"
      className={cn(
        "inline-flex w-fit items-center justify-center gap-1 rounded-medio bg-fundo-sutil p-1",
        "group-data-[orientation=vertical]/abas:h-fit group-data-[orientation=vertical]/abas:flex-col",
        className,
      )}
      {...props}
    />
  );
}

function AbaGatilho({ className, ...props }: React.ComponentProps<typeof TabsPrimitive.Trigger>) {
  return (
    <TabsPrimitive.Trigger
      data-slot="aba-gatilho"
      className={cn(
        "inline-flex h-[var(--dimensao-altura-controle-compacta)] flex-1 items-center justify-center gap-1.5",
        "rounded-pequeno px-3 estilo-rotulo text-texto-terciario",
        "transition-colors duration-imediata ease-padrao",
        "group-data-[orientation=vertical]/abas:w-full group-data-[orientation=vertical]/abas:justify-start",
        "hover:text-texto-primario",
        "disabled:pointer-events-none disabled:text-texto-desabilitado",
        "data-[state=active]:bg-fundo-superficie data-[state=active]:text-texto-primario data-[state=active]:shadow-baixa",
        "[&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
        className,
      )}
      {...props}
    />
  );
}

function ConteudoDaAba({ className, ...props }: React.ComponentProps<typeof TabsPrimitive.Content>) {
  return <TabsPrimitive.Content data-slot="conteudo-da-aba" className={cn("flex-1", className)} {...props} />;
}

export { Abas, ListaDeAbas, AbaGatilho, ConteudoDaAba };
