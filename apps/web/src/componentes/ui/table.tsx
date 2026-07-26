"use client";

import * as React from "react";

import { cn } from "@/lib/utils";

/**
 * Tabela base (`table`) — T4.
 *
 * Primitivo de marcacao HTML de tabela simples (sem virtualizacao). A
 * data-table configuravel e virtualizada (`TabelaDeDados`, 10.000 linhas) e
 * componente de DOMINIO da F09a/A2 — vive em `src/componentes/dominio/**` e
 * consome este primitivo por baixo.
 */

function TabelaBase({ className, ...props }: React.ComponentProps<"table">) {
  return (
    <div data-slot="tabela-base-recipiente" className="relative w-full overflow-x-auto">
      <table
        data-slot="tabela-base"
        className={cn("w-full caption-bottom estilo-corpo text-texto-primario", className)}
        {...props}
      />
    </div>
  );
}

function TabelaBaseCabecalho({ className, ...props }: React.ComponentProps<"thead">) {
  return (
    <thead
      data-slot="tabela-base-cabecalho"
      className={cn("[&_tr]:border-b [&_tr]:border-borda-sutil", className)}
      {...props}
    />
  );
}

function TabelaBaseCorpo({ className, ...props }: React.ComponentProps<"tbody">) {
  return (
    <tbody
      data-slot="tabela-base-corpo"
      className={cn("[&_tr:last-child]:border-0", className)}
      {...props}
    />
  );
}

function TabelaBaseRodape({ className, ...props }: React.ComponentProps<"tfoot">) {
  return (
    <tfoot
      data-slot="tabela-base-rodape"
      className={cn(
        "border-t border-borda-sutil bg-fundo-sutil font-medium [&>tr]:last:border-b-0",
        className,
      )}
      {...props}
    />
  );
}

function TabelaBaseLinha({ className, ...props }: React.ComponentProps<"tr">) {
  return (
    <tr
      data-slot="tabela-base-linha"
      className={cn(
        "border-b border-borda-sutil transition-colors duration-imediata ease-padrao",
        "hover:bg-fundo-enfase",
        "data-[selecionada=true]:bg-acao-sutil-fundo",
        className,
      )}
      {...props}
    />
  );
}

function TabelaBaseCabecalhoDeColuna({ className, ...props }: React.ComponentProps<"th">) {
  return (
    <th
      data-slot="tabela-base-cabecalho-de-coluna"
      scope="col"
      className={cn(
        "h-10 px-2 estilo-rotulo text-left align-middle whitespace-nowrap text-texto-secundario",
        "[&:has([role=checkbox])]:pr-0 [&>[role=checkbox]]:translate-y-px",
        className,
      )}
      {...props}
    />
  );
}

function TabelaBaseCelula({ className, ...props }: React.ComponentProps<"td">) {
  return (
    <td
      data-slot="tabela-base-celula"
      className={cn(
        "p-2 align-middle whitespace-nowrap",
        "[&:has([role=checkbox])]:pr-0 [&>[role=checkbox]]:translate-y-px",
        className,
      )}
      {...props}
    />
  );
}

function TabelaBaseLegenda({ className, ...props }: React.ComponentProps<"caption">) {
  return (
    <caption
      data-slot="tabela-base-legenda"
      className={cn("mt-4 estilo-legenda text-texto-terciario", className)}
      {...props}
    />
  );
}

export {
  TabelaBase,
  TabelaBaseCabecalho,
  TabelaBaseCorpo,
  TabelaBaseRodape,
  TabelaBaseLinha,
  TabelaBaseCabecalhoDeColuna,
  TabelaBaseCelula,
  TabelaBaseLegenda,
};
