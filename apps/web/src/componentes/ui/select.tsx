"use client";

import * as React from "react";
import { CheckIcon, ChevronDownIcon, ChevronUpIcon } from "lucide-react";
import { Select as SelectPrimitive } from "radix-ui";

import { cn } from "@/lib/utils";

/**
 * Selecao (`select`) — primitivo de formulario (T3).
 *
 * O menu suspenso usa `z-[var(--camada-suspenso)]`: a escala `camada` do
 * contrato tem dez niveis fixos e `suspenso` (1000) e explicitamente descrito
 * como "precisa vencer o dialogo" — por isso um `<Selecao>` dentro de um
 * `<Dialogo>` continua abrindo por cima dele. Nenhum z-index e escrito como
 * numero solto neste arquivo.
 */

function Selecao({ ...props }: React.ComponentProps<typeof SelectPrimitive.Root>) {
  return <SelectPrimitive.Root data-slot="selecao" {...props} />;
}

function SelecaoGrupo({ ...props }: React.ComponentProps<typeof SelectPrimitive.Group>) {
  return <SelectPrimitive.Group data-slot="selecao-grupo" {...props} />;
}

function SelecaoValor({ ...props }: React.ComponentProps<typeof SelectPrimitive.Value>) {
  return <SelectPrimitive.Value data-slot="selecao-valor" {...props} />;
}

interface SelecaoGatilhoProps extends React.ComponentProps<typeof SelectPrimitive.Trigger> {
  tamanho?: "padrao" | "compacto";
}

function SelecaoGatilho({ className, tamanho = "padrao", children, ...props }: SelecaoGatilhoProps) {
  return (
    <SelectPrimitive.Trigger
      data-slot="selecao-gatilho"
      data-tamanho={tamanho}
      className={cn(
        "flex w-fit items-center justify-between gap-2 rounded-pequeno border border-borda-controle",
        "bg-fundo-superficie px-3 estilo-corpo text-texto-primario",
        "transition-colors duration-imediata ease-padrao",
        tamanho === "padrao"
          ? "h-[var(--dimensao-altura-controle)]"
          : "h-[var(--dimensao-altura-controle-compacta)]",
        "hover:border-borda-forte",
        "disabled:cursor-not-allowed disabled:border-borda-sutil disabled:bg-fundo-desabilitado disabled:text-texto-desabilitado",
        "aria-invalid:border-estado-erro-borda",
        "data-[placeholder]:text-texto-terciario",
        "[&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4 [&_svg:not([class*='text-'])]:text-texto-terciario",
        className,
      )}
      {...props}
    >
      {children}
      <SelectPrimitive.Icon asChild>
        <ChevronDownIcon className="size-4" />
      </SelectPrimitive.Icon>
    </SelectPrimitive.Trigger>
  );
}

function SelecaoConteudo({
  className,
  children,
  position = "item-aligned",
  align = "center",
  ...props
}: React.ComponentProps<typeof SelectPrimitive.Content>) {
  return (
    <SelectPrimitive.Portal>
      <SelectPrimitive.Content
        data-slot="selecao-conteudo"
        className={cn(
          "relative z-[var(--camada-suspenso)] max-h-(--radix-select-content-available-height)",
          "min-w-32 origin-(--radix-select-content-transform-origin) overflow-x-hidden overflow-y-auto",
          "rounded-medio border border-borda-padrao bg-fundo-superficie-elevada text-texto-primario shadow-media",
          position === "popper" &&
            "data-[side=bottom]:translate-y-1 data-[side=left]:-translate-x-1 data-[side=right]:translate-x-1 data-[side=top]:-translate-y-1",
          className,
        )}
        position={position}
        align={align}
        {...props}
      >
        <SelecaoRolarParaCima />
        <SelectPrimitive.Viewport
          className={cn(
            "p-1",
            position === "popper" &&
              "h-[var(--radix-select-trigger-height)] w-full min-w-[var(--radix-select-trigger-width)] scroll-my-1",
          )}
        >
          {children}
        </SelectPrimitive.Viewport>
        <SelecaoRolarParaBaixo />
      </SelectPrimitive.Content>
    </SelectPrimitive.Portal>
  );
}

function SelecaoRotulo({ className, ...props }: React.ComponentProps<typeof SelectPrimitive.Label>) {
  return (
    <SelectPrimitive.Label
      data-slot="selecao-rotulo"
      className={cn("estilo-legenda px-2 py-1.5 text-texto-terciario", className)}
      {...props}
    />
  );
}

function SelecaoItem({ className, children, ...props }: React.ComponentProps<typeof SelectPrimitive.Item>) {
  return (
    <SelectPrimitive.Item
      data-slot="selecao-item"
      className={cn(
        "relative flex w-full cursor-default items-center gap-2 rounded-pequeno py-1.5 pr-8 pl-2",
        "estilo-corpo select-none",
        "focus:bg-fundo-enfase focus:text-texto-primario",
        "data-[disabled]:pointer-events-none data-[disabled]:text-texto-desabilitado",
        "[&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
        className,
      )}
      {...props}
    >
      <span
        data-slot="selecao-item-indicador"
        className="absolute right-2 flex size-3.5 items-center justify-center"
      >
        <SelectPrimitive.ItemIndicator>
          <CheckIcon className="size-4" />
        </SelectPrimitive.ItemIndicator>
      </span>
      <SelectPrimitive.ItemText>{children}</SelectPrimitive.ItemText>
    </SelectPrimitive.Item>
  );
}

function SelecaoSeparador({
  className,
  ...props
}: React.ComponentProps<typeof SelectPrimitive.Separator>) {
  return (
    <SelectPrimitive.Separator
      data-slot="selecao-separador"
      className={cn(
        "pointer-events-none -mx-1 my-1 h-[var(--dimensao-espessura-borda)] bg-borda-sutil",
        className,
      )}
      {...props}
    />
  );
}

function SelecaoRolarParaCima({
  className,
  ...props
}: React.ComponentProps<typeof SelectPrimitive.ScrollUpButton>) {
  return (
    <SelectPrimitive.ScrollUpButton
      data-slot="selecao-rolar-cima"
      className={cn("flex cursor-default items-center justify-center py-1", className)}
      {...props}
    >
      <ChevronUpIcon className="size-4" />
    </SelectPrimitive.ScrollUpButton>
  );
}

function SelecaoRolarParaBaixo({
  className,
  ...props
}: React.ComponentProps<typeof SelectPrimitive.ScrollDownButton>) {
  return (
    <SelectPrimitive.ScrollDownButton
      data-slot="selecao-rolar-baixo"
      className={cn("flex cursor-default items-center justify-center py-1", className)}
      {...props}
    >
      <ChevronDownIcon className="size-4" />
    </SelectPrimitive.ScrollDownButton>
  );
}

export {
  Selecao,
  SelecaoConteudo,
  SelecaoGrupo,
  SelecaoItem,
  SelecaoRotulo,
  SelecaoRolarParaBaixo,
  SelecaoRolarParaCima,
  SelecaoSeparador,
  SelecaoGatilho,
  SelecaoValor,
};
