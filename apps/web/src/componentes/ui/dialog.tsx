"use client";

import * as React from "react";
import { XIcon } from "lucide-react";
import { Dialog as DialogPrimitive } from "radix-ui";

import { cn } from "@/lib/utils";

/**
 * Dialogo (modal) — T4.
 *
 * Foco preso e retorno ao gatilho ao fechar sao comportamento NATIVO do
 * `Dialog` do Radix (`DialogPrimitive.Content` monta um focus trap e devolve
 * o foco ao elemento que abriu o dialogo); `Escape` fecha por padrao. Este
 * arquivo so estiliza — nao reimplementa nada disso.
 *
 * Empilhamento: `sobreposicao` (cortina) e `dialogo` (conteudo) vem
 * exclusivamente da escala `camada` do contrato — nunca um numero solto.
 */

function Dialogo({ ...props }: React.ComponentProps<typeof DialogPrimitive.Root>) {
  return <DialogPrimitive.Root data-slot="dialogo" {...props} />;
}

function DialogoGatilho({ ...props }: React.ComponentProps<typeof DialogPrimitive.Trigger>) {
  return <DialogPrimitive.Trigger data-slot="dialogo-gatilho" {...props} />;
}

function DialogoPortal({ ...props }: React.ComponentProps<typeof DialogPrimitive.Portal>) {
  return <DialogPrimitive.Portal data-slot="dialogo-portal" {...props} />;
}

function DialogoFechar({ ...props }: React.ComponentProps<typeof DialogPrimitive.Close>) {
  return <DialogPrimitive.Close data-slot="dialogo-fechar" {...props} />;
}

function DialogoCortina({ className, ...props }: React.ComponentProps<typeof DialogPrimitive.Overlay>) {
  return (
    <DialogPrimitive.Overlay
      data-slot="dialogo-cortina"
      className={cn(
        "fixed inset-0 z-[var(--camada-sobreposicao)] bg-fundo-sobreposicao",
        "data-[state=open]:animate-in data-[state=open]:fade-in-0",
        "data-[state=closed]:animate-out data-[state=closed]:fade-out-0",
        "duration-padrao",
        className,
      )}
      {...props}
    />
  );
}

function DialogoConteudo({
  className,
  children,
  mostrarBotaoFechar = true,
  ...props
}: React.ComponentProps<typeof DialogPrimitive.Content> & { mostrarBotaoFechar?: boolean }) {
  return (
    <DialogoPortal>
      <DialogoCortina />
      <DialogPrimitive.Content
        data-slot="dialogo-conteudo"
        className={cn(
          "fixed top-1/2 left-1/2 z-[var(--camada-dialogo)] grid w-full",
          "max-w-[calc(100%-var(--espacamento-4))]",
          "-translate-x-1/2 -translate-y-1/2 gap-4 rounded-grande border border-borda-padrao",
          "bg-fundo-superficie p-6 text-texto-primario shadow-alta duration-padrao",
          "data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-95",
          "data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:zoom-out-95",
          "sm:max-w-lg",
          className,
        )}
        {...props}
      >
        {children}
        {mostrarBotaoFechar && (
          <DialogPrimitive.Close
            data-slot="dialogo-fechar"
            className={cn(
              "absolute top-4 right-4 rounded-pequeno p-1 text-texto-terciario",
              "transition-colors duration-imediata ease-padrao",
              "hover:bg-fundo-enfase hover:text-texto-primario",
              "disabled:pointer-events-none",
              "[&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
            )}
          >
            <XIcon />
            <span className="sr-only">Fechar</span>
          </DialogPrimitive.Close>
        )}
      </DialogPrimitive.Content>
    </DialogoPortal>
  );
}

function DialogoCabecalho({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="dialogo-cabecalho"
      className={cn("flex flex-col gap-2 text-center sm:text-left", className)}
      {...props}
    />
  );
}

function DialogoRodape({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="dialogo-rodape"
      className={cn("flex flex-col-reverse gap-2 sm:flex-row sm:justify-end", className)}
      {...props}
    />
  );
}

function DialogoTitulo({ className, ...props }: React.ComponentProps<typeof DialogPrimitive.Title>) {
  return (
    <DialogPrimitive.Title
      data-slot="dialogo-titulo"
      className={cn("estilo-titulo-cartao text-texto-primario", className)}
      {...props}
    />
  );
}

function DialogoDescricao({
  className,
  ...props
}: React.ComponentProps<typeof DialogPrimitive.Description>) {
  return (
    <DialogPrimitive.Description
      data-slot="dialogo-descricao"
      className={cn("estilo-corpo text-texto-secundario", className)}
      {...props}
    />
  );
}

export {
  Dialogo,
  DialogoFechar,
  DialogoConteudo,
  DialogoDescricao,
  DialogoRodape,
  DialogoCabecalho,
  DialogoCortina,
  DialogoPortal,
  DialogoTitulo,
  DialogoGatilho,
};
