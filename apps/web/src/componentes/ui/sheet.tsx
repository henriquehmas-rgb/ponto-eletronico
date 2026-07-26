"use client";

import * as React from "react";
import { XIcon } from "lucide-react";
import { Dialog as SheetPrimitive } from "radix-ui";

import { cn } from "@/lib/utils";

/**
 * Folha lateral (`sheet`/`drawer`) — T4.
 *
 * Construida sobre o mesmo primitivo Radix `Dialog` (e o que o proprio
 * shadcn/ui faz): foco preso, retorno ao gatilho e `Escape` sao o MESMO
 * comportamento nativo do `Dialogo`. So a apresentacao (lateral, nao
 * centralizada) muda.
 */

function Folha({ ...props }: React.ComponentProps<typeof SheetPrimitive.Root>) {
  return <SheetPrimitive.Root data-slot="folha" {...props} />;
}

function FolhaGatilho({ ...props }: React.ComponentProps<typeof SheetPrimitive.Trigger>) {
  return <SheetPrimitive.Trigger data-slot="folha-gatilho" {...props} />;
}

function FolhaFechar({ ...props }: React.ComponentProps<typeof SheetPrimitive.Close>) {
  return <SheetPrimitive.Close data-slot="folha-fechar" {...props} />;
}

function FolhaPortal({ ...props }: React.ComponentProps<typeof SheetPrimitive.Portal>) {
  return <SheetPrimitive.Portal data-slot="folha-portal" {...props} />;
}

function FolhaCortina({ className, ...props }: React.ComponentProps<typeof SheetPrimitive.Overlay>) {
  return (
    <SheetPrimitive.Overlay
      data-slot="folha-cortina"
      className={cn(
        "fixed inset-0 z-[var(--camada-sobreposicao)] bg-fundo-sobreposicao",
        "data-[state=open]:animate-in data-[state=open]:fade-in-0",
        "data-[state=closed]:animate-out data-[state=closed]:fade-out-0",
        className,
      )}
      {...props}
    />
  );
}

const LADO_PARA_CLASSE: Record<"top" | "right" | "bottom" | "left", string> = {
  right: cn(
    "inset-y-0 right-0 h-full w-3/4 border-l border-borda-padrao sm:max-w-sm",
    "data-[state=open]:slide-in-from-right data-[state=closed]:slide-out-to-right",
  ),
  left: cn(
    "inset-y-0 left-0 h-full w-3/4 border-r border-borda-padrao sm:max-w-sm",
    "data-[state=open]:slide-in-from-left data-[state=closed]:slide-out-to-left",
  ),
  top: cn(
    "inset-x-0 top-0 h-auto border-b border-borda-padrao",
    "data-[state=open]:slide-in-from-top data-[state=closed]:slide-out-to-top",
  ),
  bottom: cn(
    "inset-x-0 bottom-0 h-auto border-t border-borda-padrao",
    "data-[state=open]:slide-in-from-bottom data-[state=closed]:slide-out-to-bottom",
  ),
};

function FolhaConteudo({
  className,
  children,
  lado = "right",
  mostrarBotaoFechar = true,
  ...props
}: React.ComponentProps<typeof SheetPrimitive.Content> & {
  lado?: "top" | "right" | "bottom" | "left";
  mostrarBotaoFechar?: boolean;
}) {
  return (
    <FolhaPortal>
      <FolhaCortina />
      <SheetPrimitive.Content
        data-slot="folha-conteudo"
        className={cn(
          "fixed z-[var(--camada-dialogo)] flex flex-col gap-4 bg-fundo-superficie text-texto-primario",
          "shadow-alta duration-lenta ease-padrao",
          "data-[state=open]:animate-in data-[state=closed]:animate-out",
          LADO_PARA_CLASSE[lado],
          className,
        )}
        {...props}
      >
        {children}
        {mostrarBotaoFechar && (
          <SheetPrimitive.Close
            data-slot="folha-fechar"
            className={cn(
              "absolute top-4 right-4 rounded-pequeno p-1 text-texto-terciario",
              "transition-colors duration-imediata ease-padrao",
              "hover:bg-fundo-enfase hover:text-texto-primario",
              "disabled:pointer-events-none",
            )}
          >
            <XIcon className="size-4" />
            <span className="sr-only">Fechar</span>
          </SheetPrimitive.Close>
        )}
      </SheetPrimitive.Content>
    </FolhaPortal>
  );
}

function FolhaCabecalho({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="folha-cabecalho"
      className={cn("flex flex-col gap-[var(--espacamento-1x5)] p-4", className)}
      {...props}
    />
  );
}

function FolhaRodape({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="folha-rodape"
      className={cn("mt-auto flex flex-col gap-2 p-4", className)}
      {...props}
    />
  );
}

function FolhaTitulo({ className, ...props }: React.ComponentProps<typeof SheetPrimitive.Title>) {
  return (
    <SheetPrimitive.Title
      data-slot="folha-titulo"
      className={cn("estilo-titulo-cartao text-texto-primario", className)}
      {...props}
    />
  );
}

function FolhaDescricao({ className, ...props }: React.ComponentProps<typeof SheetPrimitive.Description>) {
  return (
    <SheetPrimitive.Description
      data-slot="folha-descricao"
      className={cn("estilo-corpo text-texto-secundario", className)}
      {...props}
    />
  );
}

export {
  Folha,
  FolhaGatilho,
  FolhaFechar,
  FolhaConteudo,
  FolhaCabecalho,
  FolhaRodape,
  FolhaTitulo,
  FolhaDescricao,
};
