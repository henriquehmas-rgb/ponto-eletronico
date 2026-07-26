import * as React from "react";

import { cn } from "@/lib/utils";

/** Cartao (`card`) — T4. */

function Cartao({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="cartao"
      className={cn(
        "flex flex-col gap-[var(--espacamento-4)] rounded-medio border border-borda-padrao",
        "bg-fundo-superficie py-[var(--espacamento-4)] text-texto-primario shadow-baixa",
        className,
      )}
      {...props}
    />
  );
}

function CartaoCabecalho({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="cartao-cabecalho"
      className={cn(
        "grid auto-rows-min grid-rows-[auto_auto] items-start gap-2 px-[var(--espacamento-4)]",
        "has-data-[slot=cartao-acao]:grid-cols-[1fr_auto]",
        className,
      )}
      {...props}
    />
  );
}

function CartaoTitulo({ className, ...props }: React.ComponentProps<"div">) {
  return <div data-slot="cartao-titulo" className={cn("estilo-titulo-cartao", className)} {...props} />;
}

function CartaoDescricao({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="cartao-descricao"
      className={cn("estilo-corpo text-texto-secundario", className)}
      {...props}
    />
  );
}

function CartaoAcao({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="cartao-acao"
      className={cn("col-start-2 row-span-2 row-start-1 self-start justify-self-end", className)}
      {...props}
    />
  );
}

function CartaoConteudo({ className, ...props }: React.ComponentProps<"div">) {
  return <div data-slot="cartao-conteudo" className={cn("px-[var(--espacamento-4)]", className)} {...props} />;
}

function CartaoRodape({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="cartao-rodape"
      className={cn(
        "flex items-center px-[var(--espacamento-4)] [.border-t]:pt-[var(--espacamento-4)]",
        className,
      )}
      {...props}
    />
  );
}

export { Cartao, CartaoCabecalho, CartaoRodape, CartaoTitulo, CartaoAcao, CartaoDescricao, CartaoConteudo };
