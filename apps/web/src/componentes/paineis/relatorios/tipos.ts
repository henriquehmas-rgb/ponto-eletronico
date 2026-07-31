import type { Esquema } from "@/lib/api";

/**
 * Formato interno de `colunasDisponiveis`/`filtrosDisponiveis`/`agrupamentos`
 * (F11/A1, `apps/api/app/relatorios/catalogo.py`, seção "Formato interno").
 * O contrato só exige `type: object` — o conteúdo é decisão de A1, e esta
 * tela é o único consumidor de frontend, então o formato é espelhado aqui,
 * a partir da mesma fonte (não duplicado por acaso: se `catalogo.py` mudar
 * o formato, este arquivo muda junto, no mesmo commit).
 */
export interface ColunaDoCatalogo {
  chave: string;
  rotulo: string;
  tipo: "texto" | "numero" | "data" | "booleano" | "uuid";
  duracao: boolean;
}

export interface FiltroDoCatalogo {
  chave: string;
  rotulo: string;
  tipo: "texto" | "numero" | "data" | "booleano" | "uuid";
}

export interface AgrupamentoDoCatalogo {
  chave: string;
  rotulo: string;
}

function ehObjeto(valor: unknown): valor is Record<string, unknown> {
  return typeof valor === "object" && valor !== null;
}

/** Lê `colunasDisponiveis` (`RelatorioDefinicao`) no formato fixado por
 * `catalogo.py`. Devolve `[]` para qualquer formato inesperado — a tela
 * genérica nunca quebra por causa de um relatório com catálogo incompleto,
 * só mostra menos colunas configuráveis. */
export function colunasDoCatalogo(
  definicao: Esquema<"RelatorioDefinicao"> | undefined,
): ColunaDoCatalogo[] {
  const bruto = definicao?.colunasDisponiveis;
  if (!ehObjeto(bruto) || !Array.isArray(bruto.colunas)) return [];
  return bruto.colunas
    .filter(ehObjeto)
    .filter(
      (item): item is Record<string, unknown> & { chave: string } => typeof item.chave === "string",
    )
    .map((item) => ({
      chave: item.chave,
      rotulo: typeof item.rotulo === "string" ? item.rotulo : item.chave,
      tipo: (typeof item.tipo === "string" ? item.tipo : "texto") as ColunaDoCatalogo["tipo"],
      duracao: item.duracao === true,
    }));
}

/** Lê `filtrosDisponiveis` no formato fixado por `catalogo.py`. */
export function filtrosDoCatalogo(
  definicao: Esquema<"RelatorioDefinicao"> | undefined,
): FiltroDoCatalogo[] {
  const bruto = definicao?.filtrosDisponiveis;
  if (!ehObjeto(bruto) || !Array.isArray(bruto.filtros)) return [];
  return bruto.filtros
    .filter(ehObjeto)
    .filter(
      (item): item is Record<string, unknown> & { chave: string } => typeof item.chave === "string",
    )
    .map((item) => ({
      chave: item.chave,
      rotulo: typeof item.rotulo === "string" ? item.rotulo : item.chave,
      tipo: (typeof item.tipo === "string" ? item.tipo : "texto") as FiltroDoCatalogo["tipo"],
    }));
}

/** Lê `agrupamentos` no formato fixado por `catalogo.py`. */
export function agrupamentosDoCatalogo(
  definicao: Esquema<"RelatorioDefinicao"> | undefined,
): AgrupamentoDoCatalogo[] {
  const bruto = definicao?.agrupamentos;
  if (!ehObjeto(bruto) || !Array.isArray(bruto.agrupamentos)) return [];
  return bruto.agrupamentos
    .filter(ehObjeto)
    .filter(
      (item): item is Record<string, unknown> & { chave: string } => typeof item.chave === "string",
    )
    .map((item) => ({
      chave: item.chave,
      rotulo: typeof item.rotulo === "string" ? item.rotulo : item.chave,
    }));
}

export const ROTULO_CATEGORIA: Record<string, string> = {
  operacional: "Operacional",
  gerencial: "Gerencial",
  fiscal: "Fiscal",
  financeiro: "Financeiro",
  lgpd: "LGPD",
};

export const ROTULO_FORMATO: Record<string, string> = {
  json: "JSON",
  csv: "CSV",
  xlsx: "Excel (XLSX)",
  pdf: "PDF",
};

export const ROTULO_STATUS_EXECUCAO: Record<string, string> = {
  enfileirado: "Na fila",
  processando: "Processando",
  concluido: "Concluído",
  falhou: "Falhou",
  cancelado: "Cancelado",
  expirado: "Expirado",
};
