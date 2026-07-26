import * as React from "react";
import { ChevronLeftIcon, ChevronRightIcon, MoreHorizontalIcon } from "lucide-react";

import { cn } from "@/lib/utils";
import { buttonVariants } from "@/componentes/ui/button";

/** Paginacao — T4. */

function Paginacao({ className, ...props }: React.ComponentProps<"nav">) {
  return (
    <nav
      role="navigation"
      aria-label="paginacao"
      data-slot="paginacao"
      className={cn("mx-auto flex w-full justify-center", className)}
      {...props}
    />
  );
}

function PaginacaoConteudo({ className, ...props }: React.ComponentProps<"ul">) {
  return (
    <ul
      data-slot="paginacao-conteudo"
      className={cn("flex flex-row items-center gap-1", className)}
      {...props}
    />
  );
}

function PaginacaoItem({ ...props }: React.ComponentProps<"li">) {
  return <li data-slot="paginacao-item" {...props} />;
}

type PaginacaoLinkProps = {
  ativa?: boolean;
  tamanho?: "padrao" | "icone";
} & React.ComponentProps<"a">;

function PaginacaoLink({ className, ativa, tamanho = "icone", ...props }: PaginacaoLinkProps) {
  return (
    <a
      aria-current={ativa ? "page" : undefined}
      data-slot="paginacao-link"
      data-ativa={ativa}
      className={cn(
        buttonVariants({ variant: ativa ? "secundaria" : "sutil", tamanho }),
        className,
      )}
      {...props}
    />
  );
}

function PaginacaoAnterior({ className, ...props }: React.ComponentProps<typeof PaginacaoLink>) {
  return (
    <PaginacaoLink
      aria-label="Ir para a pagina anterior"
      tamanho="padrao"
      className={cn("gap-1 px-2.5", className)}
      {...props}
    >
      <ChevronLeftIcon />
      <span className="hidden sm:block">Anterior</span>
    </PaginacaoLink>
  );
}

function PaginacaoProxima({ className, ...props }: React.ComponentProps<typeof PaginacaoLink>) {
  return (
    <PaginacaoLink
      aria-label="Ir para a proxima pagina"
      tamanho="padrao"
      className={cn("gap-1 px-2.5", className)}
      {...props}
    >
      <span className="hidden sm:block">Proxima</span>
      <ChevronRightIcon />
    </PaginacaoLink>
  );
}

function PaginacaoReticencias({ className, ...props }: React.ComponentProps<"span">) {
  return (
    <span
      aria-hidden
      data-slot="paginacao-reticencias"
      className={cn("flex size-9 items-center justify-center", className)}
      {...props}
    >
      <MoreHorizontalIcon className="size-4" />
      <span className="sr-only">Mais paginas</span>
    </span>
  );
}

export {
  Paginacao,
  PaginacaoConteudo,
  PaginacaoLink,
  PaginacaoItem,
  PaginacaoAnterior,
  PaginacaoProxima,
  PaginacaoReticencias,
};
