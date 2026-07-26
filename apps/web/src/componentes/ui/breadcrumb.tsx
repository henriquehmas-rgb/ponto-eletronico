import * as React from "react";
import { ChevronRight, MoreHorizontal } from "lucide-react";
import { Slot } from "radix-ui";

import { cn } from "@/lib/utils";

/** Trilha de navegacao (`breadcrumb`) — T4. */

function Trilha({ ...props }: React.ComponentProps<"nav">) {
  return <nav aria-label="trilha de navegacao" data-slot="trilha" {...props} />;
}

function TrilhaLista({ className, ...props }: React.ComponentProps<"ol">) {
  return (
    <ol
      data-slot="trilha-lista"
      className={cn(
        "flex flex-wrap items-center gap-1.5 estilo-corpo text-texto-terciario break-words sm:gap-2.5",
        className,
      )}
      {...props}
    />
  );
}

function TrilhaItem({ className, ...props }: React.ComponentProps<"li">) {
  return <li data-slot="trilha-item" className={cn("inline-flex items-center gap-1.5", className)} {...props} />;
}

function TrilhaLink({
  asChild,
  className,
  ...props
}: React.ComponentProps<"a"> & { asChild?: boolean }) {
  const Comp = asChild ? Slot.Root : "a";
  return (
    <Comp
      data-slot="trilha-link"
      className={cn(
        "underline-offset-4 transition-colors duration-imediata ease-padrao hover:text-texto-primario hover:underline",
        className,
      )}
      {...props}
    />
  );
}

function TrilhaPagina({ className, ...props }: React.ComponentProps<"span">) {
  return (
    <span
      data-slot="trilha-pagina"
      role="link"
      aria-disabled="true"
      aria-current="page"
      className={cn("font-normal text-texto-primario", className)}
      {...props}
    />
  );
}

function TrilhaSeparador({ children, className, ...props }: React.ComponentProps<"li">) {
  return (
    <li
      data-slot="trilha-separador"
      role="presentation"
      aria-hidden="true"
      className={cn("[&>svg]:size-3.5", className)}
      {...props}
    >
      {children ?? <ChevronRight />}
    </li>
  );
}

function TrilhaReticencias({ className, ...props }: React.ComponentProps<"span">) {
  return (
    <span
      data-slot="trilha-reticencias"
      role="presentation"
      aria-hidden="true"
      className={cn("flex size-9 items-center justify-center", className)}
      {...props}
    >
      <MoreHorizontal className="size-4" />
      <span className="sr-only">Mais itens da trilha</span>
    </span>
  );
}

export { Trilha, TrilhaLista, TrilhaItem, TrilhaLink, TrilhaPagina, TrilhaSeparador, TrilhaReticencias };
